import os
import json
import shutil
import base64
import sqlite3
import requests
from loguru import logger
from requests.cookies import RequestsCookieJar
from duce.core.config import get_user_data_path
from duce.core.exceptions import LoginException


def encrypt_cookies(cookies_data, file_path):
    try:
        raw_data = json.dumps(cookies_data).encode("utf-8")
        if os.name == "nt":
            import win32crypt
            # 0x01 = CRYPTPROTECT_UI_FORBIDDEN
            encrypted_data = win32crypt.CryptProtectData(
                raw_data, "DUCE Cookie Cache", None, None, None, 0x01)
        else:
            encrypted_data = raw_data
        temp_path = file_path + ".tmp"
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(encrypted_data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(temp_path, file_path)
        logger.debug(f"Saved encrypted cookie cache to {file_path}")
    except Exception as e:
        logger.error(f"Failed to encrypt cookie cache: {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def decrypt_cookies(file_path):
    try:
        with open(file_path, "rb") as f:
            encrypted_data = f.read()
        if os.name == "nt":
            import win32crypt
            _, decrypted_data = win32crypt.CryptUnprotectData(
                encrypted_data, None, None, None, 0)
        else:
            decrypted_data = encrypted_data
        return json.loads(decrypted_data.decode("utf-8"))
    except Exception as e:
        logger.debug(f"Failed to decrypt cookie cache from {file_path}: {e}")
        return None


def get_browser_key(local_state_path):
    if not os.path.exists(local_state_path):
        return None
    try:
        import win32crypt
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(
            local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]
        return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except Exception as e:
        logger.debug(f"Failed to decrypt key from {local_state_path}: {e}")
        return None


def decrypt_cookie_val(value, key):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if value[:3] == b'v10' or value[:3] == b'v11':
            nonce = value[3:15]
            ciphertext = value[15:]
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return None


def find_browser_cookie_paths():
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    logger.debug(
        f"find_browser_cookie_paths: APPDATA={appdata}, LOCALAPPDATA={localappdata}")

    browsers = {
        "Chrome": {
            "user_data": os.path.join(localappdata, r"Google\Chrome\User Data"),
            "state": "Local State",
            "processes": ["chrome.exe"]
        },
        "Edge": {
            "user_data": os.path.join(localappdata, r"Microsoft\Edge\User Data"),
            "state": "Local State",
            "processes": ["msedge.exe"]
        },
        "Brave": {
            "user_data": os.path.join(localappdata, r"BraveSoftware\Brave-Browser\User Data"),
            "state": "Local State",
            "processes": ["brave.exe"]
        },
        "Vivaldi": {
            "user_data": os.path.join(localappdata, r"Vivaldi\User Data"),
            "state": "Local State",
            "processes": ["vivaldi.exe"]
        },
        "Opera": {
            "user_data": os.path.join(appdata, r"Opera Software\Opera Stable"),
            "state": "Local State",
            "processes": ["opera.exe"]
        },
        "Opera GX": {
            "user_data": os.path.join(appdata, r"Opera Software\Opera GX Stable"),
            "state": "Local State",
            "processes": ["opera.exe"]
        }
    }

    candidates = []
    for b_name, b_info in browsers.items():
        user_data = b_info["user_data"]
        state_file = os.path.join(user_data, b_info["state"])
        logger.debug(
            f"Checking Chromium browser {b_name}: user_data={user_data}, state_file={state_file}")
        if not os.path.exists(state_file):
            logger.debug(f"  Local State file not found for {b_name}")
            continue

        profiles = ["Default"]
        try:
            if os.path.exists(user_data):
                for item in os.listdir(user_data):
                    if item.startswith("Profile ") and os.path.isdir(os.path.join(user_data, item)):
                        profiles.append(item)
        except Exception as e:
            logger.debug(f"  Error reading profiles inside {user_data}: {e}")

        logger.debug(f"  Profiles list to check for {b_name}: {profiles}")
        for profile in profiles:
            p_path = os.path.join(user_data, profile)
            if not os.path.exists(p_path) and (b_name in ("Opera", "Opera GX")):
                p_path = user_data

            cookies_options = [
                os.path.join(p_path, "Network", "Cookies"),
                os.path.join(p_path, "Cookies")
            ]
            for cookies_path in cookies_options:
                exists = os.path.exists(cookies_path)
                logger.debug(
                    f"  Checking cookies path option: {cookies_path} (exists={exists})")
                if exists:
                    candidates.append({
                        "type": "chromium",
                        "browser": b_name,
                        "profile": profile,
                        "state_path": state_file,
                        "cookies_path": cookies_path,
                        "processes": b_info["processes"]
                    })
                    break

    firefox_like = {
        "Firefox": {
            "profiles_dir": os.path.join(appdata, r"Mozilla\Firefox\Profiles"),
            "processes": ["firefox.exe"]
        },
        "LibreWolf": {
            "profiles_dir": os.path.join(appdata, r"LibreWolf\Profiles"),
            "processes": ["librewolf.exe"]
        },
        "Waterfox": {
            "profiles_dir": os.path.join(appdata, r"Waterfox\Profiles"),
            "processes": ["waterfox.exe"]
        }
    }

    for b_name, b_info in firefox_like.items():
        p_dir = b_info["profiles_dir"]
        logger.debug(
            f"Checking Firefox-like browser {b_name}: profiles_dir={p_dir}")
        if not os.path.exists(p_dir):
            logger.debug(f"  Profiles directory not found for {b_name}")
            continue
        try:
            for item in os.listdir(p_dir):
                profile_path = os.path.join(p_dir, item)
                if os.path.isdir(profile_path):
                    cookies_path = os.path.join(profile_path, "cookies.sqlite")
                    exists = os.path.exists(cookies_path)
                    logger.debug(
                        f"  Checking cookies path option: {cookies_path} (exists={exists})")
                    if exists:
                        candidates.append({
                            "type": "firefox",
                            "browser": b_name,
                            "profile": item,
                            "cookies_path": cookies_path,
                            "processes": b_info["processes"]
                        })
        except Exception as e:
            logger.debug(f"  Error reading Firefox profiles for {b_name}: {e}")

    logger.debug(
        f"find_browser_cookie_paths: found {len(candidates)} candidates.")
    return candidates


def kill_browser_processes(processes):
    import subprocess
    import os
    for proc in processes:
        try:
            logger.info(f"Force closing browser process: {proc}")
            if os.name == "nt":
                subprocess.run(["taskkill", "/f", "/im", proc],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                unix_proc = proc.replace(".exe", "")
                subprocess.run(["pkill", "-f", unix_proc],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug(f"Failed to terminate process {proc}: {e}")


def extract_cookies_from_candidate(c):
    b_name = c["browser"]
    profile = c["profile"]
    cookies_path = c["cookies_path"]

    temp_path = get_user_data_path(f"temp_{b_name}_{profile}_cookies")
    try:
        shutil.copy2(cookies_path, temp_path)
    except PermissionError as e:
        raise e
    except Exception as e:
        logger.debug(f"Failed to copy cookies for {b_name} - {profile}: {e}")
        return None, None, False

    temp_cj = RequestsCookieJar()
    is_v20 = False
    try:
        if c["type"] == "chromium":
            key = get_browser_key(c["state_path"])
            if not key:
                return None, None, False

            conn = sqlite3.connect(temp_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(cookies)")
                columns = [col[1] for col in cursor.fetchall()]

                q_cols = ["host_key", "name", "path", "encrypted_value"]
                has_secure = "secure" in columns
                has_is_secure = "is_secure" in columns
                if has_secure:
                    q_cols.append("secure")
                elif has_is_secure:
                    q_cols.append("is_secure")

                query = f"SELECT {', '.join(q_cols)} FROM cookies WHERE host_key LIKE '%udemy%'"
                cursor.execute(query)
                rows = cursor.fetchall()

                found_names = []
                decrypted_count = 0
                for row in rows:
                    host, name, path, enc_val = row[0], row[1], row[2], row[3]
                    if name in ("access_token", "client_id"):
                        found_names.append(name)

                    secure = False
                    if has_secure or has_is_secure:
                        secure = bool(row[4])
                    dec_val = decrypt_cookie_val(enc_val, key)
                    if dec_val:
                        temp_cj.set(name, dec_val, domain=host,
                                    path=path, secure=secure)
                        if name in ("access_token", "client_id"):
                            decrypted_count += 1

                # Check for App-Bound Encryption (v20)
                if ("access_token" in found_names or "client_id" in found_names) and decrypted_count == 0:
                    is_v20 = True
                    logger.debug(
                        f"Detected App-Bound Encryption (v20) in browser {c['browser']} - {c['profile']}")
            finally:
                conn.close()

        elif c["type"] == "firefox":
            conn = sqlite3.connect(temp_path)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(moz_cookies)")
                columns = [col[1] for col in cursor.fetchall()]

                q_cols = ["host", "name", "value", "path"]
                has_secure = "isSecure" in columns
                if has_secure:
                    q_cols.append("isSecure")

                query = f"SELECT {', '.join(q_cols)} FROM moz_cookies WHERE host LIKE '%udemy%'"
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    host, name, val, path = row[0], row[1], row[2], row[3]
                    secure = False
                    if has_secure:
                        secure = bool(row[4])
                    temp_cj.set(name, val, domain=host,
                                path=path, secure=secure)
            finally:
                conn.close()
    except Exception as e:
        logger.debug(f"Error parsing database for {b_name} - {profile}: {e}")
        return None, None, False
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    cookie_dict = requests.utils.dict_from_cookiejar(temp_cj)
    if "access_token" in cookie_dict and "client_id" in cookie_dict:
        return cookie_dict, temp_cj, False
    return None, None, is_v20


def fetch_cookies(on_locked=None, on_select=None) -> tuple[dict, RequestsCookieJar]:
    """Gets cookies from browser using local profile databases or loads them from cookies.json.
    Tries loading from cookies.json/udemy-cookies.json first, then falls back to browser databases.
    Returns (cookie_dict, cookie_jar)
    """
    debug_log_path = get_user_data_path("duce_debug.log")
    try:
        logger.add(debug_log_path, rotation="5 MB", level="DEBUG")
    except Exception:
        pass
    logger.info("Fetching cookies")
    logger.debug("--- Start fetch_cookies ---")

    # 1. Clipboard Check
    clipboard_text = ""
    try:
        if os.name == "nt":
            import win32clipboard
            try:
                win32clipboard.OpenClipboard()
                clipboard_text = win32clipboard.GetClipboardData(
                    win32clipboard.CF_UNICODETEXT)
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
        else:
            import tkinter as tk
            root = tk.Tk()
            try:
                root.withdraw()
                clipboard_text = root.clipboard_get()
            finally:
                try:
                    root.destroy()
                except Exception:
                    pass

        if clipboard_text and len(clipboard_text) < 1024 * 1024 and (clipboard_text.strip().startswith("[") or clipboard_text.strip().startswith("{")):
            try:
                cookies_data = json.loads(clipboard_text)
                if isinstance(cookies_data, dict):
                    cookies_data = [cookies_data]
                if isinstance(cookies_data, list):
                    cj = RequestsCookieJar()
                    for c in cookies_data:
                        if isinstance(c, dict):
                            cj.set(
                                c.get("name"),
                                c.get("value"),
                                domain=c.get("domain", ""),
                                path=c.get("path", "/"),
                                secure=c.get("secure", False),
                                expires=c.get("expirationDate")
                            )
                    cookie_dict = requests.utils.dict_from_cookiejar(cj)
                    if "access_token" in cookie_dict and "client_id" in cookie_dict:
                        logger.info(
                            "Cookies successfully loaded from system clipboard")
                        encrypt_cookies(
                            cookies_data, get_user_data_path("udemy-cookies.json"))
                        try:
                            cookies_json_path = get_user_data_path("cookies.json")
                            temp_path = cookies_json_path + ".tmp"
                            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                            with os.fdopen(fd, "w", encoding="utf-8") as f:
                                json.dump(cookies_data, f, indent=4)
                                f.flush()
                                try:
                                    os.fsync(f.fileno())
                                except Exception:
                                    pass
                            os.replace(temp_path, cookies_json_path)
                            logger.info(f"Saved clipboard cookies to {cookies_json_path}")
                        except Exception as file_err:
                            logger.error(f"Failed to save clipboard cookies to cookies.json: {file_err}")
                            if 'temp_path' in locals() and os.path.exists(temp_path):
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                        return cookie_dict, cj
            except Exception as e:
                logger.debug(f"Failed to parse clipboard cookies JSON: {e}")
    except Exception as e:
        logger.debug(f"Failed to read from clipboard: {e}")

    # 2. Cached File Check
    for filename in ("cookies.json", "udemy-cookies.json"):
        cookies_file = get_user_data_path(filename)
        if os.path.exists(cookies_file):
            logger.info(
                f"Found {filename} at {cookies_file}, trying to load...")
            cookies_data = decrypt_cookies(cookies_file)
            if not cookies_data:
                try:
                    with open(cookies_file, "r", encoding="utf-8") as f:
                        cookies_data = json.load(f)
                except Exception as plain_err:
                    logger.error(f"Failed to load {filename}: {plain_err}. Auto-healing: backing up and removing corrupt cookie file.")
                    try:
                        bak_file = cookies_file + ".bak"
                        if os.path.exists(bak_file):
                            os.remove(bak_file)
                        os.rename(cookies_file, bak_file)
                    except Exception as backup_err:
                        logger.error(f"Failed to back up corrupt cookie file: {backup_err}")
                        try:
                            os.remove(cookies_file)
                        except Exception:
                            pass
                    continue
            if cookies_data:
                cj = RequestsCookieJar()
                for c in cookies_data:
                    cj.set(
                        c.get("name"),
                        c.get("value"),
                        domain=c.get("domain", ""),
                        path=c.get("path", "/"),
                        secure=c.get("secure", False),
                        expires=c.get("expirationDate")
                    )
                cookie_dict = requests.utils.dict_from_cookiejar(cj)
                if "access_token" in cookie_dict and "client_id" in cookie_dict:
                    logger.info(f"Cookies successfully loaded from {filename}")
                    if filename == "cookies.json":
                        encrypt_cookies(
                            cookies_data, get_user_data_path("udemy-cookies.json"))
                    return cookie_dict, cj
                else:
                    logger.warning(
                        f"{filename} was loaded but missing access_token/client_id")

    # 3. Dynamic Browser Profile Scan (Deprecated)
    logger.warning("Automatic browser cookie extraction is deprecated.")
    raise LoginException(
        "Automatic browser cookie extraction is deprecated due to modern browser security restrictions (e.g. App-Bound Encryption).\n\n"
        "Please import your cookies manually:\n\n"
        "1. Install the 'Cookie-Editor' extension in Chrome, Firefox, Edge, or Brave.\n\n"
        "2. Log in to your Udemy account on www.udemy.com.\n\n"
        "3. Click the 'Cookie-Editor' icon (cookie shape in top-right), click 'Export', and select 'JSON' (copies to clipboard).\n\n"
        "4. Return to this app and click 'Extract & Auto Login' (will load automatically from clipboard).\n\n"
        "5. Or paste (Ctrl+V) directly into the 'cookies.json' file in the application folder."
    )
