import os
import re
import json
import time
import atexit
import requests
import threading
import concurrent.futures
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote
from loguru import logger
try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.requests.errors import RequestsError
except ImportError:
    cffi_requests = None
    class RequestsError(Exception):
        pass

from duce.core.config import VERSION, scraper_dict, get_user_data_path, resource_path
from duce.core.exceptions import LoginException
from duce.core.models import Course
from duce.core.cookies import fetch_cookies
from duce.utils.html import parse_html
from duce.core.db import db
from duce.utils.network import RobustRequestsSession, RobustCffiSession, SystemCertHTTPAdapter


class Udemy:
    def __init__(self, interface: str, debug: bool = False):
        self.interface = interface
        self.client = RobustRequestsSession()
        adapter = SystemCertHTTPAdapter()
        self.client.mount("https://", adapter)
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "Referer": "https://www.udemy.com/",
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }

        self.client.headers.update(headers)
        self.debug = debug

        self.successfully_enrolled_c = 0
        self.already_enrolled_c = 0
        self.expired_c = 0
        self.excluded_c = 0
        self.amount_saved_c = Decimal(0)

        self.course: Course = None
        self.currency: str = "USD"
        self.stats_lock = threading.Lock()
        self.txt_file = None
        atexit.register(self.cleanup)

        # Log program start
        logger.info(f"Program started - {self.interface} mode")

    def update_progress(self):
        """Placeholder method to be overridden by UI/CLI implementations"""
        pass

    def get_date_from_utc(self, d: str):
        utc_dt = datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ")
        dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return dt.strftime("%B %d, %Y")

    def get_now_to_utc(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def load_settings(self):
        settings_file = get_user_data_path(
            f"duce-{self.interface}-settings.json")
        default_file = resource_path(
            f"default-duce-{self.interface}-settings.json")
        loaded = False

        try:
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
                loaded = True
        except Exception as e:
            logger.error(
                f"Error loading settings file {settings_file}: {e}. Backing up and restoring defaults.")
            try:
                corrupted_backup = settings_file + ".bak"
                if os.path.exists(settings_file):
                    if os.path.exists(corrupted_backup):
                        os.remove(corrupted_backup)
                    os.rename(settings_file, corrupted_backup)
            except Exception as backup_e:
                logger.error(
                    f"Failed to backup corrupted settings: {backup_e}")

        if not loaded:
            try:
                with open(default_file, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except Exception as default_e:
                logger.critical(
                    f"Failed to load default settings file {default_file}: {default_e}")
                # Ultimate hardcoded fallback settings dictionary to prevent crashes
                self.settings = {
                    "email": "",
                    "password": "",
                    "use_browser_cookies": True,
                    "save_txt": True,
                    "discounted_only": False,
                    "course_update_threshold_months": 24,
                    "min_rating": 0.0,
                    "stay_logged_in": {"auto": False, "manual": False},
                    "sites": {
                        k: (k not in ("Tutorial Bar", "E-next",
                            "Course Joiner", "Course Vania"))
                        for k in scraper_dict.keys()
                    },
                    "categories": {
                        "Development": True, "Business": True, "IT & Software": True,
                        "Office Productivity": True, "Personal Development": True,
                        "Design": True, "Marketing": True, "Lifestyle": True,
                        "Photography & Video": True, "Health & Fitness": True,
                        "Music": True, "Teaching & Academics": True, "Finance & Accounting": True
                    },
                    "languages": {
                        "Arabic": True, "Chinese": True, "Dutch": True, "English": True,
                        "French": True, "German": True, "Hindi": True, "Indonesian": True,
                        "Italian": True, "Japanese": True, "Korean": True, "Nepali": True,
                        "Polish": True, "Portuguese": True, "Romanian": True, "Russian": True,
                        "Spanish": True, "Thai": True, "Turkish": True, "Urdu": True,
                        "Vietnamese": True
                    },
                    "title_exclude": [],
                    "instructor_exclude": [],
                    "proxies": {"http": "", "https": ""},
                    "discord_webhook_url": ""
                }

        # Self-healing logic to merge missing keys from default_settings dictionary
        default_settings = {
            "stay_logged_in": {"auto": False, "manual": False},
            "min_rating": 0.0,
            "title_exclude": [],
            "instructor_exclude": [],
            "languages": {
                "Arabic": True, "Chinese": True, "Dutch": True, "English": True,
                "French": True, "German": True, "Hindi": True, "Indonesian": True,
                "Italian": True, "Japanese": True, "Korean": True, "Nepali": True,
                "Polish": True, "Portuguese": True, "Romanian": True, "Russian": True,
                "Spanish": True, "Thai": True, "Turkish": True, "Urdu": True,
                "Vietnamese": True
            },
            "categories": {
                "Business": True, "Design": True, "Development": True,
                "Finance & Accounting": True, "Health & Fitness": True,
                "IT & Software": True, "Lifestyle": True, "Marketing": True,
                "Music": True, "Office Productivity": True, "Personal Development": True,
                "Photography & Video": True, "Teaching & Academics": True
            },
            "sites": {
                "Real Discount": True, "Courson": True, "IDownloadCoupons": True,
                "Tutorial Bar": False, "E-next": False, "Discudemy": True,
                "Udemy Freebies": True, "Course Joiner": False, "Course Vania": False,
                "Coupon Scorpion": True
            },
            "email": "",
            "password": "",
            "save_txt": False,
            "discounted_only": False,
            "course_update_threshold_months": 24,
            "use_browser_cookies": False,
            "proxies": {"http": "", "https": ""},
            "discord_webhook_url": "",
            "allow_insecure_ssl_fallback": False,
            "network_timeout": 60
        }

        # Merge missing top-level and dictionary-level keys
        for key, val in default_settings.items():
            if key not in self.settings:
                self.settings[key] = val
            elif isinstance(val, dict):
                for sub_key, sub_val in val.items():
                    if sub_key not in self.settings[key]:
                        self.settings[key][sub_key] = sub_val

        # Interface-specific defaults
        if self.interface == "cli" and "use_browser_cookies" not in self.settings:
            self.settings["use_browser_cookies"] = False

        self.settings["languages"] = dict(
            sorted(self.settings["languages"].items(),
                    key=lambda item: item[0])
        )
        self.save_settings()
        self.title_exclude = "\n".join(self.settings["title_exclude"])
        self.instructor_exclude = "\n".join(
            self.settings["instructor_exclude"])

        # Apply proxy settings if available
        proxies = self.settings.get("proxies", {})
        if proxies:
            valid_proxies = {k: v for k, v in proxies.items() if v}
            if valid_proxies:
                self.client.proxies.update(valid_proxies)
                from duce.utils.network import session as net_session
                net_session.proxies.update(valid_proxies)
                logger.info(f"Proxies configured: {valid_proxies}")

        # Apply SSL fallback setting
        allow_fallback = self.settings.get("allow_insecure_ssl_fallback", False)
        self.client.allow_insecure_fallback = allow_fallback
        from duce.utils import network
        network.session.allow_insecure_fallback = allow_fallback

        # Apply Network Timeout setting
        network_timeout = self.settings.get("network_timeout", 60)
        network.RobustRequestsSession.network_timeout = network_timeout
        if hasattr(network, "RobustCffiSession"):
            network.RobustCffiSession.network_timeout = network_timeout
        self.client.network_timeout = network_timeout
        network.session.network_timeout = network_timeout

    def save_settings(self):
        settings_file = get_user_data_path(
            f"duce-{self.interface}-settings.json")
        temp_file = settings_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, settings_file)
        except Exception as e:
            logger.error(f"Failed to atomically save settings: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def compare_versions(self, version1, version2):
        v1_parts = list(map(int, version1.split(".")))
        v2_parts = list(map(int, version2.split(".")))
        max_length = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_length - len(v1_parts)))
        v2_parts.extend([0] * (max_length - len(v2_parts)))

        for v1, v2 in zip(v1_parts, v2_parts):
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
        return 0

    def check_for_update(self) -> tuple[str, str]:
        logger.info("Checking for updates...")
        try:
            s = RobustRequestsSession()
            adapter = SystemCertHTTPAdapter()
            s.mount("https://", adapter)
            r_version = s.get(
                "https://api.github.com/repos/MikeWIseX0/Discounted-Udemy-Course-Enroller/releases/latest",
                timeout=15
            )
            if r_version.status_code != 200:
                logger.error("Failed to fetch latest version info")
                return ("Login " + VERSION, "Discounted-Udemy-Course-Enroller " + VERSION)
            r_version = r_version.json()
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return ("Login " + VERSION, "Discounted-Udemy-Course-Enroller " + VERSION)
        r_version = r_version["tag_name"].removeprefix("v")
        c_version = VERSION.removeprefix("v")
        logger.info(
            f"Current version: {c_version}, Latest version: {r_version}")
        comparison = self.compare_versions(c_version, r_version)

        if comparison == -1:
            return (
                f"Update {r_version} Available",
                f"Update {r_version} Available",
            )
        elif comparison == 0:
            return (
                f"Login {c_version}",
                f"Discounted-Udemy-Course-Enroller {c_version}",
            )
        else:
            return (
                f"Dev Login {c_version}",
                f"Dev Discounted-Udemy-Course-Enroller {c_version}",
            )

    def make_cookies(self, client_id: str, access_token: str, csrf_token: str):
        self.cookie_dict = dict(
            client_id=client_id,
            access_token=access_token,
            csrf_token=csrf_token,
        )

    def fetch_cookies(self, on_locked=None, on_select=None):
        self.cookie_dict, self.cookie_jar = fetch_cookies(
            on_locked=on_locked, on_select=on_select)

    def manual_login(self, email: str, password: str):
        """Manual Login to Udemy using email and password and sets cookies"""
        logger.info("Trying to login with email and password")
        s = RobustRequestsSession()
        adapter = SystemCertHTTPAdapter()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        r = s.get(
            "https://www.udemy.com/join/signup-popup/?locale=en_US&response_type=html&next=https%3A%2F%2Fwww.udemy.com%2Flogout%2F",
            headers={
                "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)"},
            timeout=15
        )
        try:
            csrf_token = r.cookies["csrftoken"]
        except (KeyError, Exception) as e:
            logger.error(f"Failed to get CSRF token: {e}")
            if self.debug:
                logger.error(r.text)
            raise LoginException(
                "Failed to get CSRF token from Udemy. Try using browser cookies instead.")
        data = {
            "csrfmiddlewaretoken": csrf_token,
            "locale": "en_US",
            "email": email,
            "password": password,
        }

        s.cookies.update(r.cookies)
        s.headers.update(
            {
                "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-GB,en;q=0.5",
                "Referer": "https://www.udemy.com/join/login-popup/?passwordredirect=True&response_type=json",
                "Origin": "https://www.udemy.com",
                "DNT": "1",
                "Host": "www.udemy.com",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
            }
        )
        login_cookies = requests.utils.dict_from_cookiejar(s.cookies)
        cffi_s = RobustCffiSession(impersonate="chrome")
        cffi_s.headers.update(dict(s.headers))
        r = cffi_s.post(
            "https://www.udemy.com/join/login-popup/?passwordredirect=True&response_type=json",
            data=data,
            cookies=login_cookies,
            allow_redirects=False,
            timeout=15,
        )
        if "returnUrl" in r.text:
            self.make_cookies(
                r.cookies["client_id"], r.cookies["access_token"], csrf_token
            )
        else:
            try:
                r_json = r.json()
                login_error = r_json["error"]["data"]["formErrors"][0]
                if login_error[0] == "Y":
                    raise LoginException("Too many logins per hour try later")
                elif login_error[0] == "T":
                    raise LoginException("Email or password incorrect")
                else:
                    raise LoginException(login_error)
            except Exception as e:
                if isinstance(e, LoginException):
                    raise e
                raise LoginException(f"Login failed: invalid credentials or service block. (HTTP {r.status_code})")

    def get_session_info(self):
        """Get Session info"""
        logger.info("Getting session info")
        s = RobustCffiSession(impersonate="chrome")
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "Referer": "https://www.udemy.com/",
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }

        r_json = None
        for attempt in range(3):
            try:
                r = s.get(
                    "https://www.udemy.com/api-2.0/contexts/me/?header=True",
                    cookies=self.cookie_dict,
                    headers=headers,
                    timeout=15
                )
                r_json = r.json()
                break
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1} to get session context failed: {e}")
                if attempt == 2:
                    raise LoginException(
                        f"Failed to connect to Udemy session API: {e}")
                time.sleep(2)

        if not r_json or not r_json.get("header", {}).get("isLoggedIn"):
            logger.error("Login Failed: " + str(r_json))
            raise LoginException("Login Failed: Session not authenticated")

        self.display_name: str = r_json["header"]["user"]["display_name"]

        # Get currency
        for attempt in range(3):
            try:
                r = s.get(
                    "https://www.udemy.com/api-2.0/shopping-carts/me/",
                    headers=headers,
                    cookies=self.cookie_dict,
                    timeout=15
                )
                r_data = r.json()
                self.currency = r_data["user"]["credit"]["currency_code"]
                break
            except Exception as e:
                logger.warning(
                    f"Failed to fetch cart currency (attempt {attempt + 1}): {e}")
                self.currency = "USD"
                time.sleep(1)

        s = RobustCffiSession(impersonate="chrome")
        s.cookies.update(self.cookie_dict)
        s.headers.update(headers)
        self.client = s
        logger.info("Session info retrieved")
        self.get_enrolled_courses()

    def get_enrolled_courses(self):
        """Get enrolled courses with automatic page-fetching retries to prevent network crashes."""
        logger.info("Getting enrolled courses")

        # Load from cache first
        courses = db.get_enrolled_courses()
        logger.info(
            f"Loaded {len(courses)} enrolled courses from local database cache")

        # Determine whether to do a full sync or a delta sync
        is_delta = len(courses) > 0
        next_page = "https://www.udemy.com/api-2.0/users/me/subscribed-courses/?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"

        new_courses = {}
        pages_fetched = 0

        while next_page:
            response_data = None
            for attempt in range(3):
                try:
                    r = self.client.get(next_page, timeout=15)
                    response_data = r.json()
                    break
                except Exception as e:
                    logger.warning(
                        f"Error fetching enrolled courses page (attempt {attempt + 1}): {e}")
                    if attempt == 2:
                        logger.error(
                            "Failed to retrieve enrolled courses after 3 attempts. Proceeding with cached courses.")
                        self.enrolled_courses = courses
                        return
                    time.sleep(2)

            page_results = response_data.get(
                "results", []) if isinstance(response_data, dict) else []
            if not page_results:
                break

            has_seen_existing = False
            for course in page_results:
                try:
                    parts = [p for p in course["url"].split("/") if p]
                    if len(parts) >= 2:
                        slug = parts[1]
                        if slug == "draft" and len(parts) >= 3:
                            slug = parts[2]
                        enroll_time = course.get("enrollment_time", "")

                        if is_delta and slug in courses:
                            has_seen_existing = True

                        new_courses[slug] = enroll_time
                except Exception as parse_e:
                    logger.error(
                        f"Error parsing course URL in enrolled courses: {parse_e}")

            pages_fetched += 1
            if is_delta and has_seen_existing:
                logger.info(
                    f"Delta sync complete: reached previously cached courses after {pages_fetched} page(s)")
                break

            next_page = response_data.get("next") if isinstance(response_data, dict) else None

        if new_courses:
            courses.update(new_courses)
            db.save_enrolled_courses(new_courses)

        self.enrolled_courses = courses
        logger.info(f"Enrolled courses total: {len(courses)}")

    def is_keyword_excluded(self) -> bool:
        """Check if the course title contains any excluded keywords or phrases (case-insensitive)"""
        title = self.course.title.casefold()
        for kw in self.settings.get("title_exclude", []):
            if kw.strip() and kw.casefold() in title:
                return True
        return False

    def is_instructor_excluded(self) -> bool:
        """Check if the course instructor username is in the excluded list (case-insensitive)"""
        instructors = [i.casefold().strip() for i in self.course.instructors]
        excluded = [i.casefold().strip()
                    for i in self.settings.get("instructor_exclude", [])]
        for instructor in instructors:
            if instructor in excluded:
                return True
        return False

    def is_course_updated(self) -> bool:
        """Check if the course is updated within the threshold months"""
        last_update = self.course.last_update
        if not last_update:
            return True
        current_date = datetime.now()
        last_update_date = datetime.strptime(last_update, "%Y-%m-%d")
        years = current_date.year - last_update_date.year
        months = current_date.month - last_update_date.month
        days = current_date.day - last_update_date.day

        if days < 0:
            months -= 1
        if months < 0:
            years -= 1
            months += 12

        month_diff = years * 12 + months
        return month_diff < self.settings["course_update_threshold_months"]

    def is_course_excluded(self):
        selected_categories = [c.strip().casefold()
                               for c in self.categories if c]
        selected_languages = [lang.strip().casefold()
                              for lang in self.languages if lang]

        course_category = str(self.course.category).strip(
        ).casefold() if self.course.category else ""
        course_language = str(self.course.language).strip(
        ).casefold() if self.course.language else ""

        if not self.is_course_updated():
            logger.info(
                f"Course excluded: Last updated {self.course.last_update}")
            self.course.status_text = "Excluded: Outdated"
            self.course.status_color = "#8E8E93"
        elif self.is_instructor_excluded():
            logger.info(f"Instructor excluded: {self.course.instructors[0]}")
            self.course.status_text = "Excluded: Instructor"
            self.course.status_color = "#8E8E93"
        elif self.is_keyword_excluded():
            logger.info("Keyword Excluded")
            self.course.status_text = "Excluded: Title Keyword"
            self.course.status_color = "#8E8E93"
        elif course_category not in selected_categories:
            logger.info(f"Category excluded: {self.course.category}")
            self.course.status_text = f"Excluded Category: {self.course.category or 'None'}"
            self.course.status_color = "#8E8E93"
        elif course_language not in selected_languages:
            logger.info(f"Language excluded: {self.course.language}")
            self.course.status_text = f"Excluded Language: {self.course.language or 'None'}"
            self.course.status_color = "#8E8E93"
        elif self.course.rating < self.min_rating:
            logger.info(f"Low rating: {self.course.rating}")
            self.course.status_text = f"Excluded: Low Rating ({self.course.rating})"
            self.course.status_color = "#8E8E93"
        else:
            return
        self.course.is_excluded = True

    def validate_settings(self) -> bool:
        self.sites = []
        for key in scraper_dict:
            if self.settings["sites"].get(key):
                self.sites.append(key)
        self.categories = [
            key for key, value in self.settings["categories"].items() if value
        ]
        self.languages = [
            key for key, value in self.settings["languages"].items() if value
        ]
        self.instructor_exclude = self.settings["instructor_exclude"]
        self.title_exclude = self.settings["title_exclude"]
        self.min_rating = self.settings["min_rating"]
        return not all([bool(self.sites), bool(self.categories), bool(self.languages)])

    def get_course_id(self):
        """Set course_id and metadata and is_excluded"""
        if self.course.course_id:
            return
        url = re.sub(r"\W+$", "", unquote(self.course.url))
        r = None
        for attempt in range(3):
            try:
                r = self.client.get(url, timeout=15)
                if r.status_code == 200:
                    break
            except (requests.exceptions.ConnectionError, RequestsError):
                r = None
            except Exception as e:
                logger.error(
                    f"Error fetching course ID (attempt {attempt + 1}): {e}")
                logger.error(f"Course URL: {url}")
                r = None
            time.sleep(1)

        if r is None:
            logger.error("Failed to fetch course ID after 3 attempts")
            self.course.is_valid = False
            self.course.error = "Failed to fetch course ID: network error"
            return

        if r.status_code != 200:
            logger.warning(f"Failed to fetch course ID: status code {r.status_code}")
            self.course.is_valid = False
            self.course.error = f"Failed to fetch course ID: HTTP {r.status_code}"
            return

        self.course.set_url(r.url)
        soup = parse_html(r.content)
        body = soup.find("body")
        if not body or not body.get("data-clp-course-id"):
            self.course.is_valid = False
            self.course.error = "Course ID not found on landing page: Report to developer"
            return

        course_id = body.get("data-clp-course-id", "invalid")
        if course_id == "invalid":
            self.course.is_valid = False
            self.course.error = "Course ID not found: Report to developer"
            return

        self.course.course_id = course_id
        try:
            dma_str = body.get("data-module-args")
            if dma_str:
                dma = json.loads(dma_str)
                if self.debug:
                    os.makedirs("debug/", exist_ok=True)
                    with open("debug/dma.json", "w") as f:
                        json.dump(dma, f, indent=4)
                self.course.set_metadata(dma)
            else:
                self.course.is_valid = False
                self.course.error = "data-module-args not found on page"
        except Exception as e:
            self.course.is_valid = False
            self.course.error = f"Error reading page metadata: {e}"

        if not self.course.is_valid:
            return
        self.is_course_excluded()

    def check_course(self):
        if self.course.price is not None:
            return
        url = f"https://www.udemy.com/api-2.0/course-landing-components/{self.course.course_id}/me/?components=purchase"
        if self.course.coupon_code:
            url += f",redeem_coupon&couponCode={self.course.coupon_code}"
        logger.debug(f"Checking course: {url}")
        for _ in range(3):
            try:
                r = self.client.get(url, timeout=15)
                r_json = r.json()
                if isinstance(r_json, dict):
                    r = r_json
                    break
                else:
                    logger.error(f"Invalid non-dict JSON response from Udemy check: {type(r_json).__name__}")
                    r = None
            except (requests.exceptions.ConnectionError, RequestsError):
                r = None
            except Exception as e:
                logger.error(f"Error fetching course data: {e}")
                logger.error(f"Course ID: {self.course.course_id}")
                logger.error(f"Coupon Code: {self.course.coupon_code}")
                logger.error(f"URL: {url}")
                r = None
        if r is None or not isinstance(r, dict):
            logger.error(
                f"Failed to fetch valid course data after 3 attempts for course {self.course.course_id}")
            self.course.is_valid = False
            self.course.error = "Failed to fetch course data: network error or invalid response"
            return
        amount = (
            r.get("purchase", {})
            .get("data", {})
            .get("list_price", {})
            .get("amount", None)
        )
        self.course.price = Decimal(
            str(amount)) if amount is not None else None
        if self.course.price is None:
            logger.error(f"Course not found {self.course.course_id}")
            logger.error("Report to developer")
            raise Exception("Course not found")

        if self.course.coupon_code and "redeem_coupon" in r:
            discount = r["purchase"]["data"]["pricing_result"]["discount_percent"]
            status = r["redeem_coupon"]["discount_attempts"][0]["status"]
            self.course.is_coupon_valid = discount == 100 and status == "applied"

    def save_course(self, course: Course = None):
        if course is None:
            course = self.course
        if self.settings["save_txt"]:
            try:
                self.txt_file.write(f"{str(course)}\n")
                self.txt_file.flush()
                os.fsync(self.txt_file.fileno())
            except Exception as e:
                logger.exception(f"Error writing course to file: {e}")

    def is_already_enrolled(self):
        slug = self.course.slug
        if not slug or not isinstance(slug, str):
            logger.error("SLUG NOT FOUND")
            return False
        return slug in self.enrolled_courses

    def start_new_enroll(self):
        """Filters scraped courses based on validity, settings, and coupon status."""
        logger.info("Starting enrollment process")
        self.setup_txt_file()

        courses: list[Course] = self.scraped_data
        self.total_courses = len(courses)
        self.valid_courses: list[Course] = []
        self.total_courses_processed = 0
        self.processed_slugs = set()

        for index, current_course in enumerate(courses):
            if getattr(self, "cancelled", False):
                logger.info("Enrollment process cancelled by user")
                break
            self.course = current_course
            self.course.status_text = "Evaluating..."
            self.course.status_color = "#00F2FE"
            self.total_courses_processed = (index + 1)
            self.update_progress()

            slug = self.course.slug
            if slug and slug in self.processed_slugs:
                logger.info(
                    f"Bypassing redundant course evaluation for slug: {slug}")
                self.course.status_text = "Bypassed (Duplicate)"
                self.course.status_color = "#8E8E93"
                self.update_progress()
                continue

            logger.info(
                f"Processing course {index + 1} / {self.total_courses}: {str(self.course)}")
            if self.is_already_enrolled():
                enroll_time = self.enrolled_courses.get(self.course.slug, "")
                if enroll_time:
                    try:
                        logger.info(
                            f"Already enrolled on {self.get_date_from_utc(enroll_time)}")
                    except (ValueError, TypeError):
                        logger.info(
                            "Already enrolled (enrollment date unavailable)")
                else:
                    logger.info("Already enrolled")
                self.course.status_text = "Already Enrolled"
                self.course.status_color = "#FF9F0A"
                self.already_enrolled_c += 1
                if slug:
                    self.processed_slugs.add(slug)
            else:
                cached_data = db.get_validation(slug, self.course.coupon_code)
                if cached_data:
                    logger.info(
                        f"Loaded validation state from local cache for {slug}")
                    self.course.is_valid = cached_data["is_valid"]
                    self.course.is_free = cached_data["is_free"]
                    self.course.error = cached_data["error"]
                    self.course.title = cached_data["title"]
                    self.course.course_id = cached_data["course_id"]
                    self.course.price = cached_data["price"]
                    self.course.instructors = cached_data["instructors"]
                    self.course.language = cached_data["language"]
                    self.course.category = cached_data["category"]
                    self.course.rating = cached_data["rating"]
                    self.course.last_update = cached_data["last_update"]
                    self.course.is_coupon_valid = cached_data["is_coupon_valid"]
                    # Re-evaluate exclusion against current user settings
                    # (cached is_excluded may be stale if user changed filters)
                    self.course.is_excluded = False
                    if self.course.is_valid:
                        self.is_course_excluded()
                else:
                    self.get_course_id()
                    if self.course.is_valid and not self.course.is_excluded:
                        if not self.course.is_free:
                            self.check_course()
                    # Cache the newly resolved validation details
                    db.save_validation(self.course)

                final_slug = self.course.slug

                if not self.course.is_valid:
                    logger.error(f"Invalid: {self.course.error}")
                    self.course.status_text = f"Invalid: {self.course.error}"
                    self.course.status_color = "#FF453A"
                    self.excluded_c += 1

                elif self.is_already_enrolled():
                    enroll_time = self.enrolled_courses.get(
                        self.course.slug, "")
                    if enroll_time:
                        try:
                            logger.info(
                                f"Already enrolled on {self.get_date_from_utc(enroll_time)}")
                        except (ValueError, TypeError):
                            logger.info(
                                "Already enrolled (enrollment date unavailable)")
                    else:
                        logger.info("Already enrolled")
                    self.course.status_text = "Already Enrolled"
                    self.course.status_color = "#FF9F0A"
                    self.already_enrolled_c += 1
                elif self.course.is_excluded:
                    # Note: status_text is already set inside is_course_excluded()
                    self.excluded_c += 1

                elif self.course.is_free:
                    if self.settings["discounted_only"]:
                        logger.info(
                            "Free course excluded (discounted only setting)")
                        self.course.status_text = "Excluded: Free Course"
                        self.course.status_color = "#8E8E93"
                        self.excluded_c += 1
                    else:
                        self.free_checkout()
                        if self.course.status:
                            logger.success("Successfully Subscribed")
                            self.course.status_text = "Successfully Subscribed"
                            self.course.status_color = "#2ECC71"
                            self.successfully_enrolled_c += 1
                            self.save_course()
                            db.save_enrolled_courses(
                                {self.course.slug: self.get_now_to_utc()})
                        else:
                            logger.info(
                                "Unknown Error: Report this link to the developer")
                            self.course.status_text = "Failed to Subscribe"
                            self.course.status_color = "#FF453A"
                            self.expired_c += 1

                elif not self.course.is_coupon_valid:
                    logger.info("Coupon Expired")
                    self.course.status_text = "Coupon Expired"
                    self.course.status_color = "#FF453A"
                    self.expired_c += 1

                elif self.course.is_coupon_valid:
                    self.valid_courses.append(self.course)
                    logger.info("Added for enrollment")
                    self.course.status_text = "Added for Enrollment"
                    self.course.status_color = "#2ECC71"

                if final_slug:
                    self.processed_slugs.add(final_slug)
                if slug and slug != final_slug:
                    self.processed_slugs.add(slug)

                self.update_progress()
                if len(self.valid_courses) >= 5:
                    try:
                        self.bulk_checkout()
                    except Exception as e:
                        logger.error(
                            f"Bulk checkout failed: {e}. Falling back to individual course enrollment...")
                        self.individual_checkout_fallback(self.valid_courses)
                    self.valid_courses.clear()
            self.update_progress()

        if self.valid_courses and not getattr(self, "cancelled", False):
            try:
                self.bulk_checkout()
            except Exception as e:
                logger.error(
                    f"Bulk checkout failed: {e}. Falling back to individual course enrollment...")
                self.individual_checkout_fallback(self.valid_courses)
            self.valid_courses.clear()
        logger.info("Enrollment process completed")
        logger.info(
            f"Successfully Enrolled: {self.successfully_enrolled_c}\nAlready Enrolled: {self.already_enrolled_c}\nExpired: {self.expired_c}\nExcluded: {self.excluded_c}"
        )
        self.send_discord_alert()
        if hasattr(self, "txt_file") and self.txt_file and not self.txt_file.closed:
            try:
                self.txt_file.flush()
                self.txt_file.close()
                self.txt_file = None
            except Exception as e:
                logger.error(f"Error closing course log file: {e}")

    def setup_txt_file(self):
        if self.settings["save_txt"]:
            try:
                if hasattr(self, "txt_file") and self.txt_file and not self.txt_file.closed:
                    self.txt_file.flush()
                    self.txt_file.close()
            except Exception as e:
                logger.error(f"Error closing previous course log file: {e}")
            os.makedirs("Courses/", exist_ok=True)
            self.txt_file = open(
                f"Courses/{time.strftime('%Y-%m-%d--%H-%M')}.txt", "w", encoding="utf-8"
            )

    def bulk_checkout(self):
        logger.info("Enrolling in courses...")
        items = []
        for course in self.valid_courses:
            if not course.is_free:
                items.append(
                    {
                        "buyable": {"id": str(course.course_id), "type": "course"},
                        "discountInfo": {"code": course.coupon_code},
                        "price": {"amount": 0, "currency": self.currency.upper()},
                    }
                )
        if not items:
            logger.error("No courses to enroll in")
            return

        payload = {
            "checkout_environment": "Marketplace",
            "checkout_event": "Submit",
            "payment_info": {
                "method_id": "0",
                "payment_method": "free-method",
                "payment_vendor": "Free",
            },
            "shopping_info": {"items": items, "is_cart": True},
        }
        headers = {
            "User-Agent": "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US",
            "Referer": "https://www.udemy.com/payment/checkout/",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "x-checkout-is-mobile-app": "false",
            "Origin": "https://www.udemy.com",
            "Host": "www.udemy.com",
            "DNT": "1",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0",
            "X-CSRF-Token": self.cookie_dict.get("csrftoken", self.cookie_dict.get("csrf_token", "")),
        }

        last_error = "Unknown bulk checkout error"
        for attempt in range(3):
            try:
                r = self.client.post(
                    "https://www.udemy.com/payment/checkout-submit/",
                    json=payload,
                    headers=headers,
                    timeout=30
                )

                retry_after = r.headers.get("retry-after")
                if retry_after:
                    try:
                        wait_sec = int(retry_after)
                    except ValueError:
                        wait_sec = 30
                    logger.warning(
                        f"Rate limited during bulk checkout. Waiting {wait_sec} seconds...")
                    time.sleep(wait_sec)
                    continue

                if r.status_code == 504:
                    r_data = {"status": "succeeded",
                              "message": "Request Timeout"}
                else:
                    r_data = r.json()
            except Exception as e:
                last_error = f"Request failed: {str(e)}"
                logger.warning(
                    f"Bulk checkout attempt {attempt + 1} failed: {e}")
                time.sleep(5 + attempt)
                continue

            if isinstance(r_data, dict) and r_data.get("status") == "succeeded":
                for course in self.valid_courses:
                    self.course = course
                    now_time = self.get_now_to_utc()
                    self.enrolled_courses[self.course.slug] = now_time
                    db.save_enrolled_courses({self.course.slug: now_time})
                    self.amount_saved_c += (
                        Decimal(str(course.price))
                        if course.price is not None
                        else Decimal(0)
                    )
                    self.successfully_enrolled_c += 1
                    self.save_course()
                logger.success(
                    f"Successfully Enrolled To {len(self.valid_courses)} Courses :)")
                return

            last_error = f"API returned error: {r_data}"
            logger.error(
                f"Bulk checkout failed attempt {attempt + 1}: {r_data}, Retrying...")
            self.client.get(
                "https://www.udemy.com/payment/checkout/", headers=headers, timeout=15)
            time.sleep(5 + attempt)

        raise Exception(
            f"Bulk checkout failed after 3 attempts. Last error: {last_error}")

    def individual_checkout_fallback(self, courses: list[Course]):
        logger.info(
            f"Starting individual fallback checkout for {len(courses)} courses")

        def checkout_single(course: Course):
            logger.info(f"Individually checkout fallback for: {str(course)}")
            try:
                if course.is_free:
                    self.free_checkout(course)
                    if course.status:
                        logger.success(
                            f"Successfully Subscribed: {course.title}")
                        now_time = self.get_now_to_utc()
                        with self.stats_lock:
                            self.enrolled_courses[course.slug] = now_time
                            db.save_enrolled_courses({course.slug: now_time})
                            self.successfully_enrolled_c += 1
                            self.save_course(course)
                    else:
                        logger.error(
                            f"Fallback free checkout failed for: {course.title}")
                        with self.stats_lock:
                            self.expired_c += 1
                else:
                    self.single_discounted_checkout(course)
            except Exception as e:
                logger.error(
                    f"Fallback checkout failed for {course.title}: {e}")
                with self.stats_lock:
                    self.expired_c += 1
            self.update_progress()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(checkout_single, courses))

    def single_discounted_checkout(self, course: Course):
        payload = {
            "checkout_environment": "Marketplace",
            "checkout_event": "Submit",
            "payment_info": {
                "method_id": "0",
                "payment_method": "free-method",
                "payment_vendor": "Free",
            },
            "shopping_info": {
                "items": [
                    {
                        "buyable": {"id": str(course.course_id), "type": "course"},
                        "discountInfo": {"code": course.coupon_code},
                        "price": {"amount": 0, "currency": self.currency.upper()},
                    }
                ],
                "is_cart": False,
            },
        }
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US",
            "Referer": f"https://www.udemy.com/payment/checkout/express/course/{course.course_id}/?discountCode={course.coupon_code}",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "x-checkout-is-mobile-app": "true",
            "Origin": "https://www.udemy.com",
            "DNT": "1",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=0",
        }
        for attempt in range(3):
            r = self.client.post(
                "https://www.udemy.com/payment/checkout-submit/",
                json=payload,
                headers=headers,
                timeout=15,
            )
            retry_after = r.headers.get("retry-after")
            if retry_after:
                try:
                    wait_sec = int(retry_after)
                except ValueError:
                    wait_sec = 30
                logger.warning(
                    f"Rate limited by Udemy during single checkout. Waiting {wait_sec} seconds...")
                time.sleep(wait_sec)
                continue

            try:
                res = r.json()
            except Exception as e:
                logger.error(
                    f"Failed to parse single checkout JSON response: {e}")
                continue

            status = res.get("status") if isinstance(res, dict) else None
            if status == "succeeded":
                logger.success(
                    f"Successfully Enrolled (Fallback): {course.title}")
                now_time = self.get_now_to_utc()
                with self.stats_lock:
                    self.enrolled_courses[course.slug] = now_time
                    db.save_enrolled_courses({course.slug: now_time})
                    self.amount_saved_c += (
                        Decimal(str(course.price))
                        if course.price is not None
                        else Decimal(0)
                    )
                    self.successfully_enrolled_c += 1
                    self.save_course(course)
                return
            elif status == "failed" or (isinstance(res, dict) and "message" in res):
                message = res.get("message", "") if isinstance(res, dict) else ""
                if "item_already_subscribed" in message or "already_enrolled" in message:
                    logger.info(f"Already enrolled in: {course.title}")
                    with self.stats_lock:
                        self.already_enrolled_c += 1
                    return
                else:
                    logger.error(f"Single checkout failed: {message}")

            time.sleep(2)
        else:
            logger.error(
                f"Failed single checkout for {course.title} after 3 attempts")
            with self.stats_lock:
                self.expired_c += 1

    def free_checkout(self, course: Course = None):
        if course is None:
            course = self.course
        self.client.get(
            f"https://www.udemy.com/course/subscribe/?courseId={course.course_id}",
            timeout=15
        )
        r = self.client.get(
            f"https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private",
            timeout=15
        )

        retry_after = r.headers.get("retry-after")
        if retry_after:
            try:
                wait_sec = int(retry_after)
            except ValueError:
                wait_sec = 30
            logger.warning(
                f"Rate limited by Udemy during free checkout. Waiting {wait_sec} seconds...")
            time.sleep(wait_sec)
            raise Exception(
                f"Rate limited by Udemy during free checkout. Wait time requested: {wait_sec} seconds")
        if r.status_code == 503:
            logger.error(r.text)
            course.status = True
            return
        r = r.json()
        course.status = r.get("_class") == "course"

    def cleanup(self):
        """Clean up open resources, close connection pools, and flush log files"""
        logger.info("Cleaning up Udemy client resources")
        try:
            if hasattr(self, "txt_file") and self.txt_file and not self.txt_file.closed:
                self.txt_file.flush()
                self.txt_file.close()
                logger.debug("Closed course log file")
        except Exception as e:
            logger.error(f"Error closing course log file: {e}")

        try:
            if hasattr(self, "client") and self.client:
                self.client.close()
                logger.debug("Closed client HTTP session")
        except Exception as e:
            logger.error(f"Error closing client HTTP session: {e}")

    def send_discord_alert(self):
        webhook_url = self.settings.get("discord_webhook_url", "").strip()
        if not webhook_url:
            return

        logger.info("Sending Discord webhook alert...")
        payload = {
            "username": "DUCE Bot",
            "avatar_url": "https://raw.githubusercontent.com/techtanic/Discounted-Udemy-Course-Enroller/main/extra/DUCE-LOGO.png",
            "embeds": [
                {
                    "title": "📚 Enrollment Run Completed!",
                    "color": 5763719,  # Green
                    "description": "Discounted-Udemy-Course-Enroller has finished processing.",
                    "fields": [
                        {
                            "name": "✅ Successfully Enrolled",
                            "value": f"{self.successfully_enrolled_c} courses",
                            "inline": True
                        },
                        {
                            "name": "💰 Total Amount Saved",
                            "value": f"{round(self.amount_saved_c, 2)} {self.currency.upper()}",
                            "inline": True
                        },
                        {
                            "name": "🎓 Already Enrolled",
                            "value": f"{self.already_enrolled_c} courses",
                            "inline": True
                        },
                        {
                            "name": "❌ Expired / Invalid",
                            "value": f"{self.expired_c} courses",
                            "inline": True
                        },
                        {
                            "name": "🚫 Excluded",
                            "value": f"{self.excluded_c} courses",
                            "inline": True
                        }
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {
                        "text": "Made with 🩷 by techtanic"
                    }
                }
            ]
        }
        try:
            r = requests.post(webhook_url, json=payload, timeout=15)
            if r.status_code in (200, 204):
                logger.success("Discord webhook alert sent successfully!")
            else:
                logger.error(
                    f"Discord webhook returned status code: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"Failed to send Discord webhook alert: {e}")
