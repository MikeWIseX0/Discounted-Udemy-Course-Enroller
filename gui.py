# pyrefly: ignore [missing-import]
import customtkinter as ctk
import tkinter as tk
import queue
import threading
import time
import os
import sys
import traceback
from webbrowser import open as web

from base import LINKS, VERSION, LoginException, Scraper, Udemy, scraper_dict, logger, get_user_data_path
from duce.core.images import icon


def verify_dependencies():
    required = {
        "cryptography": "cryptography",
        "curl_cffi": "curl-cffi",
        "requests": "requests",
        "customtkinter": "customtkinter",
        "darkdetect": "darkdetect",
        "loguru": "loguru"
    }
    missing = []
    for module, pkg in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)
    if missing:
        msg = f"Error: Missing required Python packages:\n{', '.join(missing)}\n\nPlease run:\npip install -r requirements.txt\nto install them."
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, msg, "Dependency Check Failed", 0x10)
        except Exception:
            pass
        print(msg, file=sys.stderr)
        sys.exit(1)


verify_dependencies()

# Set up global CustomTkinter themes
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MainWindowAdapter:
    """Adapter to match original PySimpleGUI write_event_value pattern."""

    def __init__(self, app):
        self.app = app

    def write_event_value(self, event, value):
        self.app.write_event_value(event, value)

    def was_closed(self):
        try:
            return not self.app.winfo_exists()
        except Exception:
            return True


class ScraperProgressRow:
    """Row component showing progress bar and status for an individual website scraper."""

    def __init__(self, parent, site_name, row_idx):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.grid_columnconfigure(1, weight=1)

        self.label = ctk.CTkLabel(
            self.frame,
            text=site_name,
            width=130,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            text_color="#E1E1E6"
        )
        self.label.grid(row=0, column=0, padx=(5, 10), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.frame,
            height=10,
            progress_color="#1F85DE",
            fg_color="#2C2C2E"
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=1, padx=10, sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.frame,
            text="Pending",
            width=120,
            anchor="e",
            font=("Segoe UI", 11),
            text_color="#A0A0A5"
        )
        self.status_label.grid(row=0, column=2, padx=(10, 5), sticky="e")
        self.row_idx = row_idx

    def set_visible(self, visible):
        if visible:
            self.frame.grid(row=self.row_idx, column=0, sticky="ew", pady=3)
        else:
            self.frame.grid_forget()

    def update_progress(self, val, max_val, visible):
        if max_val:
            self.progress_bar.set(float(val) / float(max_val))
            self.status_label.configure(
                text=f"Scraping {val}/{max_val}", text_color="#1F85DE")
        else:
            self.progress_bar.set(0.0)
            self.status_label.configure(
                text="Scraping...", text_color="#1F85DE")

    def set_done(self, done):
        if done:
            self.progress_bar.set(1.0)
            self.progress_bar.configure(progress_color="#2ECC71")
            self.status_label.configure(text="✔ Done", text_color="#2ECC71")
        else:
            self.progress_bar.set(0.0)
            self.progress_bar.configure(progress_color="#1F85DE")
            self.status_label.configure(
                text="Scraping...", text_color="#1F85DE")

    def set_error(self, err_msg="Error"):
        self.progress_bar.set(0.0)
        self.status_label.configure(text=f"❌ {err_msg}", text_color="#FF453A")


class ProfileSelectionDialog(ctk.CTkToplevel):
    """Dialog allowing user to choose a browser/profile to load cookies from."""

    def __init__(self, parent, profiles, response_queue):
        super().__init__(parent)
        self.title("Select Browser Profile")
        self.geometry("450x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.response_queue = response_queue
        self.selected_idx = 0

        # Center the dialog
        self.update_idletasks()
        width = 450
        height = 220
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        self.frame = ctk.CTkFrame(self, fg_color="#121214")
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)

        lbl = ctk.CTkLabel(
            self.frame,
            text="Multiple browser profiles with Udemy cookies were found.\nPlease select which profile to load cookies from:",
            font=("Segoe UI", 12),
            text_color="#E1E1E6",
            justify="left"
        )
        lbl.pack(pady=(10, 15), anchor="w", padx=10)

        self.combo = ctk.CTkComboBox(
            self.frame,
            values=profiles,
            width=380,
            state="readonly",
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            button_color="#2ECC71",
            button_hover_color="#27AE60",
            dropdown_fg_color="#1C1C1E",
            dropdown_hover_color="#3A3A3C",
            dropdown_text_color="#FFFFFF"
        )
        self.combo.pack(pady=10)
        self.combo.set(profiles[0])

        self.profiles = profiles

        select_btn = ctk.CTkButton(
            self.frame,
            text="Select & Load",
            fg_color="#2ECC71",
            hover_color="#27AE60",
            text_color="#121214",
            font=("Segoe UI", 12, "bold"),
            command=self.on_select
        )
        select_btn.pack(pady=(15, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_select(self):
        val = self.combo.get()
        try:
            idx = self.profiles.index(val)
        except ValueError:
            idx = 0
        self.response_queue.put(idx)
        self.destroy()

    def on_close(self):
        self.response_queue.put(0)
        self.destroy()


class CookieInstructionsDialog(ctk.CTkToplevel):
    """Custom Modal Dialog to guide user when automatic cookie import fails."""

    def __init__(self, parent, cookies_path):
        super().__init__(parent)
        self.title("Cookie Import Instructions")
        self.geometry("640x530")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center the dialog
        self.update_idletasks()
        width = 640
        height = 530
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        self.frame = ctk.CTkFrame(self, fg_color="#121214")
        self.frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(4, weight=1)

        title_lbl = ctk.CTkLabel(
            self.frame,
            text="Udemy Cookie Import Instructions",
            font=("Segoe UI", 16, "bold"),
            text_color="#00F2FE"
        )
        title_lbl.grid(row=0, column=0, pady=(15, 10))

        desc_lbl = ctk.CTkLabel(
            self.frame,
            text="Automatic browser cookie extraction is deprecated due to modern browser security restrictions.\nFollow the easy steps below to log in using cookies:",
            font=("Segoe UI", 11),
            text_color="#E1E1E6",
            justify="left"
        )
        desc_lbl.grid(row=1, column=0, padx=15, pady=5)

        self.path_entry = ctk.CTkEntry(
            self.frame,
            width=500,
            font=("Consolas", 10),
            fg_color="#1C1C1E",
            border_color="#3A3A3C"
        )
        self.path_entry.grid(row=2, column=0, padx=15, pady=5)
        self.path_entry.insert(0, cookies_path)
        self.path_entry.configure(state="readonly")

        instr_lbl = ctk.CTkLabel(
            self.frame,
            text="How to log in manually using cookies:",
            font=("Segoe UI", 13, "bold"),
            text_color="#00F2FE",
            anchor="w"
        )
        instr_lbl.grid(row=3, column=0, padx=20, pady=(15, 5), sticky="w")

        steps_box = ctk.CTkTextbox(
            self.frame,
            font=("Segoe UI", 11),
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            border_width=1,
            wrap="word"
        )
        steps_box.grid(row=4, column=0, padx=20, pady=(0, 15), sticky="nsew")

        steps_text = (
            "Step 1: Install the 'Cookie-Editor' extension in Chrome, Firefox, Edge, or Brave.\n\n\n"
            "Step 2: Log in to your Udemy account in your browser.\n\n\n"
            "Step 3: Click the Cookie-Editor extension icon, then click 'Export' (select 'JSON') to copy cookies to clipboard.\n\n\n"
            "Step 4: Click 'Extract & Auto Login' in this app to automatically import from clipboard and log in!\n\n\n"
            "Alternative Option:\n\n"
            "If clipboard auto-detection fails, click 'Open cookies.json' below, paste your copied cookies JSON into it, save/close, and try again."
        )
        steps_box.insert("1.0", steps_text)
        steps_box.configure(state="disabled")

        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.grid(row=5, column=0, padx=20, pady=(0, 15), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        open_file_btn = ctk.CTkButton(
            btn_frame,
            text="Open cookies.json",
            fg_color="#252528",
            hover_color="#3A3A3C",
            text_color="#FFFFFF",
            command=lambda: self.open_file(cookies_path)
        )
        open_file_btn.grid(row=0, column=0, padx=5)

        open_folder_btn = ctk.CTkButton(
            btn_frame,
            text="Open Folder",
            fg_color="#252528",
            hover_color="#3A3A3C",
            text_color="#FFFFFF",
            command=lambda: self.open_folder(cookies_path)
        )
        open_folder_btn.grid(row=0, column=1, padx=5)

        close_btn = ctk.CTkButton(
            btn_frame,
            text="OK",
            fg_color="#2ECC71",
            hover_color="#27AE60",
            text_color="#121214",
            command=self.destroy
        )
        close_btn.grid(row=0, column=2, padx=5)

    def open_file(self, cookies_path):
        try:
            os.startfile(cookies_path)
        except Exception as e:
            logger.error(f"Failed to open cookies file: {e}")
            ErrorPopupDialog(
                self, f"Could not open cookies file:\n{e}\n\nPath:\n{cookies_path}", "Error Opening File")

    def open_folder(self, cookies_path):
        try:
            os.startfile(os.path.dirname(cookies_path))
        except Exception as e:
            logger.error(f"Failed to open cookies folder: {e}")
            ErrorPopupDialog(
                self, f"Could not open cookies folder:\n{e}\n\nPath:\n{os.path.dirname(cookies_path)}", "Error Opening Folder")


class ErrorPopupDialog(ctk.CTkToplevel):
    """Custom Modal Dialog to display detailed error traces styled to match CustomTkinter."""

    def __init__(self, parent, message, title="Error"):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center the popup
        self.update_idletasks()
        width = 520
        height = 360
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        self.frame = ctk.CTkFrame(self, fg_color="#121214")
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        title_lbl = ctk.CTkLabel(
            self.frame,
            text=title,
            font=("Segoe UI", 14, "bold"),
            text_color="#FF453A"
        )
        title_lbl.grid(row=0, column=0, pady=(10, 5))

        text_box = ctk.CTkTextbox(
            self.frame,
            font=("Consolas", 10),
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            border_width=1
        )
        text_box.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        text_box.insert("1.0", message)
        text_box.configure(state="disabled")

        close_btn = ctk.CTkButton(
            self.frame,
            text="Close",
            fg_color="#2ECC71",
            hover_color="#27AE60",
            text_color="#121214",
            command=self.destroy
        )
        close_btn.grid(row=2, column=0, pady=(0, 10))


class LoginFrame(ctk.CTkFrame):
    """View component for authentication interface."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        # Header / Brand Section
        self.brand_lbl = ctk.CTkLabel(
            self,
            text="DUCE",
            font=("Segoe UI", 36, "bold"),
            text_color="#2ECC71"
        )
        self.brand_lbl.pack(pady=(40, 5))

        self.desc_lbl = ctk.CTkLabel(
            self,
            text="Discounted Udemy Course Enroller",
            font=("Segoe UI", 12),
            text_color="#A0A0A5"
        )
        self.desc_lbl.pack(pady=(0, 30))

        # Centered Login Card
        self.card = ctk.CTkFrame(
            self, fg_color="#1E1E1E", width=420, height=360, corner_radius=16)
        self.card.pack(pady=10)
        self.card.pack_propagate(False)

        # Toggle Segmented Button for auto / manual login views
        self.segment = ctk.CTkSegmentedButton(
            self.card,
            values=["Cookie Auto-Login", "Manual Login"],
            command=self.toggle_login_mode,
            font=("Segoe UI", 12, "bold"),
            selected_color="#1E824C",
            unselected_color="#2C2C2E",
            text_color="#E1E1E6"
        )
        self.segment.pack(padx=20, pady=25, fill="x")
        self.segment.set("Cookie Auto-Login")

        # sub-frame container
        self.mode_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.mode_frame.pack(fill="both", expand=True)

        # Initialize views
        self.setup_auto_login_view()
        self.setup_manual_login_view()

        # Show default auto view
        self.show_auto_login()

        # Status message label at the very bottom
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 11, "italic"),
            text_color="#00F2FE",
            wraplength=450
        )
        self.status_label.pack(pady=(20, 20))

    def setup_auto_login_view(self):
        self.auto_frame = ctk.CTkFrame(self.mode_frame, fg_color="transparent")
        self.auto_frame.grid_columnconfigure(0, weight=1)

        info_lbl = ctk.CTkLabel(
            self.auto_frame,
            text="Extract cookies from active browser session automatically.",
            font=("Segoe UI", 11),
            text_color="#A0A0A5",
            wraplength=350
        )
        info_lbl.grid(row=0, column=0, padx=20, pady=(10, 20))

        self.sli_a_var = tk.BooleanVar(
            value=self.app.udemy.settings["stay_logged_in"]["auto"])
        self.sli_a_cb = ctk.CTkCheckBox(
            self.auto_frame,
            text="Stay logged-in (auto)",
            variable=self.sli_a_var,
            text_color="#E1E1E6",
            font=("Segoe UI", 12),
            border_color="#A0A0A5",
            hover_color="#2ECC71",
            fg_color="#2ECC71"
        )
        self.sli_a_cb.grid(row=1, column=0, padx=20, pady=10)

        self.auto_btn = ctk.CTkButton(
            self.auto_frame,
            text="Extract & Auto Login",
            fg_color="#2ECC71",
            text_color="#121214",
            hover_color="#27AE60",
            height=40,
            corner_radius=20,
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.app.on_auto_login_click(self.sli_a_var.get())
        )
        self.auto_btn.grid(row=2, column=0, padx=20, pady=25, sticky="ew")

    def setup_manual_login_view(self):
        self.manual_frame = ctk.CTkFrame(
            self.mode_frame, fg_color="transparent")
        self.manual_frame.grid_columnconfigure(0, weight=1)

        self.email_entry = ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Email Address",
            height=35,
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            text_color="#FFFFFF",
            font=("Segoe UI", 12)
        )
        self.email_entry.grid(row=0, column=0, padx=25, pady=8, sticky="ew")
        self.email_entry.insert(0, self.app.udemy.settings.get("email", ""))

        self.password_entry = ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Password",
            show="*",
            height=35,
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            text_color="#FFFFFF",
            font=("Segoe UI", 12)
        )
        self.password_entry.grid(row=1, column=0, padx=25, pady=8, sticky="ew")
        self.password_entry.insert(
            0, self.app.udemy.settings.get("password", ""))

        self.sli_m_var = tk.BooleanVar(
            value=self.app.udemy.settings["stay_logged_in"]["manual"])
        self.sli_m_cb = ctk.CTkCheckBox(
            self.manual_frame,
            text="Stay logged-in (manual)",
            variable=self.sli_m_var,
            text_color="#E1E1E6",
            font=("Segoe UI", 12),
            border_color="#A0A0A5",
            hover_color="#2ECC71",
            fg_color="#2ECC71"
        )
        self.sli_m_cb.grid(row=2, column=0, padx=25, pady=8)

        self.manual_btn = ctk.CTkButton(
            self.manual_frame,
            text="Login with Account",
            fg_color="#2ECC71",
            text_color="#121214",
            hover_color="#27AE60",
            height=40,
            corner_radius=20,
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.app.on_manual_login_click(
                self.email_entry.get(),
                self.password_entry.get(),
                self.sli_m_var.get()
            )
        )
        self.manual_btn.grid(row=3, column=0, padx=25,
                             pady=(15, 10), sticky="ew")

    def toggle_login_mode(self, mode):
        if mode == "Cookie Auto-Login":
            self.show_auto_login()
        else:
            self.show_manual_login()

    def show_auto_login(self):
        self.manual_frame.pack_forget()
        self.auto_frame.pack(fill="both", expand=True, padx=20)

    def show_manual_login(self):
        self.auto_frame.pack_forget()
        self.manual_frame.pack(fill="both", expand=True, padx=20)

    def disable_buttons(self):
        self.auto_btn.configure(state="disabled")
        self.manual_btn.configure(state="disabled")
        self.segment.configure(state="disabled")

    def enable_buttons(self):
        self.auto_btn.configure(state="normal")
        self.manual_btn.configure(state="normal")
        self.segment.configure(state="normal")


class DashboardPage(ctk.CTkFrame):
    """Page component displaying enroller controller, scraper progress and terminal logs."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header title
        self.header_label = ctk.CTkLabel(
            self,
            text="Course Enrollment Dashboard",
            font=("Segoe UI", 20, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.header_label.grid(row=0, column=0, pady=(0, 15), sticky="w")

        # Main Container
        self.container = ctk.CTkFrame(
            self, fg_color="#1E1E1E", corner_radius=12)
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        # 1. Main View Frame (with Start Button & Hint)
        self.main_col_frame = ctk.CTkFrame(
            self.container, fg_color="transparent")
        self.main_col_frame.grid(
            row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.main_col_frame.grid_columnconfigure(0, weight=1)
        self.main_col_frame.grid_rowconfigure(1, weight=1)

        welcome_label = ctk.CTkLabel(
            self.main_col_frame,
            text="Ready to start automated enrollment?",
            font=("Segoe UI", 16, "bold"),
            text_color="#E1E1E6"
        )
        welcome_label.grid(row=0, column=0, pady=(100, 15))

        self.start_btn = ctk.CTkButton(
            self.main_col_frame,
            text="Start Enroller",
            fg_color="#2ECC71",
            text_color="#121214",
            hover_color="#27AE60",
            width=260,
            height=50,
            corner_radius=25,
            font=("Segoe UI", 14, "bold"),
            command=self.app.start_process
        )
        self.start_btn.grid(row=1, column=0, pady=25)

        hint_label = ctk.CTkLabel(
            self.main_col_frame,
            text="Once started, the enroller will run in the background\nand cannot be stopped until scraping and course enrollment is complete.",
            font=("Segoe UI", 11),
            text_color="#A0A0A5"
        )
        hint_label.grid(row=2, column=0, pady=(15, 100))

        # 2. Running View Frame (contains Progress, Stats, and Logs)
        self.run_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.run_frame.grid_columnconfigure(0, weight=1)
        self.run_frame.grid_rowconfigure(2, weight=1)

        # Scraper Progress Frame
        self.scrape_frame = ctk.CTkFrame(
            self.run_frame, fg_color="#252528", corner_radius=8)
        self.scrape_frame.grid(row=0, column=0, padx=15,
                               pady=(10, 5), sticky="ew")
        self.scrape_frame.grid_columnconfigure(0, weight=1)

        scrape_title = ctk.CTkLabel(
            self.scrape_frame,
            text="Scraping Progress",
            font=("Segoe UI", 13, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        scrape_title.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.site_rows_container = ctk.CTkScrollableFrame(
            self.scrape_frame, fg_color="transparent", height=220)
        self.site_rows_container.grid(
            row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.site_rows_container.grid_columnconfigure(0, weight=1)

        self.site_rows = {}
        for idx, site in enumerate(self.app.udemy.settings["sites"]):
            row = ScraperProgressRow(self.site_rows_container, site, idx)
            row.set_visible(False)
            self.site_rows[site] = row

        # Enrollment Stats Panel Frame (Stats Card + Current Course Card)
        self.enroll_frame = ctk.CTkFrame(
            self.run_frame, fg_color="transparent")
        self.enroll_frame.grid_columnconfigure((0, 1), weight=1)

        # Stats Card
        self.stats_card = ctk.CTkFrame(
            self.enroll_frame, fg_color="#252528", corner_radius=8)
        self.stats_card.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.stats_card.grid_columnconfigure((0, 1), weight=1)

        stats_title = ctk.CTkLabel(
            self.stats_card,
            text="Enrollment Statistics",
            font=("Segoe UI", 13, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        stats_title.grid(row=0, column=0, columnspan=2,
                         padx=15, pady=(10, 5), sticky="w")

        self.stat_labels = {}
        stats_def = [
            ("enrolled", "Enrolled:", "#2ECC71"),
            ("already", "Already Enrolled:", "#00FA9A"),
            ("expired", "Expired:", "#FF453A"),
            ("amount_saved", "Amount Saved:", "#2ECC71"),
            ("excluded", "Excluded:", "#FF9F0A"),
            ("ready_enroll", "Pending:", "#BF5AF2")
        ]
        for idx, (sid, label_text, color) in enumerate(stats_def):
            r = (idx // 2) + 1
            c = idx % 2

            f = ctk.CTkFrame(self.stats_card, fg_color="transparent")
            f.grid(row=r, column=c, padx=12, pady=10, sticky="ew")
            f.grid_columnconfigure(0, weight=1)

            lbl = ctk.CTkLabel(
                f,
                text=label_text,
                font=("Segoe UI", 11),
                text_color="#A0A0A5",
                anchor="w"
            )
            lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))

            val_lbl = ctk.CTkLabel(
                f,
                text="0",
                font=("Segoe UI", 24, "bold"),
                text_color=color,
                anchor="w"
            )
            val_lbl.grid(row=1, column=0, sticky="w", pady=(0, 4))
            self.stat_labels[sid] = val_lbl

        # Current Course Card
        self.course_card = ctk.CTkFrame(
            self.enroll_frame, fg_color="#252528", corner_radius=8)
        self.course_card.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        self.course_card.grid_columnconfigure(0, weight=1)

        self.progress_lbl_var = tk.StringVar(value="Current Course")
        course_title = ctk.CTkLabel(
            self.course_card,
            textvariable=self.progress_lbl_var,
            font=("Segoe UI", 13, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        course_title.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        self.course_title_lbl = ctk.CTkLabel(
            self.course_card,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#FFFFFF",
            anchor="w",
            wraplength=350
        )
        self.course_title_lbl.grid(
            row=1, column=0, padx=15, pady=2, sticky="w")

        self.course_url_box = ctk.CTkTextbox(
            self.course_card,
            height=40,
            font=("Consolas", 10),
            border_width=0,
            fg_color="transparent",
            text_color="#00BFFF",
            wrap="none"
        )
        self.course_url_box.grid(
            row=2, column=0, padx=15, pady=(2, 8), sticky="ew")
        self.course_url_box.configure(state="disabled")

        self.course_status_lbl = ctk.CTkLabel(
            self.course_card,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#00F2FE",
            anchor="w"
        )
        self.course_status_lbl.grid(
            row=3, column=0, padx=15, pady=(2, 10), sticky="w")

        # Logs Textbox Card
        self.logs_card = ctk.CTkFrame(
            self.run_frame, fg_color="#252528", corner_radius=8)
        self.logs_card.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")
        self.logs_card.grid_columnconfigure(0, weight=1)
        self.logs_card.grid_columnconfigure(1, weight=0)
        self.logs_card.grid_rowconfigure(1, weight=1)

        logs_title = ctk.CTkLabel(
            self.logs_card,
            text="Process Logs",
            font=("Segoe UI", 13, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        logs_title.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")

        self.stop_btn = ctk.CTkButton(
            self.logs_card,
            text="Stop Enroller",
            fg_color="#FF453A",
            hover_color="#D11A2A",
            text_color="#FFFFFF",
            width=110,
            height=24,
            corner_radius=6,
            font=("Segoe UI", 11, "bold"),
            command=self.app.cancel_process
        )
        self.stop_btn.grid(row=0, column=1, padx=15, pady=(10, 2), sticky="e")

        self.log_textbox = ctk.CTkTextbox(
            self.logs_card,
            font=("Consolas", 11),
            fg_color="#1C1C1E",
            text_color="#E1E1E6",
            border_color="#3A3A3C",
            border_width=1
        )
        self.log_textbox.grid(row=1, column=0, padx=15,
                              pady=(0, 15), sticky="nsew")

        # Color coding tags
        self.log_textbox.tag_config("timestamp", foreground="#72727A")
        self.log_textbox.tag_config("separator", foreground="#3A3A3C")
        self.log_textbox.tag_config("info", foreground="#E1E1E6")
        self.log_textbox.tag_config("warning", foreground="#FF9F0A")
        self.log_textbox.tag_config("error", foreground="#FF453A")
        self.log_textbox.tag_config("success", foreground="#2ECC71")
        self.log_textbox.tag_config("info_highlight", foreground="#00F2FE")
        self.log_textbox.tag_config("excluded", foreground="#8E8E93")

        self.log_textbox.configure(state="disabled")

        # 3. Done Summary Frame
        self.done_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.done_frame.grid_columnconfigure(0, weight=1)

        self.done_card = ctk.CTkFrame(
            self.done_frame, fg_color="#252528", corner_radius=12)
        self.done_card.grid(row=0, column=0, padx=20, pady=30, sticky="ew")
        self.done_card.grid_columnconfigure(0, weight=1)

        done_title = ctk.CTkLabel(
            self.done_card,
            text="🎉 Enrollment Complete!",
            font=("Segoe UI", 18, "bold"),
            text_color="#2ECC71"
        )
        done_title.grid(row=0, column=0, pady=(25, 15))

        self.done_stat_labels = {}
        done_stats_def = [
            ("se_c", "Successfully Enrolled: 0", "#2ECC71"),
            ("as_c", "Amount Saved: 0", "#2ECC71"),
            ("ae_c", "Already Enrolled: 0", "#00FA9A"),
            ("e_c", "Expired Courses: 0", "#FF453A"),
            ("ex_c", "Excluded Courses: 0", "#FF9F0A")
        ]

        curr_row = 1
        for key, text, color in done_stats_def:
            lbl = ctk.CTkLabel(
                self.done_card,
                text=text,
                font=("Segoe UI", 13, "bold"),
                text_color=color
            )
            lbl.grid(row=curr_row, column=0, pady=5)
            self.done_stat_labels[key] = lbl
            curr_row += 1

        self.reset_btn = ctk.CTkButton(
            self.done_card,
            text="Back to Settings",
            fg_color="#2ECC71",
            text_color="#121214",
            hover_color="#27AE60",
            width=200,
            height=40,
            corner_radius=20,
            font=("Segoe UI", 12, "bold"),
            command=self.app.reset_gui
        )
        self.reset_btn.grid(row=curr_row, column=0, pady=(20, 25))

    def set_running_state(self):
        self.main_col_frame.grid_forget()
        self.done_frame.grid_forget()
        self.run_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def set_site_row_visibility(self, site, visible):
        if site in self.site_rows:
            self.site_rows[site].set_visible(visible)

    def update_site_progress(self, site, val, max_val, visible):
        if site in self.site_rows:
            self.site_rows[site].update_progress(val, max_val, visible)

    def set_site_done(self, site, done):
        if site in self.site_rows:
            self.site_rows[site].set_done(done)

    def set_site_error(self, site, err_msg="Error"):
        if site in self.site_rows:
            self.site_rows[site].set_error(err_msg)

    def set_main_col_visible(self, visible):
        if visible:
            self.main_col_frame.grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)
        else:
            self.main_col_frame.grid_forget()

    def set_scrape_col_visible(self, visible):
        if visible:
            self.scrape_frame.grid(
                row=0, column=0, padx=15, pady=(10, 5), sticky="ew")
        else:
            self.scrape_frame.grid_forget()

    def set_output_col_visible(self, visible):
        if visible:
            self.logs_card.grid(row=2, column=0, padx=15,
                                pady=10, sticky="nsew")
        else:
            self.logs_card.grid_forget()

    def set_enrollment_panel_visible(self, visible):
        if visible:
            self.enroll_frame.grid(
                row=1, column=0, padx=15, pady=5, sticky="ew")
        else:
            self.enroll_frame.grid_forget()

    def set_done_col_visible(self, visible):
        if visible:
            self.run_frame.grid_forget()
            self.main_col_frame.grid_forget()
            self.done_frame.grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)
        else:
            self.done_frame.grid_forget()

    def update_course_title(self, text):
        self.course_title_lbl.configure(text=text)

    def update_course_status(self, text, color="#00F2FE"):
        self.course_status_lbl.configure(text=text, text_color=color)

    def update_course_url(self, text):
        self.course_url_box.configure(state="normal")
        self.course_url_box.delete("1.0", "end")
        self.course_url_box.insert("1.0", text)
        self.course_url_box.configure(state="disabled")

    def update_course_progress(self, text):
        self.progress_lbl_var.set(text)

    def update_stat(self, stat_name, val):
        if stat_name in self.stat_labels:
            self.stat_labels[stat_name].configure(text=str(val))

    def update_done_stat(self, key, val):
        if key in self.done_stat_labels:
            self.done_stat_labels[key].configure(text=str(val))

    def reset_to_start(self):
        self.run_frame.grid_forget()
        self.done_frame.grid_forget()

        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

        self.main_col_frame.grid(
            row=0, column=0, sticky="nsew", padx=20, pady=20)

        for row in self.site_rows.values():
            row.set_visible(False)
            row.set_done(False)

        for key in self.stat_labels:
            self.stat_labels[key].configure(text="0")
        self.progress_lbl_var.set("Current Course")
        self.course_title_lbl.configure(text="")
        self.course_status_lbl.configure(text="")

        self.course_url_box.configure(state="normal")
        self.course_url_box.delete("1.0", "end")
        self.course_url_box.configure(state="disabled")


class SettingsPage(ctk.CTkFrame):
    """Page component displaying grids of checkbox filters (Websites, Languages, Categories)."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self.header_label = ctk.CTkLabel(
            self,
            text="Websites & Filter Tags Settings",
            font=("Segoe UI", 20, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.header_label.grid(row=0, column=0, pady=(0, 15), sticky="w")

        # Scrollable container for checkboxes
        self.scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="#1E1E1E", corner_radius=12)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # 1. Websites Frame
        self.sites_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.sites_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        self.sites_frame.grid_columnconfigure((0, 1, 2), weight=1)

        sites_title = ctk.CTkLabel(
            self.sites_frame,
            text="Websites to Scrape",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        sites_title.grid(row=0, column=0, columnspan=2,
                         padx=15, pady=(12, 8), sticky="w")

        sites_btn_frame = ctk.CTkFrame(self.sites_frame, fg_color="transparent")
        sites_btn_frame.grid(row=0, column=2, padx=15, pady=(12, 8), sticky="e")

        all_on_sites_btn = ctk.CTkButton(
            sites_btn_frame,
            text="All On",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.select_all_sites
        )
        all_on_sites_btn.grid(row=0, column=0, padx=2)

        all_off_sites_btn = ctk.CTkButton(
            sites_btn_frame,
            text="All Off",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.deselect_all_sites
        )
        all_off_sites_btn.grid(row=0, column=1, padx=2)

        self.site_vars = {}
        sites_list = sorted(self.app.udemy.settings["sites"].keys())
        for idx, site in enumerate(sites_list):
            val = self.app.udemy.settings["sites"][site]
            var = tk.BooleanVar(value=val)
            cb = ctk.CTkCheckBox(
                self.sites_frame,
                text=site,
                variable=var,
                text_color="#E1E1E6",
                font=("Segoe UI", 12),
                border_color="#A0A0A5",
                hover_color="#2ECC71",
                fg_color="#2ECC71"
            )
            cb.grid(row=(idx // 3) + 1, column=idx %
                    3, padx=15, pady=8, sticky="w")
            self.site_vars[site] = var

        # 2. Languages Frame
        self.langs_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.langs_frame.grid(row=1, column=0, padx=15, pady=15, sticky="ew")
        self.langs_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        langs_title = ctk.CTkLabel(
            self.langs_frame,
            text="Course Languages",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        langs_title.grid(row=0, column=0, columnspan=2,
                         padx=15, pady=(12, 8), sticky="w")

        langs_btn_frame = ctk.CTkFrame(self.langs_frame, fg_color="transparent")
        langs_btn_frame.grid(row=0, column=3, padx=15, pady=(12, 8), sticky="e")

        all_on_langs_btn = ctk.CTkButton(
            langs_btn_frame,
            text="All On",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.select_all_langs
        )
        all_on_langs_btn.grid(row=0, column=0, padx=2)

        all_off_langs_btn = ctk.CTkButton(
            langs_btn_frame,
            text="All Off",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.deselect_all_langs
        )
        all_off_langs_btn.grid(row=0, column=1, padx=2)

        self.lang_vars = {}
        langs_list = sorted(self.app.udemy.settings["languages"].keys())
        for idx, lang in enumerate(langs_list):
            val = self.app.udemy.settings["languages"][lang]
            var = tk.BooleanVar(value=val)
            cb = ctk.CTkCheckBox(
                self.langs_frame,
                text=lang,
                variable=var,
                text_color="#E1E1E6",
                font=("Segoe UI", 12),
                border_color="#A0A0A5",
                hover_color="#2ECC71",
                fg_color="#2ECC71"
            )
            cb.grid(row=(idx // 4) + 1, column=idx %
                    4, padx=15, pady=8, sticky="w")
            self.lang_vars[lang] = var

        # 3. Categories Frame
        self.cats_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.cats_frame.grid(row=2, column=0, padx=15, pady=15, sticky="ew")
        self.cats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        cats_title = ctk.CTkLabel(
            self.cats_frame,
            text="Course Categories",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        cats_title.grid(row=0, column=0, columnspan=2,
                        padx=15, pady=(12, 8), sticky="w")

        cats_btn_frame = ctk.CTkFrame(self.cats_frame, fg_color="transparent")
        cats_btn_frame.grid(row=0, column=2, padx=15, pady=(12, 8), sticky="e")

        all_on_cats_btn = ctk.CTkButton(
            cats_btn_frame,
            text="All On",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.select_all_cats
        )
        all_on_cats_btn.grid(row=0, column=0, padx=2)

        all_off_cats_btn = ctk.CTkButton(
            cats_btn_frame,
            text="All Off",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=55,
            height=20,
            font=("Segoe UI", 10, "bold"),
            command=self.deselect_all_cats
        )
        all_off_cats_btn.grid(row=0, column=1, padx=2)

        self.cat_vars = {}
        cats_list = sorted(self.app.udemy.settings["categories"].keys())
        for idx, cat in enumerate(cats_list):
            val = self.app.udemy.settings["categories"][cat]
            var = tk.BooleanVar(value=val)
            cb = ctk.CTkCheckBox(
                self.cats_frame,
                text=cat,
                variable=var,
                text_color="#E1E1E6",
                font=("Segoe UI", 12),
                border_color="#A0A0A5",
                hover_color="#2ECC71",
                fg_color="#2ECC71"
            )
            cb.grid(row=(idx // 3) + 1, column=idx %
                    3, padx=15, pady=8, sticky="w")
            self.cat_vars[cat] = var

    def select_all_sites(self):
        for var in self.site_vars.values():
            var.set(True)

    def deselect_all_sites(self):
        for var in self.site_vars.values():
            var.set(False)

    def select_all_langs(self):
        for var in self.lang_vars.values():
            var.set(True)

    def deselect_all_langs(self):
        for var in self.lang_vars.values():
            var.set(False)

    def select_all_cats(self):
        for var in self.cat_vars.values():
            var.set(True)

    def deselect_all_cats(self):
        for var in self.cat_vars.values():
            var.set(False)


class ExclusionsPage(ctk.CTkFrame):
    """Page component displaying text exclusions, ratings, and save settings."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self.header_label = ctk.CTkLabel(
            self,
            text="Exclusions & Filter Limits",
            font=("Segoe UI", 20, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.header_label.grid(row=0, column=0, pady=(0, 15), sticky="w")

        # Scrollable container
        self.scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="#1E1E1E", corner_radius=12)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew")
        self.scroll_frame.grid_columnconfigure((0, 1), weight=1)

        # Instructor Frame
        self.inst_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.inst_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.inst_frame.grid_columnconfigure(0, weight=1)
        self.inst_frame.grid_rowconfigure(1, weight=1)

        inst_label = ctk.CTkLabel(
            self.inst_frame,
            text="Exclude Instructors",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        inst_label.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self.instructor_exclude_box = ctk.CTkTextbox(
            self.inst_frame,
            height=150,
            font=("Consolas", 11),
            border_color="#3A3A3C",
            border_width=1,
            fg_color="#1C1C1E"
        )
        self.instructor_exclude_box.grid(
            row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.instructor_exclude_box.insert("1.0", "\n".join(
            self.app.udemy.settings.get("instructor_exclude", [])))

        inst_hint = ctk.CTkLabel(
            self.inst_frame,
            text="Paste username(s) on new lines",
            font=("Segoe UI", 10),
            text_color="#A0A0A5"
        )
        inst_hint.grid(row=2, column=0, padx=15, pady=(0, 12), sticky="w")

        # Title Exclude Frame
        self.title_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.title_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        self.title_frame.grid_columnconfigure(0, weight=1)
        self.title_frame.grid_rowconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            self.title_frame,
            text="Exclude Title Keywords",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        title_label.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self.title_exclude_box = ctk.CTkTextbox(
            self.title_frame,
            height=150,
            font=("Consolas", 11),
            border_color="#3A3A3C",
            border_width=1,
            fg_color="#1C1C1E"
        )
        self.title_exclude_box.grid(
            row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.title_exclude_box.insert("1.0", "\n".join(
            self.app.udemy.settings.get("title_exclude", [])))

        title_hint = ctk.CTkLabel(
            self.title_frame,
            text="Keywords in new lines (case-insensitive)",
            font=("Segoe UI", 10),
            text_color="#A0A0A5"
        )
        title_hint.grid(row=2, column=0, padx=15, pady=(0, 12), sticky="w")

        # Sliders Frame
        self.slider_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.slider_frame.grid(row=1, column=0, columnspan=2,
                               padx=15, pady=15, sticky="ew")
        self.slider_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Rating Slider
        self.rating_label_var = tk.StringVar()
        self.update_rating_label(
            self.app.udemy.settings.get("min_rating", 0.0))

        rating_title = ctk.CTkLabel(
            self.slider_frame,
            textvariable=self.rating_label_var,
            font=("Segoe UI", 13, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        rating_title.grid(row=0, column=0, padx=15, pady=(12, 2), sticky="w")

        self.min_rating_slider = ctk.CTkSlider(
            self.slider_frame,
            from_=0.0,
            to=5.0,
            number_of_steps=10,
            fg_color="#2C2C2E",
            progress_color="#2ECC71",
            button_color="#2ECC71",
            button_hover_color="#27AE60",
            command=self.update_rating_label
        )
        self.min_rating_slider.set(
            self.app.udemy.settings.get("min_rating", 0.0))
        self.min_rating_slider.grid(
            row=1, column=0, padx=15, pady=(0, 15), sticky="ew")

        # Threshold Slider
        self.threshold_label_var = tk.StringVar()
        self.update_threshold_label(self.app.udemy.settings.get(
            "course_update_threshold_months", 24))

        threshold_title = ctk.CTkLabel(
            self.slider_frame,
            textvariable=self.threshold_label_var,
            font=("Segoe UI", 13, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        threshold_title.grid(row=0, column=1, padx=15,
                             pady=(12, 2), sticky="w")

        self.threshold_slider = ctk.CTkSlider(
            self.slider_frame,
            from_=1,
            to=48,
            number_of_steps=47,
            fg_color="#2C2C2E",
            progress_color="#2ECC71",
            button_color="#2ECC71",
            button_hover_color="#27AE60",
            command=self.update_threshold_label
        )
        self.threshold_slider.set(self.app.udemy.settings.get(
            "course_update_threshold_months", 24))
        self.threshold_slider.grid(
            row=1, column=1, padx=15, pady=(0, 15), sticky="ew")

        # Network Timeout Slider
        self.timeout_label_var = tk.StringVar()
        self.update_timeout_label(self.app.udemy.settings.get(
            "network_timeout", 60))

        timeout_title = ctk.CTkLabel(
            self.slider_frame,
            textvariable=self.timeout_label_var,
            font=("Segoe UI", 13, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        timeout_title.grid(row=0, column=2, padx=15,
                             pady=(12, 2), sticky="w")

        self.timeout_slider = ctk.CTkSlider(
            self.slider_frame,
            from_=5,
            to=180,
            number_of_steps=35,
            fg_color="#2C2C2E",
            progress_color="#2ECC71",
            button_color="#2ECC71",
            button_hover_color="#27AE60",
            command=self.update_timeout_label
        )
        self.timeout_slider.set(self.app.udemy.settings.get(
            "network_timeout", 60))
        self.timeout_slider.grid(
            row=1, column=2, padx=15, pady=(0, 15), sticky="ew")

        # Options Frame
        self.options_frame = ctk.CTkFrame(
            self.scroll_frame, fg_color="#252528", corner_radius=8)
        self.options_frame.grid(
            row=2, column=0, columnspan=2, padx=15, pady=15, sticky="ew")
        self.options_frame.grid_columnconfigure(0, weight=1)

        options_title = ctk.CTkLabel(
            self.options_frame,
            text="Additional Enrollment Options",
            font=("Segoe UI", 14, "bold"),
            text_color="#2ECC71",
            anchor="w"
        )
        options_title.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self.save_txt_var = tk.BooleanVar(
            value=self.app.udemy.settings.get("save_txt", False))
        self.save_txt_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Save enrolled courses list in text file",
            variable=self.save_txt_var,
            text_color="#E1E1E6",
            font=("Segoe UI", 12),
            border_color="#A0A0A5",
            hover_color="#2ECC71",
            fg_color="#2ECC71"
        )
        self.save_txt_cb.grid(row=1, column=0, padx=15, pady=8, sticky="w")

        self.discounted_only_var = tk.BooleanVar(
            value=self.app.udemy.settings.get("discounted_only", False))
        self.discounted_only_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Enroll in 100% Free / Discounted courses only",
            variable=self.discounted_only_var,
            text_color="#E1E1E6",
            font=("Segoe UI", 12),
            border_color="#A0A0A5",
            hover_color="#2ECC71",
            fg_color="#2ECC71"
        )
        self.discounted_only_cb.grid(
            row=2, column=0, padx=15, pady=8, sticky="w")

        self.allow_ssl_fallback_var = tk.BooleanVar(
            value=self.app.udemy.settings.get("allow_insecure_ssl_fallback", False))
        self.allow_ssl_fallback_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Allow insecure SSL fallback (Bypass SSL/TLS handshake errors)",
            variable=self.allow_ssl_fallback_var,
            text_color="#E1E1E6",
            font=("Segoe UI", 12),
            border_color="#A0A0A5",
            hover_color="#2ECC71",
            fg_color="#2ECC71"
        )
        self.allow_ssl_fallback_cb.grid(
            row=3, column=0, padx=15, pady=(8, 15), sticky="w")

    def update_rating_label(self, val):
        self.rating_label_var.set(
            f"Min Rating: {float(val):.1f} / 5.0")

    def update_threshold_label(self, val):
        self.threshold_label_var.set(
            f"Max Age: {int(float(val))} Month(s)")

    def update_timeout_label(self, val):
        self.timeout_label_var.set(
            f"Timeout: {int(float(val))}s")


class AboutPage(ctk.CTkFrame):
    """Page component displaying links, credits, and support icons."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self.header_label = ctk.CTkLabel(
            self,
            text="About Application",
            font=("Segoe UI", 20, "bold"),
            text_color="#FFFFFF",
            anchor="w"
        )
        self.header_label.grid(row=0, column=0, pady=(0, 15), sticky="w")

        # Container
        self.container = ctk.CTkFrame(
            self, fg_color="#1E1E1E", corner_radius=12)
        self.container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.container.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            self.container,
            text="Discounted Udemy Course Enroller (DUCE)",
            font=("Segoe UI", 16, "bold"),
            text_color="#2ECC71"
        )
        title_lbl.grid(row=0, column=0, pady=(35, 10))

        desc_text = (
            "DUCE is a lightweight, background automation tool designed to monitor coupon websites, "
            "scrape courses with active free discounts or coupon codes, and automatically enroll them "
            "into your Udemy account.\n\n"
            "By automating checking, checking criteria, and checkout actions, DUCE helps you expand your "
            "Udemy library with zero manual effort."
        )
        desc_lbl = ctk.CTkLabel(
            self.container,
            text=desc_text,
            font=("Segoe UI", 12),
            text_color="#E1E1E6",
            wraplength=600,
            justify="center"
        )
        desc_lbl.grid(row=1, column=0, padx=40, pady=15)

        # Action Buttons frame
        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=25)
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        github_btn = ctk.CTkButton(
            btn_frame,
            text="Github Repository",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1.5,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=160,
            font=("Segoe UI", 12, "bold"),
            command=lambda: web(LINKS["github"])
        )
        github_btn.grid(row=0, column=0, padx=10)

        discord_btn = ctk.CTkButton(
            btn_frame,
            text="Discord Server",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1.5,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=160,
            font=("Segoe UI", 12, "bold"),
            command=lambda: web(LINKS["discord"])
        )
        discord_btn.grid(row=0, column=1, padx=10)

        support_btn = ctk.CTkButton(
            btn_frame,
            text="Support Creator",
            fg_color="transparent",
            border_color="#2ECC71",
            border_width=1.5,
            text_color="#2ECC71",
            hover_color="#184A2C",
            width=160,
            font=("Segoe UI", 12, "bold"),
            command=lambda: web(LINKS["support"])
        )
        support_btn.grid(row=0, column=2, padx=10)

        footer_lbl = ctk.CTkLabel(
            self.container,
            text="Made with 🩷 by techtanic",
            font=("Segoe UI", 11, "italic"),
            text_color="#A0A0A5"
        )
        footer_lbl.grid(row=3, column=0, pady=(40, 20))


class SidebarFrame(ctk.CTkFrame):
    """Sidebar navigation container."""

    def __init__(self, parent, app):
        super().__init__(parent, width=220, corner_radius=0, fg_color="#151517")
        self.parent = parent
        self.app = app
        self.grid_propagate(False)

        # Logo / Title
        self.logo_lbl = ctk.CTkLabel(
            self,
            text="DUCE ENROLLER",
            font=("Segoe UI", 16, "bold"),
            text_color="#2ECC71"
        )
        self.logo_lbl.grid(row=0, column=0, padx=20, pady=(35, 5), sticky="w")

        self.ver_lbl = ctk.CTkLabel(
            self,
            text=f"Version {VERSION}",
            font=("Segoe UI", 11),
            text_color="#A0A0A5"
        )
        self.ver_lbl.grid(row=1, column=0, padx=20, pady=(0, 25), sticky="w")

        # Sidebar Menu Navigation Buttons
        self.nav_buttons = {}
        pages_def = [
            ("dashboard", "Dashboard"),
            ("settings", "Websites & Tags"),
            ("exclusions", "Exclusions & Limits"),
            ("about", "About DUCE")
        ]

        curr_row = 2
        for page_id, title in pages_def:
            btn = ctk.CTkButton(
                self,
                text=title,
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                text_color="#E1E1E6",
                text_color_disabled="#8E8E93",
                hover_color="#282A30",
                font=("Segoe UI", 12),
                command=lambda p=page_id: self.parent.show_page(p)
            )
            btn.grid(row=curr_row, column=0, padx=15, pady=4, sticky="ew")
            self.nav_buttons[page_id] = btn
            curr_row += 1

        # Spacer
        self.grid_rowconfigure(curr_row, weight=1)
        curr_row += 1

        # User Status Info Frame
        self.user_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.user_frame.grid(row=curr_row, column=0,
                             padx=15, pady=(10, 5), sticky="ew")
        self.user_frame.grid_columnconfigure(0, weight=1)

        self.user_lbl = ctk.CTkLabel(
            self.user_frame,
            text="Logged in as:",
            font=("Segoe UI", 10),
            text_color="#A0A0A5",
            anchor="w"
        )
        self.user_lbl.grid(row=0, column=0, sticky="w")

        self.user_name_lbl = ctk.CTkLabel(
            self.user_frame,
            text=self.app.udemy.display_name,
            font=("Segoe UI", 12, "bold"),
            text_color="#FFFFFF",
            anchor="w",
            wraplength=190
        )
        self.user_name_lbl.grid(row=1, column=0, sticky="w")

        self.total_enrolled_lbl = ctk.CTkLabel(
            self.user_frame,
            text=f"Total Enrolled: {len(self.app.udemy.enrolled_courses)}",
            font=("Segoe UI", 11),
            text_color="#2ECC71",
            anchor="w"
        )
        self.total_enrolled_lbl.grid(row=2, column=0, sticky="w")

        # Logout Button
        self.logout_btn = ctk.CTkButton(
            self,
            text="Logout",
            fg_color="transparent",
            text_color="#FF453A",
            border_color="#FF453A",
            border_width=1,
            height=35,
            corner_radius=8,
            hover_color="#4F1515",
            font=("Segoe UI", 12, "bold"),
            command=self.app.logout
        )
        self.logout_btn.grid(row=curr_row + 1, column=0,
                             padx=15, pady=(5, 25), sticky="ew")

    def disable_navigation(self):
        for btn in self.nav_buttons.values():
            btn.configure(state="disabled")
        self.logout_btn.configure(state="disabled")

    def enable_navigation(self):
        for btn in self.nav_buttons.values():
            btn.configure(state="normal")
        self.logout_btn.configure(state="normal")


class MainFrame(ctk.CTkFrame):
    """Parent container for the authenticated dashboard view."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Sidebar Frame
        self.sidebar = SidebarFrame(self, self.app)
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        # Sub-page container frame
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(
            row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # Initialize Subpages
        self.dashboard_page = DashboardPage(self.content_container, self.app)
        self.settings_page = SettingsPage(self.content_container, self.app)
        self.exclusions_page = ExclusionsPage(self.content_container, self.app)
        self.about_page = AboutPage(self.content_container, self.app)

        self.pages = {
            "dashboard": self.dashboard_page,
            "settings": self.settings_page,
            "exclusions": self.exclusions_page,
            "about": self.about_page
        }

        self.active_page = None
        self.show_page("dashboard")

    def show_page(self, page_id):
        if self.active_page == page_id:
            return

        if self.active_page:
            self.pages[self.active_page].grid_forget()
            self.sidebar.nav_buttons[self.active_page].configure(
                fg_color="transparent",
                text_color="#E1E1E6",
                text_color_disabled="#8E8E93"
            )

        self.pages[page_id].grid(row=0, column=0, sticky="nsew")
        self.sidebar.nav_buttons[page_id].configure(
            fg_color="#2ECC71",
            text_color="#121214",
            text_color_disabled="#121214"
        )
        self.active_page = page_id

        # Reset scroll position and set focus to title to prevent auto-scrolling to the bottom
        self.update_idletasks()
        if hasattr(self.pages[page_id], "scroll_frame"):
            try:
                self.pages[page_id].scroll_frame._canvas.yview_moveto(0)
            except Exception:
                pass
        try:
            self.pages[page_id].header_label.focus_set()
        except Exception:
            pass

    def update_total_enrolled(self, text):
        self.sidebar.total_enrolled_lbl.configure(text=text)

    def update_user_name(self, text):
        self.sidebar.user_name_lbl.configure(text=text)


class App(ctk.CTk):
    """Main Application Controller."""

    def __init__(self, udemy):
        super().__init__()
        self.udemy = udemy

        # Configure Root Window
        self.title(login_title)
        self.geometry("980x680")
        self.minsize(920, 620)

        self.is_running = False
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Center Window
        self.update_idletasks()
        width = 980
        height = 680
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        # Set window icon
        try:
            img = tk.PhotoImage(data=icon)
            self.iconphoto(True, img)
        except Exception as e:
            logger.error(f"Failed to set window icon: {e}")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Event Queue
        self.event_queue = queue.Queue()
        self.check_queue()

        # Initialize views
        self.login_frame = LoginFrame(self, self)
        self.main_frame = None
        self.current_frame = None

        self.show_login_view()

        # Register log sink
        log_level = self.udemy.settings.get("log_level", "INFO")
        self.log_sink_id = logger.add(
            self.gui_log_sink,
            format="{time:HH:mm:ss} | {level:7} | {message}",
            level=log_level
        )

        # Begin startup auto checks
        self.check_startup_login()

    def on_closing(self):
        if getattr(self, "is_running", False):
            from tkinter import messagebox
            if messagebox.askyesno("Exit Confirmation", "A course enrollment process is currently active. Are you sure you want to stop the enroller and exit?"):
                self.udemy.cancelled = True
                try:
                    logger.remove(self.log_sink_id)
                except Exception:
                    pass
                self.destroy()
        else:
            try:
                logger.remove(self.log_sink_id)
            except Exception:
                pass
            self.destroy()

    def show_login_view(self):
        if self.main_frame:
            self.main_frame.grid_forget()
            self.main_frame = None

        self.title(login_title)
        self.login_frame.grid(row=0, column=0, sticky="nsew")
        self.login_frame.enable_buttons()
        self.login_frame.status_label.configure(text="")
        self.current_frame = "login"

    def show_main_view(self):
        self.login_frame.grid_forget()

        self.title(main_title)
        self.main_frame = MainFrame(self, self)
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.current_frame = "main"

        # Start the background task to poll enrolled courses count
        threading.Thread(target=update_enrolled_courses, daemon=True).start()

    def write_event_value(self, event, value):
        self.event_queue.put((event, value))

    def check_queue(self):
        try:
            while True:
                event, value = self.event_queue.get_nowait()
                self.handle_gui_event(event, value)
                self.event_queue.task_done()
        except queue.Empty:
            pass
        self.after(50, self.check_queue)

    def gui_log_sink(self, message):
        try:
            cleaned_msg = message.strip()
            self.write_event_value("Log-Append", cleaned_msg + "\n")
        except Exception:
            pass

    def handle_log_append(self, msg):
        if self.current_frame != "main":
            return

        tb = self.main_frame.dashboard_page.log_textbox
        tb.configure(state="normal")

        for line in msg.splitlines(keepends=True):
            stripped = line.strip()
            if not stripped:
                tb.insert("end", line, "info")
                continue

            parts = line.split(" | ", 2)
            if len(parts) == 3:
                time_part, level_part, msg_part = parts

                # Timestamp
                tb.insert("end", time_part, "timestamp")
                tb.insert("end", " | ", "separator")

                # Level
                lvl_clean = level_part.strip()
                lvl_tag = "info"
                if lvl_clean == "WARNING":
                    lvl_tag = "warning"
                elif lvl_clean in ("ERROR", "CRITICAL", "FAILED"):
                    lvl_tag = "error"
                elif lvl_clean in ("SUCCESS", "INFO"):
                    if lvl_clean == "SUCCESS":
                        lvl_tag = "success"
                tb.insert("end", level_part, lvl_tag)
                tb.insert("end", " | ", "separator")

                # Message Content Highlight
                msg_lower = msg_part.lower()
                msg_tag = "info"

                if "successfully enrolled" in msg_lower or "successfully subscribed" in msg_lower or "enrolled :)" in msg_lower:
                    msg_tag = "success"
                elif "added for enrollment" in msg_lower:
                    msg_tag = "info_highlight"
                elif "expired" in msg_lower or "rate limited" in msg_lower:
                    msg_tag = "warning"
                elif "excluded" in msg_lower or "skipping" in msg_lower:
                    msg_tag = "excluded"
                elif "error" in msg_lower or "failed" in msg_lower:
                    msg_tag = "error"
                elif "processing course" in msg_lower:
                    msg_tag = "info_highlight"

                tb.insert("end", msg_part, msg_tag)
            else:
                line_lower = line.lower()
                tag = "info"
                if "successfully" in line_lower:
                    tag = "success"
                elif "error" in line_lower or "failed" in line_lower:
                    tag = "error"
                elif "warning" in line_lower:
                    tag = "warning"
                elif "excluded" in line_lower:
                    tag = "excluded"
                tb.insert("end", line, tag)

        try:
            total_lines = int(tb.index("end-1c").split(".")[0])
            if total_lines > 1000:
                tb.delete("1.0", f"{total_lines - 1000 + 1}.0")
        except Exception:
            pass

        tb.configure(state="disabled")
        tb.see("end")

    def check_startup_login(self):
        if self.udemy.settings["stay_logged_in"]["auto"]:
            self.login_frame.status_label.configure(
                text="Auto-logging in with cookies, please wait...", text_color="#00F2FE")
            self.login_frame.disable_buttons()

            def run_auto_login():
                def gui_on_locked(browser_name, processes):
                    q = queue.Queue()
                    self.write_event_value(
                        "Prompt-Locked-Browser", (browser_name, processes, q))
                    return q.get()

                def gui_on_select(candidates_names):
                    q = queue.Queue()
                    self.write_event_value(
                        "Prompt-Select-Profile", (candidates_names, q))
                    return q.get()

                try:
                    self.udemy.fetch_cookies(
                        on_locked=gui_on_locked, on_select=gui_on_select)
                    self.udemy.get_session_info()
                    self.write_event_value("Login-Success", "auto")
                except LoginException as e:
                    self.write_event_value("Login-Failed", (str(e), "auto"))
                except Exception:
                    self.write_event_value(
                        "Login-Failed", (traceback.format_exc(), "auto-error"))

            threading.Thread(target=run_auto_login, daemon=True).start()

        elif self.udemy.settings["stay_logged_in"]["manual"]:
            email = self.udemy.settings["email"]
            password = self.udemy.settings["password"]
            if email and password:
                self.login_frame.status_label.configure(
                    text="Auto-logging in manually, please wait...", text_color="#00F2FE")
                self.login_frame.disable_buttons()

                def run_manual_login():
                    try:
                        self.udemy.manual_login(email, password)
                        self.udemy.get_session_info()
                        self.write_event_value("Login-Success", "manual")
                    except LoginException as e:
                        self.write_event_value(
                            "Login-Failed", (str(e), "manual"))
                    except Exception:
                        self.write_event_value(
                            "Login-Failed", (traceback.format_exc(), "manual-error"))

                threading.Thread(target=run_manual_login, daemon=True).start()

    def on_auto_login_click(self, stay_logged_in_val):
        self.login_frame.status_label.configure(
            text="Connecting and extracting browser cookies...", text_color="#00F2FE")
        self.login_frame.disable_buttons()

        def run_user_a_login(sli):
            def gui_on_locked(browser_name, processes):
                q = queue.Queue()
                self.write_event_value(
                    "Prompt-Locked-Browser", (browser_name, processes, q))
                return q.get()

            def gui_on_select(candidates_names):
                q = queue.Queue()
                self.write_event_value(
                    "Prompt-Select-Profile", (candidates_names, q))
                return q.get()

            try:
                self.udemy.fetch_cookies(
                    on_locked=gui_on_locked, on_select=gui_on_select)
                self.udemy.get_session_info()
                self.write_event_value("Login-Success", ("user-auto", sli))
            except LoginException as e:
                self.write_event_value("Login-Failed", (str(e), "user-auto"))
            except Exception:
                self.write_event_value(
                    "Login-Failed", (traceback.format_exc(), "user-auto-error"))

        threading.Thread(target=run_user_a_login, args=(
            stay_logged_in_val,), daemon=True).start()

    def on_manual_login_click(self, email_val, password_val, stay_logged_in_val):
        if not email_val.strip() or not password_val.strip():
            self.login_frame.status_label.configure(
                text="Email and password cannot be empty.",
                text_color="#FF453A"
            )
            return

        self.udemy.settings["email"] = email_val
        self.udemy.settings["password"] = password_val

        self.login_frame.status_label.configure(
            text="Logging in manually...", text_color="#00F2FE")
        self.login_frame.disable_buttons()

        def run_user_m_login(e, p, sli):
            try:
                self.udemy.manual_login(e, p)
                self.udemy.get_session_info()
                self.write_event_value("Login-Success", ("user-manual", sli))
            except LoginException as err:
                self.write_event_value(
                    "Login-Failed", (str(err), "user-manual"))
            except Exception:
                self.write_event_value(
                    "Login-Failed", (traceback.format_exc(), "user-manual-error"))

        threading.Thread(target=run_user_m_login, args=(
            email_val, password_val, stay_logged_in_val), daemon=True).start()

    def handle_gui_event(self, event, value):
        if event == "Login-Success":
            args = value
            if isinstance(args, tuple) and args[0] == "user-auto":
                self.udemy.settings["stay_logged_in"]["auto"] = args[1]
                self.udemy.settings["stay_logged_in"]["manual"] = False
                self.udemy.save_settings()
            elif isinstance(args, tuple) and args[0] == "user-manual":
                self.udemy.settings["stay_logged_in"]["manual"] = args[1]
                self.udemy.settings["stay_logged_in"]["auto"] = False
                self.udemy.save_settings()
            elif args == "auto":
                self.udemy.settings["stay_logged_in"]["auto"] = True
                self.udemy.settings["stay_logged_in"]["manual"] = False
                self.udemy.save_settings()
            elif args == "manual":
                self.udemy.settings["stay_logged_in"]["manual"] = True
                self.udemy.settings["stay_logged_in"]["auto"] = False
                self.udemy.save_settings()

            self.show_main_view()

        elif event == "Login-Failed":
            err_msg, src = value
            logger.warning(f"Login failed from {src}: {err_msg}")
            self.login_frame.enable_buttons()

            if src in ("auto", "manual"):
                self.login_frame.status_label.configure(
                    text=f"Auto-login failed: {err_msg}",
                    text_color="#FF453A"
                )
            else:
                self.login_frame.status_label.configure(
                    text="", text_color="#A0A0A5")

            if src in ("auto", "manual"):
                pass
            elif src == "user-auto":
                cookies_path = get_user_data_path("cookies.json")
                if not os.path.exists(cookies_path):
                    template = [
                        {
                            "domain": ".udemy.com",
                            "name": "access_token",
                            "value": "PASTE_ACCESS_TOKEN_HERE",
                            "path": "/"
                        },
                        {
                            "domain": ".udemy.com",
                            "name": "client_id",
                            "value": "PASTE_CLIENT_ID_HERE",
                            "path": "/"
                        }
                    ]
                    try:
                        import json
                        with open(cookies_path, "w", encoding="utf-8") as f:
                            json.dump(template, f, indent=4)
                    except Exception as file_err:
                        logger.error(
                            f"Failed to create cookies.json template: {file_err}")
                self.show_cookie_instructions(cookies_path)
            elif src == "user-manual":
                self.show_error_popup(err_msg, "Login Error")
            else:
                self.show_error_popup(err_msg, f"Unknown Error {VERSION}")

        elif event == "Error":
            msg = value.split("|:|")
            error_text = msg[0]
            title = msg[1]
            logger.exception(f"GUI Error Popup: {title} - {error_text}")
            self.show_error_popup(error_text, title)

        elif event == "Log-Append":
            self.handle_log_append(value)

        elif event == "Prompt-Locked-Browser":
            browser_name, processes, response_queue = value
            from tkinter import messagebox
            choice = messagebox.askyesno(
                "Browser Locked",
                f"Browser '{browser_name}' is currently open and locking its database.\n\n"
                f"Would you like to force close '{browser_name}' to continue?",
                parent=self
            )
            response_queue.put(choice)

        elif event == "Prompt-Select-Profile":
            candidates_names, response_queue = value
            ProfileSelectionDialog(self, candidates_names, response_queue)

        elif event == "Update-Element":
            key, args, kwargs = value
            self.handle_update_element(key, *args, **kwargs)

    def handle_update_element(self, key, *args, **kwargs):
        if self.current_frame != "main":
            return

        if key == "total_enrolled_t":
            val = args[0] if args else kwargs.get("value", "")
            self.main_frame.update_total_enrolled(val)
        elif key == "user_t":
            val = args[0] if args else kwargs.get("value", "")
            self.main_frame.update_user_name(val)
        elif key.startswith("pcol"):
            site = key[4:]
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_site_row_visibility(
                site, visible)
        elif key.startswith("p") and key[1:] in self.udemy.settings["sites"]:
            site = key[1:]
            val = args[0] if args else kwargs.get("value", 0)
            max_val = kwargs.get("max", None)
            visible = kwargs.get("visible", None)
            self.main_frame.dashboard_page.update_site_progress(
                site, val, max_val, visible)
        elif key.startswith("i") and key[1:] in self.udemy.settings["sites"]:
            site = key[1:]
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_site_done(site, visible)
        elif key == "main_col":
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_main_col_visible(visible)
        elif key == "scrape_col":
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_scrape_col_visible(visible)
        elif key == "output_col":
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_output_col_visible(visible)
        elif key in ["enrollment_panel", "stats_panel", "current_course_panel"]:
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_enrollment_panel_visible(
                visible)
        elif key == "done_col":
            visible = kwargs.get("visible", True)
            self.main_frame.dashboard_page.set_done_col_visible(visible)
            if visible:
                self.is_running = False
                self.main_frame.sidebar.enable_navigation()
        elif key == "current_course_title":
            val = kwargs.get("value", args[0] if args else "")
            self.main_frame.dashboard_page.update_course_title(val)
        elif key == "current_course_status":
            val = kwargs.get("value", args[0] if args else "")
            color = kwargs.get("color", "#00F2FE")
            self.main_frame.dashboard_page.update_course_status(val, color)
        elif key == "current_course_url":
            val = kwargs.get("value", args[0] if args else "")
            self.main_frame.dashboard_page.update_course_url(val)
        elif key == "course_progress":
            val = kwargs.get("value", args[0] if args else "")
            self.main_frame.dashboard_page.update_course_progress(val)
        elif key.startswith("stat_"):
            stat_name = key[5:]
            val = kwargs.get("value", args[0] if args else "")
            self.main_frame.dashboard_page.update_stat(stat_name, val)
        elif key in ["se_c", "as_c", "ae_c", "e_c", "ex_c"]:
            val = kwargs.get("value", args[0] if args else "")
            self.main_frame.dashboard_page.update_done_stat(key, val)

    def get_gui_values(self):
        values = {}
        # Websites
        for site, var in self.main_frame.settings_page.site_vars.items():
            values[site] = var.get()
        # Languages
        for lang, var in self.main_frame.settings_page.lang_vars.items():
            values[lang] = var.get()
        # Categories
        for cat, var in self.main_frame.settings_page.cat_vars.items():
            values[cat] = var.get()

        # Exclusions Page Text inputs & options
        values["instructor_exclude"] = self.main_frame.exclusions_page.instructor_exclude_box.get(
            "1.0", "end-1c")
        values["title_exclude"] = self.main_frame.exclusions_page.title_exclude_box.get(
            "1.0", "end-1c")
        values["min_rating"] = self.main_frame.exclusions_page.min_rating_slider.get()
        values["course_update_threshold_months"] = int(
            self.main_frame.exclusions_page.threshold_slider.get())
        values["network_timeout"] = int(
            self.main_frame.exclusions_page.timeout_slider.get())
        values["save_txt"] = self.main_frame.exclusions_page.save_txt_var.get()
        values["discounted_only"] = self.main_frame.exclusions_page.discounted_only_var.get()
        values["allow_insecure_ssl_fallback"] = self.main_frame.exclusions_page.allow_ssl_fallback_var.get()
        return values

    def start_process(self):
        self.is_running = True
        self.udemy.cancelled = False
        if self.main_frame and hasattr(self.main_frame.dashboard_page, "stop_btn"):
            self.main_frame.dashboard_page.stop_btn.configure(
                text="Stop Enroller", state="normal")

        values = self.get_gui_values()

        for setting in ["languages", "categories", "sites"]:
            for key in self.udemy.settings[setting]:
                self.udemy.settings[setting][key] = values[key]

        self.udemy.settings["instructor_exclude"] = str(
            values["instructor_exclude"]).split()
        self.udemy.settings["title_exclude"] = list(
            filter(None, values["title_exclude"].split("\n"))
        )
        self.udemy.settings["min_rating"] = float(values["min_rating"])
        self.udemy.settings["course_update_threshold_months"] = int(
            values["course_update_threshold_months"]
        )
        self.udemy.settings["network_timeout"] = int(values["network_timeout"])
        self.udemy.settings["save_txt"] = values["save_txt"]
        self.udemy.settings["discounted_only"] = values["discounted_only"]
        self.udemy.settings["allow_insecure_ssl_fallback"] = values["allow_insecure_ssl_fallback"]
        self.udemy.save_settings()

        settings_invalid = self.udemy.validate_settings()
        if settings_invalid:
            self.is_running = False
            self.show_error_popup(
                "Please select at least one site, language, and category.", "Validation Error")
            return

        global scraper
        scraper = Scraper(self.udemy.sites)
        self.udemy.window = main_window

        self.main_frame.dashboard_page.set_running_state()
        self.main_frame.sidebar.disable_navigation()

        threading.Thread(target=scrape, daemon=True).start()

    def cancel_process(self):
        self.is_running = False
        self.udemy.cancelled = True
        if self.main_frame and hasattr(self.main_frame.dashboard_page, "stop_btn"):
            self.main_frame.dashboard_page.stop_btn.configure(
                text="Stopping...", state="disabled")

    def reset_gui(self):
        self.is_running = False
        self.udemy.cancelled = False
        if self.main_frame:
            self.main_frame.sidebar.enable_navigation()
            if hasattr(self.main_frame.dashboard_page, "stop_btn"):
                self.main_frame.dashboard_page.stop_btn.configure(
                    text="Stop Enroller", state="normal")
        self.main_frame.dashboard_page.reset_to_start()

        from decimal import Decimal
        self.udemy.successfully_enrolled_c = 0
        self.udemy.already_enrolled_c = 0
        self.udemy.expired_c = 0
        self.udemy.excluded_c = 0
        self.udemy.amount_saved_c = Decimal(0)

    def logout(self):
        self.udemy.settings["stay_logged_in"]["auto"] = False
        self.udemy.settings["stay_logged_in"]["manual"] = False
        self.udemy.save_settings()

        self.show_login_view()

    def show_cookie_instructions(self, cookies_path):
        CookieInstructionsDialog(self, cookies_path)

    def show_error_popup(self, message, title="Error"):
        ErrorPopupDialog(self, message, title)


def update_enrolled_courses():
    while True:
        try:
            logger.debug(
                f"Enrolled courses count: {len(udemy.enrolled_courses)}")
            safe_update("total_enrolled_t",
                        f"Total Enrolled: {len(udemy.enrolled_courses)}")
        except Exception as e:
            logger.error(f"Error in update_enrolled_courses: {e}")
        time.sleep(10)


def safe_update(key, *args, **kwargs):
    """Thread-safe update helper for GUI elements using CustomTkinter event queue."""
    try:
        main_window.write_event_value("Update-Element", (key, args, kwargs))
    except Exception as e:
        logger.error(f"Failed to write event value for safe update: {e}")


def create_scraping_thread(site: str):
    if getattr(udemy, "cancelled", False):
        return

    logger.info(f"Launching scraping thread for site: {site}")
    code_name = scraper_dict[site]
    safe_update(f"i{site}", visible=False)
    safe_update(f"p{site}", 0, visible=True)

    try:
        threading.Thread(target=getattr(
            scraper, code_name), daemon=True).start()
        while getattr(scraper, f"{code_name}_length") == 0 and not getattr(
            scraper, f"{code_name}_done"
        ) and not getattr(scraper, f"{code_name}_error"):
            if getattr(udemy, "cancelled", False):
                raise Exception("Process cancelled by user")
            time.sleep(0.1)
        if getattr(scraper, f"{code_name}_length") == -1:
            raise Exception(f"Error in: {site}")
        safe_update(f"p{site}", 0, max=getattr(scraper, f"{code_name}_length"))
        while not getattr(scraper, f"{code_name}_done") and not getattr(
            scraper, f"{code_name}_error"
        ):
            if getattr(udemy, "cancelled", False):
                raise Exception("Process cancelled by user")
            safe_update(
                f"p{site}",
                getattr(scraper, f"{code_name}_progress") + 1,
                max=getattr(scraper, f"{code_name}_length"),
            )
            time.sleep(0.1)
        logger.info(
            f"Courses Found {code_name}: {len(getattr(scraper, f'{code_name}_data'))}"
        )
        if getattr(scraper, f"{code_name}_error"):
            raise Exception(f"Error in: {site}")
    except Exception as e:
        if "Process cancelled by user" in str(e):
            raise e
        error_message = getattr(scraper, f"{code_name}_error", "Unknown Error")
        logger.exception(f"Error in {site}: {error_message}")
        main_window.write_event_value(
            "Error", f"{error_message}|:|Unknown Error in: {site} {VERSION}"
        )
    finally:
        safe_update(f"p{site}", 0, visible=False)
        safe_update(f"i{site}", visible=True)


def scrape():
    try:
        for site in udemy.sites:
            safe_update(f"pcol{site}", visible=True)
        safe_update("main_col", visible=False)
        safe_update("scrape_col", visible=True)
        safe_update("output_col", visible=True)
        udemy.scraped_data = scraper.get_scraped_courses(
            create_scraping_thread)
        safe_update("scrape_col", visible=False)

        if getattr(udemy, "cancelled", False):
            raise Exception("Process cancelled by user")

        safe_update("enrollment_panel", visible=True)
        safe_update("stats_panel", visible=True)
        safe_update("current_course_panel", visible=True)

        total_courses = len(udemy.scraped_data)

        def update_progress():
            if getattr(udemy, "cancelled", False):
                raise Exception("Process cancelled by user")

            if hasattr(udemy, "course") and udemy.course:
                safe_update("current_course_title", value=udemy.course.title)
                safe_update("current_course_url", value=udemy.course.url)
                status_text = getattr(udemy.course, "status_text", "")
                status_color = getattr(udemy.course, "status_color", "#00F2FE")
                safe_update("current_course_status", value=status_text, color=status_color)

            if hasattr(udemy, "total_courses_processed"):
                progress_text = (
                    f"Course {udemy.total_courses_processed:4d}/{total_courses:4d}"
                )
                safe_update("course_progress", value=progress_text)

            safe_update("stat_enrolled",
                        value=f"{udemy.successfully_enrolled_c}")
            safe_update("stat_amount_saved",
                        value=f"{round(udemy.amount_saved_c, 2)} {udemy.currency.upper()}")
            safe_update("stat_already", value=f"{udemy.already_enrolled_c}")
            safe_update("stat_excluded", value=f"{udemy.excluded_c}")
            safe_update("stat_expired", value=f"{udemy.expired_c}")

            ready_count = len(getattr(udemy, "valid_courses", []))
            safe_update("stat_ready_enroll", value=f"{ready_count}/5")

        udemy.update_progress = update_progress
        udemy.total_courses_processed = 0

        if getattr(udemy, "cancelled", False):
            raise Exception("Process cancelled by user")

        udemy.start_new_enroll()

        safe_update("enrollment_panel", visible=False)
        safe_update("done_col", visible=True)

        safe_update(
            "se_c", value=f"Successfully Enrolled: {udemy.successfully_enrolled_c}")
        safe_update(
            "as_c",
            value=f"Amount Saved: {round(udemy.amount_saved_c, 2)} {udemy.currency.upper()}"
        )
        safe_update(
            "ae_c", value=f"Already Enrolled: {udemy.already_enrolled_c}")
        safe_update("e_c", value=f"Expired Courses: {udemy.expired_c}")
        safe_update("ex_c", value=f"Excluded Courses: {udemy.excluded_c}")

    except Exception as err:
        if "Process cancelled by user" in str(err):
            logger.info(
                "Scraping/enrollment process was cancelled by the user.")
            safe_update("enrollment_panel", visible=False)
            safe_update("scrape_col", visible=False)
            safe_update("done_col", visible=True)

            safe_update(
                "se_c", value=f"Successfully Enrolled: {udemy.successfully_enrolled_c}")
            safe_update(
                "as_c",
                value=f"Amount Saved: {round(udemy.amount_saved_c, 2)} {udemy.currency.upper()}"
            )
            safe_update(
                "ae_c", value=f"Already Enrolled: {udemy.already_enrolled_c}")
            safe_update("e_c", value=f"Expired Courses: {udemy.expired_c}")
            safe_update("ex_c", value=f"Excluded Courses: {udemy.excluded_c}")
        else:
            e = traceback.format_exc()
            logger.exception(
                f"Error during scraping/enrollment: {e}\nCourse: {str(udemy.course)}"
            )
            main_window.write_event_value(
                "Error",
                e + f"\n\n{str(udemy.course)}" + f"|:|Error {VERSION}",
            )


# Global instances
udemy = Udemy("gui")
logger.info("Starting CustomTkinter GUI application")
udemy.load_settings()
login_title, main_title = udemy.check_for_update()

global main_window

if __name__ == "__main__":
    app = App(udemy)
    main_window = MainWindowAdapter(app)
    app.mainloop()
