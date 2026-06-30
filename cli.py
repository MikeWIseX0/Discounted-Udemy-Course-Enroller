from base import VERSION, LoginException, Scraper, Udemy, scraper_dict, logger, get_user_data_path
from rich import box
from rich.text import Text
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.panel import Panel
from rich.live import Live
from rich.console import Console
import traceback
import time
import threading
import sys
import os


def verify_dependencies():
    required = {
        "cryptography": "cryptography",
        "curl_cffi": "curl-cffi",
        "requests": "requests",
        "loguru": "loguru",
        "rich": "rich"
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


def center_console_window():
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)
                ]
            rect = RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            screen_width = ctypes.windll.user32.GetSystemMetrics(0)
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)
            
            x = (screen_width // 2) - (width // 2)
            y = (screen_height // 2) - (height // 2)
            
            ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)
    except Exception:
        pass


center_console_window()

console = Console()
udemy = None
scraper = None
INTERACTIVE = True


def cli_on_locked(browser_name, processes):
    if not INTERACTIVE:
        logger.warning(
            f"Browser '{browser_name}' is locked. Forcing close in non-interactive mode.")
        return True
    from rich.prompt import Confirm
    console.print(
        f"\n[bold yellow]Browser '{browser_name}' is currently open and locking its database.[/bold yellow]")
    choice = Confirm.ask(
        f"Would you like to force close '{browser_name}' to continue?", default=False)
    return choice


def cli_on_select(candidates_names):
    if not INTERACTIVE:
        logger.info("Automatically selecting first cookie profile in non-interactive mode.")
        return 0
    from rich.prompt import Prompt
    console.print(
        "\n[bold cyan]Multiple profiles containing Udemy cookies were found:[/bold cyan]")
    for idx, name in enumerate(candidates_names):
        console.print(f"  [[bold green]{idx}[/bold green]] {name}")
    choice = Prompt.ask(
        "Please select which profile to load cookies from",
        choices=[str(i) for i in range(len(candidates_names))],
        default="0"
    )
    return int(choice)


def handle_error(error_message, error=None, exit_program=True):
    """Handle errors consistently throughout the application."""
    logger.error(f"ERROR: {error_message}")
    console.print(
        f"\n[bold white on red] ERROR [/bold white on red] [bold red]{error_message}[/bold red]"
    )

    if error:
        error_details = str(error)
        trace = traceback.format_exc()
        console.print(f"[red]Details: {error_details}[/red]")
        console.print("[yellow]Full traceback:[/yellow]")
        console.print(Panel(trace, border_style="red"))
        logger.exception(f"{error_message} - Details: {error_details}")

    if exit_program:
        sys.exit(1)


def create_unified_live_panel(udemy_obj: Udemy, total_courses: int) -> Panel:
    """Create a unified panel showing stats, current course, and progress."""
    # Stats section
    stats_table = Table.grid(padding=(0, 2))
    stats_table.add_column(style="cyan", justify="right", width=22)
    stats_table.add_column(style="white", justify="left", width=12)
    stats_table.add_column(style="cyan", justify="right", width=18)
    stats_table.add_column(style="white", justify="left", width=12)
    stats_table.add_column(style="cyan", justify="right", width=18)
    stats_table.add_column(style="white", justify="left", width=12)

    stats_table.add_row(
        "Successfully Enrolled:", f"[green]{udemy_obj.successfully_enrolled_c}[/green]",
        "Already Enrolled:", f"[cyan]{udemy_obj.already_enrolled_c}[/cyan]",
        "Expired/Invalid:", f"[red]{udemy_obj.expired_c}[/red]"
    )
    stats_table.add_row(
        "Total Amount Saved:", f"[green]{round(udemy_obj.amount_saved_c, 2)} {udemy_obj.currency.upper()}[/green]",
        "Excluded Courses:", f"[yellow]{udemy_obj.excluded_c}[/yellow]",
        "Pending Enrollment:", f"[orange1]{len(getattr(udemy_obj, 'valid_courses', []))}/5[/orange1]"
    )

    # Current Course section
    if hasattr(udemy_obj, "course") and udemy_obj.course:
        title = udemy_obj.course.title
        url = udemy_obj.course.url
        progress = f"Course {udemy_obj.total_courses_processed} / {total_courses}"
    else:
        title = "Scraping completed, starting checkout..."
        url = "N/A"
        progress = "Waiting..."

    course_table = Table(box=None, show_header=False,
                         show_edge=False, padding=(0, 2))
    course_table.add_column("", style="cyan", justify="right", width=10)
    course_table.add_column("", style="white", justify="left")

    course_table.add_row("Title:", Text(title, style="white", overflow="fold"))
    course_table.add_row("URL:", Text(
        url, style="bright_blue", overflow="fold"))
    course_table.add_row("Progress:", Text(progress, style="yellow"))

    # Consolidated content layout
    content_grid = Table.grid(padding=1)
    content_grid.add_row("[bold yellow]📊 ENROLLMENT STATISTICS[/bold yellow]")
    content_grid.add_row(stats_table)
    content_grid.add_row(
        "[dim]──────────────────────────────────────────────────────────────────────────[/dim]")
    content_grid.add_row(
        "[bold yellow]📚 CURRENT COURSE PROCESSING[/bold yellow]")
    content_grid.add_row(course_table)

    return Panel(
        content_grid,
        title=f"[bold green]DUCE Course Enroller {VERSION}[/bold green]",
        border_style="green",
        padding=(1, 2)
    )


def create_scraping_thread(site: str):
    code_name = scraper_dict[site]
    task_id = udemy.progress.add_task(site, total=100)
    try:
        threading.Thread(target=getattr(
            scraper, code_name), daemon=True).start()
        while getattr(scraper, f"{code_name}_length") == 0 and not getattr(
            scraper, f"{code_name}_done"
        ) and not getattr(scraper, f"{code_name}_error"):
            time.sleep(0.1)
        if getattr(scraper, f"{code_name}_length") == -1:
            raise Exception(f"Error in: {site}")

        udemy.progress.update(task_id, total=getattr(
            scraper, f"{code_name}_length"))

        while not getattr(scraper, f"{code_name}_done") and not getattr(
            scraper, f"{code_name}_error"
        ):
            current = getattr(scraper, f"{code_name}_progress")
            udemy.progress.update(
                task_id,
                completed=current,
                total=getattr(scraper, f"{code_name}_length"),
            )
            time.sleep(0.1)

        udemy.progress.update(
            task_id, completed=getattr(scraper, f"{code_name}_length")
        )
        logger.debug(
            f"Courses Found {code_name}: {len(getattr(scraper, f'{code_name}_data'))}"
        )

        if getattr(scraper, f"{code_name}_error"):
            raise Exception(f"Error in: {site}")
    except Exception:
        error = getattr(scraper, f"{code_name}_error", traceback.format_exc())
        handle_error(f"Error in {site}", error=error, exit_program=False)


def toggle_websites_menu(udemy_obj: Udemy):
    while True:
        console.clear()
        table = Table(
            title="[bold yellow]Toggle Scraping Websites[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Website", style="white")
        table.add_column("Status", style="yellow")

        sites = list(udemy_obj.settings["sites"].keys())
        for idx, site in enumerate(sites, 1):
            status = "[green]Enabled[/green]" if udemy_obj.settings["sites"][site] else "[red]Disabled[/red]"
            table.add_row(str(idx), site, status)

        console.print(table)
        console.print(
            "\nType a number to toggle, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(sites):
                site_name = sites[choice_idx]
                udemy_obj.settings["sites"][site_name] = not udemy_obj.settings["sites"][site_name]
                udemy_obj.save_settings()
        except ValueError:
            pass


def toggle_categories_menu(udemy_obj: Udemy):
    while True:
        console.clear()
        categories = list(udemy_obj.settings["categories"].keys())
        table = Table(
            title="[bold yellow]Toggle Course Categories[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Category", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Category", style="white")
        table.add_column("Status", style="yellow")

        for idx in range(0, len(categories), 2):
            c1 = categories[idx]
            status1 = "[green]Enabled[/green]" if udemy_obj.settings["categories"][c1] else "[red]Disabled[/red]"
            row = [str(idx + 1), c1, status1]
            if idx + 1 < len(categories):
                c2 = categories[idx + 1]
                status2 = "[green]Enabled[/green]" if udemy_obj.settings["categories"][c2] else "[red]Disabled[/red]"
                row.extend([str(idx + 2), c2, status2])
            else:
                row.extend(["", "", ""])
            table.add_row(*row)

        console.print(table)
        console.print(
            "\nType a number to toggle, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(categories):
                cat_name = categories[choice_idx]
                udemy_obj.settings["categories"][cat_name] = not udemy_obj.settings["categories"][cat_name]
                udemy_obj.save_settings()
        except ValueError:
            pass


def toggle_languages_menu(udemy_obj: Udemy):
    while True:
        console.clear()
        languages = list(udemy_obj.settings["languages"].keys())
        table = Table(
            title="[bold yellow]Toggle Course Languages[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Language", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Language", style="white")
        table.add_column("Status", style="yellow")

        for idx in range(0, len(languages), 2):
            l1 = languages[idx]
            status1 = "[green]Enabled[/green]" if udemy_obj.settings["languages"][l1] else "[red]Disabled[/red]"
            row = [str(idx + 1), l1, status1]
            if idx + 1 < len(languages):
                l2 = languages[idx + 1]
                status2 = "[green]Enabled[/green]" if udemy_obj.settings["languages"][l2] else "[red]Disabled[/red]"
                row.extend([str(idx + 2), l2, status2])
            else:
                row.extend(["", "", ""])
            table.add_row(*row)

        console.print(table)
        console.print(
            "\nType a number to toggle, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(languages):
                lang_name = languages[choice_idx]
                udemy_obj.settings["languages"][lang_name] = not udemy_obj.settings["languages"][lang_name]
                udemy_obj.save_settings()
        except ValueError:
            pass


def edit_other_settings(udemy_obj: Udemy):
    while True:
        console.clear()
        table = Table(
            title="[bold yellow]Configure Exclusions & Thresholds[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Setting", style="white")
        table.add_column("Current Value", style="yellow")

        table.add_row("1", "Minimum Course Rating", str(
            udemy_obj.settings.get("min_rating", 0.0)))
        table.add_row("2", "Course Age Limit (Months)", str(
            udemy_obj.settings.get("course_update_threshold_months", 24)))
        table.add_row("3", "Enrol in Discounted Courses Only",
                      "Yes" if udemy_obj.settings.get("discounted_only", False) else "No")
        table.add_row("4", "Save Enrolled Courses to TXT Log",
                      "Yes" if udemy_obj.settings.get("save_txt", True) else "No")
        table.add_row("5", "Excluded Instructors (List)", ", ".join(
            udemy_obj.settings.get("instructor_exclude", [])) or "None")
        table.add_row("6", "Excluded Title Keywords (List)", ", ".join(
            udemy_obj.settings.get("title_exclude", [])) or "None")

        console.print(table)
        console.print(
            "\nSelect a setting number to edit, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break

        if choice == "1":
            val = console.input(
                "[cyan]Enter Minimum Rating (0.0 to 5.0): [/cyan]").strip()
            try:
                rating = float(val)
                if 0.0 <= rating <= 5.0:
                    udemy_obj.settings["min_rating"] = rating
                    udemy_obj.save_settings()
            except ValueError:
                pass
        elif choice == "2":
            val = console.input(
                "[cyan]Enter Course Age Limit in Months (1-48): [/cyan]").strip()
            try:
                months = int(val)
                if 1 <= months <= 48:
                    udemy_obj.settings["course_update_threshold_months"] = months
                    udemy_obj.save_settings()
            except ValueError:
                pass
        elif choice == "3":
            udemy_obj.settings["discounted_only"] = not udemy_obj.settings.get(
                "discounted_only", False)
            udemy_obj.save_settings()
        elif choice == "4":
            udemy_obj.settings["save_txt"] = not udemy_obj.settings.get(
                "save_txt", True)
            udemy_obj.save_settings()
        elif choice == "5":
            val = console.input(
                "[cyan]Enter excluded instructors (separated by space): [/cyan]").strip()
            udemy_obj.settings["instructor_exclude"] = val.split()
            udemy_obj.save_settings()
        elif choice == "6":
            val = console.input(
                "[cyan]Enter excluded title keywords (separated by comma): [/cyan]").strip()
            udemy_obj.settings["title_exclude"] = [k.strip()
                                                   for k in val.split(",") if k.strip()]
            udemy_obj.save_settings()


def edit_settings_menu(udemy_obj: Udemy):
    while True:
        console.clear()
        table = Table(
            title="[bold yellow]⚙️ DUCE Settings Manager[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Settings Category", style="white")
        table.add_column("Status / Description", style="yellow")

        active_sites = sum(1 for v in udemy_obj.settings.get(
            "sites", {}).values() if v)
        total_sites = len(udemy_obj.settings.get("sites", {}))
        active_cats = sum(1 for v in udemy_obj.settings.get(
            "categories", {}).values() if v)
        total_cats = len(udemy_obj.settings.get("categories", {}))
        active_langs = sum(1 for v in udemy_obj.settings.get(
            "languages", {}).values() if v)
        total_langs = len(udemy_obj.settings.get("languages", {}))

        table.add_row("1", "Scraping Websites",
                      f"{active_sites}/{total_sites} Active")
        table.add_row("2", "Course Categories",
                      f"{active_cats}/{total_cats} Active")
        table.add_row("3", "Course Languages",
                      f"{active_langs}/{total_langs} Active")
        table.add_row("4", "Ratings & Exclusions",
                      "Exclusion lists, rating, age limit...")

        console.print(table)
        console.print(
            "\nSelect an option to configure, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break

        if choice == "1":
            toggle_websites_menu(udemy_obj)
        elif choice == "2":
            toggle_categories_menu(udemy_obj)
        elif choice == "3":
            toggle_languages_menu(udemy_obj)
        elif choice == "4":
            edit_other_settings(udemy_obj)


def test_connection(udemy_obj: Udemy):
    console.print("\n[cyan]Attempting login connection test...[/cyan]")
    try:
        if udemy_obj.settings["use_browser_cookies"]:
            with console.status("[cyan]Reading browser cookies...[/cyan]"):
                udemy_obj.fetch_cookies(
                    on_locked=cli_on_locked, on_select=cli_on_select)
        else:
            email = udemy_obj.settings.get("email", "")
            password = udemy_obj.settings.get("password", "")
            if not email or not password:
                console.print(
                    "[bold red]Error: Email and password not configured![/bold red]")
                console.input("\nPress Enter to continue...")
                return
            with console.status("[cyan]Connecting using email/password...[/cyan]"):
                udemy_obj.manual_login(email, password)

        with console.status("[cyan]Verifying session context...[/cyan]"):
            udemy_obj.get_session_info()
        console.print(
            f"[bold green]Success![/bold green] Connected to Udemy as: [bold yellow]{udemy_obj.display_name}[/bold yellow] (Currency: {udemy_obj.currency})")
    except Exception as e:
        console.print(
            f"[bold red]Login Connection Test Failed![/bold red]\nError: {e}")
    console.input("\nPress Enter to continue...")


def configure_login_menu(udemy_obj: Udemy):
    while True:
        console.clear()
        table = Table(
            title="[bold yellow]Manage Account & Login[/bold yellow]", box=box.ROUNDED)
        table.add_column("No.", style="cyan", justify="right")
        table.add_column("Configuration", style="white")
        table.add_column("Current Status / Value", style="yellow")

        login_mode = "Browser Cookies" if udemy_obj.settings.get(
            "use_browser_cookies", False) else "Email / Password Credentials"
        email_val = udemy_obj.settings.get("email", "") or "Not Configured"
        pass_configured = "********" if udemy_obj.settings.get(
            "password", "") else "Not Configured"

        table.add_row("1", "Login Authentication Method", login_mode)
        table.add_row("2", "Email Address", email_val)
        table.add_row("3", "Password", pass_configured)
        table.add_row("4", "⚡ Test Login Connection",
                      "[cyan]Select this option to test login state[/cyan]")

        console.print(table)
        console.print(
            "\nSelect an option to edit, or press [bold cyan]Enter[/bold cyan] to go back.")
        choice = console.input("[cyan]Choice: [/cyan]").strip()
        if not choice:
            break

        if choice == "1":
            udemy_obj.settings["use_browser_cookies"] = not udemy_obj.settings.get(
                "use_browser_cookies", False)
            udemy_obj.save_settings()
        elif choice == "2":
            email = console.input("[cyan]Enter Email: [/cyan]").strip()
            udemy_obj.settings["email"] = email
            udemy_obj.save_settings()
        elif choice == "3":
            password = console.input(
                "[cyan]Enter Password: [/cyan]", password=True).strip()
            udemy_obj.settings["password"] = password
            udemy_obj.save_settings()
        elif choice == "4":
            test_connection(udemy_obj)


def view_history_menu(udemy_obj: Udemy):
    console.clear()
    from duce.core.db import db
    courses = db.get_enrolled_courses()

    if not courses:
        console.print(Panel(
            "[bold yellow]No enrollment history found in local database cache.[/bold yellow]\nRun the course enroller to populate history.", title="Enrollment History"))
        console.input("\nPress Enter to go back...")
        return

    table = Table(
        title=f"[bold yellow]Subscribed/Enrolled Courses ({len(courses)} total)[/bold yellow]", box=box.ROUNDED)
    table.add_column("No.", style="cyan", justify="right")
    table.add_column("Course Slug (URL Name)", style="white")
    table.add_column("Subscribed Time (UTC)", style="yellow")

    sorted_courses = sorted(courses.items(), key=lambda x: x[1], reverse=True)
    limit = min(len(sorted_courses), 50)
    for idx in range(limit):
        slug, enroll_time = sorted_courses[idx]
        table.add_row(str(idx + 1), slug, enroll_time)

    console.print(table)
    if len(sorted_courses) > 50:
        console.print(
            f"[dim](Showing top 50 most recent out of {len(sorted_courses)} courses)[/dim]")
    console.input("\nPress Enter to go back...")


def run_course_enroller_process(udemy_obj: Udemy, interactive=True):
    global scraper
    if interactive:
        console.clear()
    settings_invalid = udemy_obj.validate_settings()
    if settings_invalid:
        console.print("[bold red]Invalid settings configuration.[/bold red]")
        console.print(
            "[yellow]You must select at least one site, language, and category in the settings.[/yellow]")
        if interactive:
            console.input("\nPress Enter to go back...")
        return

    scraper = Scraper(udemy_obj.sites)

    console.print(
        "\n[bold cyan]Scraping courses from selected sites...[/bold cyan]")
    logger.info("Scraping courses from selected sites")

    udemy_obj.progress = Progress(
        SpinnerColumn(finished_text="🟢"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:.0f}%"),
        TimeRemainingColumn(elapsed_when_finished=True),
    )

    with udemy_obj.progress:
        udemy_obj.scraped_data = scraper.get_scraped_courses(
            create_scraping_thread)

    total_courses = len(udemy_obj.scraped_data)
    console.print(f"[green]Found {total_courses} courses to process[/green]")
    time.sleep(1)

    panel = create_unified_live_panel(udemy_obj, total_courses)
    udemy_obj.total_courses_processed = 0
    udemy_obj.total_courses = total_courses

    from decimal import Decimal
    udemy_obj.successfully_enrolled_c = 0
    udemy_obj.already_enrolled_c = 0
    udemy_obj.expired_c = 0
    udemy_obj.excluded_c = 0
    udemy_obj.amount_saved_c = Decimal(0)
    udemy_obj.valid_courses = []

    with Live(panel, screen=False, transient=True) as live:
        def update_progress():
            live.update(create_unified_live_panel(udemy_obj, total_courses))

        udemy_obj.update_progress = update_progress

        try:
            udemy_obj.start_new_enroll()
        except KeyboardInterrupt:
            console.print(
                "\n[bold yellow]Process interrupted by user[/bold yellow]")
        except Exception as e:
            handle_error(
                "An unexpected error occurred during enroller run", error=e, exit_program=False)

    console.print(
        Panel.fit("[bold blue]Enrollment Results[/bold blue]", border_style="cyan"))

    table = Table(box=box.ROUNDED)
    table.add_column("Stat", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Successfully Enrolled",
                  f"[green]{udemy_obj.successfully_enrolled_c}[/green]")
    table.add_row(
        "Amount Saved", f"[green]{round(udemy_obj.amount_saved_c, 2)} {udemy_obj.currency.upper()}[/green]")
    table.add_row("Already Enrolled",
                  f"[cyan]{udemy_obj.already_enrolled_c}[/cyan]")
    table.add_row("Excluded Courses",
                  f"[yellow]{udemy_obj.excluded_c}[/yellow]")
    table.add_row("Expired Courses", f"[red]{udemy_obj.expired_c}[/red]")

    console.print(table)
    if interactive:
        console.input("\nPress Enter to return to Main Menu...")


def main_menu_loop(udemy_obj: Udemy):
    while True:
        console.clear()
        console.print(
            Panel(
                f"[bold green]Discounted Udemy Course Enroller (DUCE)[/bold green]\n"
                f"[cyan]Interactive Console Overhaul {VERSION}[/cyan]\n\n"
                f"Logged in as: [bold yellow]{udemy_obj.display_name}[/bold yellow] (Currency: {udemy_obj.currency})",
                title="DUCE CLI Dashboard",
                border_style="green",
                padding=(1, 2)
            )
        )

        console.print("[bold cyan]MAIN MENU[/bold cyan]")
        console.print("1. 🚀 Run Course Enroller")
        console.print("2. ⚙️ Edit Settings")
        console.print("3. 👤 Manage Account & Login")
        console.print("4. 📜 View Enrollment History")
        console.print("5. ❌ Exit")

        choice = console.input("\n[cyan]Enter option (1-5): [/cyan]").strip()
        if choice == "1":
            run_course_enroller_process(udemy_obj)
        elif choice == "2":
            edit_settings_menu(udemy_obj)
        elif choice == "3":
            configure_login_menu(udemy_obj)
        elif choice == "4":
            view_history_menu(udemy_obj)
        elif choice == "5":
            console.print("[cyan]Exiting... Goodbye![/cyan]")
            sys.exit(0)


if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(
            description="Discounted Udemy Course Enroller (DUCE) CLI",
            add_help=False
        )
        parser.add_argument("-h", "--help", action="help", help="Show this help message and exit")
        parser.add_argument("-v", "--version", action="version", version=f"DUCE CLI {VERSION}", help="Show program version number and exit")
        parser.add_argument("-n", "--non-interactive", action="store_true", help="Run enroller in non-interactive / automated mode")
        parser.add_argument("-i", "--interval", type=int, default=0, help="Automatically run enroller repeatedly every N minutes")

        args, unknown = parser.parse_known_args()

        # Check TTY status and configure interactive flag
        is_tty = sys.stdin.isatty()
        if args.non_interactive or args.interval > 0:
            INTERACTIVE = False
        elif not is_tty:
            # Fall back to non-interactive mode automatically if not run from a TTY (cron/ci)
            logger.info("Standard input is not a TTY. Defaulting to non-interactive mode.")
            INTERACTIVE = False
        else:
            INTERACTIVE = True

        logger.info(f"Starting CLI application (interactive={INTERACTIVE})")
        udemy = Udemy("cli")
        udemy.load_settings()
        login_title, main_title = udemy.check_for_update()

        if INTERACTIVE:
            console.print(
                Panel.fit(
                    f"[bold green]Discounted Udemy Course Enroller[/bold green] [cyan]{VERSION}[/cyan]",
                    title="Welcome to DUCE",
                    border_style="green",
                )
            )
            if "Update" in login_title:
                console.print(f"[bold yellow]{login_title}[/bold yellow]")

        login_successful = False
        while not login_successful:
            try:
                login_method = ""
                if udemy.settings["use_browser_cookies"]:
                    login_method = "Browser Cookies"
                    if INTERACTIVE:
                        with console.status(
                            "[cyan]Trying to login using browser cookies...[/cyan]"
                        ):
                            udemy.fetch_cookies(
                                on_locked=cli_on_locked, on_select=cli_on_select)
                    else:
                        udemy.fetch_cookies(
                            on_locked=cli_on_locked, on_select=cli_on_select)
                elif udemy.settings["email"] and udemy.settings["password"]:
                    email, password = (
                        udemy.settings["email"],
                        udemy.settings["password"],
                    )
                    login_method = "Saved Email and Password"
                else:
                    if not INTERACTIVE:
                        raise LoginException("No saved credentials or cookies found. Cannot run non-interactively.")
                    email = console.input("[cyan]Email: [/cyan]")
                    password = console.input(
                        "[cyan]Password: [/cyan]", password=True)
                    login_method = "Email and Password"

                logger.info(f"Trying to login using {login_method}")
                console.print(
                    f"[cyan]Trying to login using {login_method}...[/cyan]")
                if "Email" in login_method:
                    if INTERACTIVE:
                        with console.status("[cyan]Logging in...[/cyan]"):
                            udemy.manual_login(email, password)
                    else:
                        udemy.manual_login(email, password)

                if INTERACTIVE:
                    with console.status("[cyan]Getting Enrolled Courses...[/cyan]"):
                        udemy.get_session_info()
                else:
                    udemy.get_session_info()

                if "Email" in login_method:
                    udemy.settings["email"], udemy.settings["password"] = (
                        email,
                        password,
                    )
                login_successful = True
            except LoginException as e:
                handle_error("Login error", error=e, exit_program=False)
                if not INTERACTIVE:
                    logger.error("Login failed in non-interactive mode. Exiting.")
                    sys.exit(1)
                if "Browser" in login_method:
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

                    console.print(
                        f"[bold yellow]Automatic browser cookie extraction is deprecated due to modern browser security restrictions (e.g. App-Bound Encryption).[/bold yellow]\n")
                    console.print(
                        "[bold cyan]How to import cookies manually:[/bold cyan]\n\n"
                        "1. Export cookies in JSON format from your browser using the 'Cookie-Editor' extension.\n\n"
                        "2. Copy them to your clipboard and choose 'Retry' (copied cookies are auto-detected).\n\n"
                        "3. Or paste them directly into the file:\n"
                        f"   [cyan]{cookies_path}[/cyan]\n"
                    )

                    console.print("[cyan]Choose an option to continue:[/cyan]")
                    console.print(
                        "[bold cyan]1.[/bold cyan] Retry loading cookies (after closing browser or filling cookies.json)")
                    console.print(
                        "[bold cyan]2.[/bold cyan] Switch to Email and Password login")
                    console.print("[bold cyan]3.[/bold cyan] Exit")

                    choice = ""
                    while choice not in ["1", "2", "3"]:
                        choice = console.input(
                            "[cyan]Enter choice (1-3): [/cyan]").strip()

                    if choice == "1":
                        udemy.settings["use_browser_cookies"] = True
                    elif choice == "2":
                        udemy.settings["use_browser_cookies"] = False
                        udemy.settings["email"], udemy.settings["password"] = "", ""
                    else:
                        sys.exit(0)
                elif "Email" in login_method:
                    console.print("[cyan]Choose an option to continue:[/cyan]")
                    console.print(
                        "[bold cyan]1.[/bold cyan] Retry Email and Password login")
                    console.print(
                        "[bold cyan]2.[/bold cyan] Switch to Browser Cookies login")
                    console.print("[bold cyan]3.[/bold cyan] Exit")

                    choice = ""
                    while choice not in ["1", "2", "3"]:
                        choice = console.input(
                            "[cyan]Enter choice (1-3): [/cyan]").strip()

                    if choice == "1":
                        udemy.settings["email"], udemy.settings["password"] = "", ""
                        udemy.settings["use_browser_cookies"] = False
                    elif choice == "2":
                        udemy.settings["use_browser_cookies"] = True
                    else:
                        sys.exit(0)

        udemy.save_settings()
        console.print("[bold green]Logged in successfully![/bold green]")
        logger.info("Logged in")
        time.sleep(1)

        # Enter main application loop
        if INTERACTIVE:
            main_menu_loop(udemy)
        else:
            if args.interval > 0:
                console.print(f"[bold cyan]Starting automation loop: running once every {args.interval} minutes.[/bold cyan]")
                logger.info(f"Starting automation loop: interval={args.interval} minutes")
                while True:
                    run_course_enroller_process(udemy, interactive=False)
                    console.print(f"\n[cyan]Enroller run completed. Sleeping for {args.interval} minutes...[/cyan]")
                    time.sleep(args.interval * 60)
            else:
                run_course_enroller_process(udemy, interactive=False)
                console.print("[bold green]Automation run completed successfully.[/bold green]")
                sys.exit(0)

    except Exception as e:
        handle_error("A critical error occurred", error=e, exit_program=True)
