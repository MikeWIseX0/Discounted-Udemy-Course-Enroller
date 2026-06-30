import traceback
from loguru import logger
from urllib.parse import parse_qs, urlparse, urlsplit
from duce.utils.url import cleanup_link, normalize_link


class Course:
    def __init__(self, title: str, url: str, site: str = None):
        self.title = title
        self.site = site
        self.url = None
        self.slug = None
        self.course_id = None
        self.coupon_code = None
        self.is_coupon_valid = False

        self.is_free = False
        self.is_valid = True
        self.is_excluded = False

        self.price = None
        self.instructors = []
        self.language = None
        self.category = None
        self.rating = None
        self.last_update = None

        self.retry = False
        self.retry_after = None
        self.ready_time = None
        self.error: str = None
        self.set_url(url)
        self.extract_coupon_code()

    def set_url(self, url: str):
        """Set course URL, clean affiliate wrappers, and normalize it"""
        cleaned_url = cleanup_link(url)
        self.url = self.normalize_link(cleaned_url)
        self.set_slug()

    @staticmethod
    def normalize_link(url: str) -> str:
        return normalize_link(url)

    def set_slug(self):
        """Set course slug from URL"""
        parsed_url = urlparse(self.url)
        path_parts = parsed_url.path.split("/")
        if len(path_parts) > 2 and path_parts[1] == "course":
            slug = path_parts[2]
        elif len(path_parts) > 1:
            slug = path_parts[1]
        else:
            logger.error(f"Invalid URL format: {self.url}")
            slug = None
        logger.debug(f"Course slug: {slug}")
        self.slug = slug

    def extract_coupon_code(self):
        """Extract coupon code from URL if present"""
        params = parse_qs(urlsplit(self.url).query)
        self.coupon_code = params.get("couponCode", [None])[0]

    def __str__(self):
        return f"{self.title} - {self.url}"

    @staticmethod
    def find_key_recursive(data, key):
        """Recursively search for a key in a dictionary or list structure"""
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for v in data.values():
                res = Course.find_key_recursive(v, key)
                if res is not None:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = Course.find_key_recursive(item, key)
                if res is not None:
                    return res
        return None

    def set_metadata(self, dma):
        """Set course metadata from the data-module-args JSON"""
        try:
            if not isinstance(dma, dict):
                self.is_valid = False
                self.error = "Invalid JSON data structure"
                return

            # Check for view restrictions / limited access
            view_restriction = dma.get("view_restriction") or self.find_key_recursive(
                dma, "view_restriction")
            if view_restriction:
                self.is_valid = False
                limited_access = dma.get(
                    "serverSideProps", {}).get("limitedAccess", {})
                if not limited_access:
                    limited_access = self.find_key_recursive(
                        dma, "limitedAccess") or {}
                self.error = limited_access.get("errorMessage", {}).get(
                    "title", "Limited access restriction")
                return

            # Try direct mapping first (fast and precise)
            try:
                course_data = dma["serverSideProps"]["course"]
                self.instructors = [
                    i["absolute_url"].split("/")[-2]
                    for i in course_data["instructors"]["instructors_info"]
                    if i.get("absolute_url")
                ]
                self.language = course_data["localeSimpleEnglishTitle"]
                self.category = dma["serverSideProps"]["topicMenu"]["breadcrumbs"][0]["title"]
                self.rating = course_data["rating"]
                self.last_update = course_data["lastUpdateDate"]
                self.is_free = not course_data.get("isPaid", True)
                return
            except (KeyError, TypeError) as direct_err:
                logger.debug(
                    f"Direct metadata path failed, falling back to recursive search: {direct_err}")

            # Fallback path-independent recursive search
            # 1. Instructors
            instructors_info = self.find_key_recursive(dma, "instructors_info")
            if instructors_info and isinstance(instructors_info, list):
                self.instructors = [
                    i["absolute_url"].split("/")[-2]
                    for i in instructors_info
                    if isinstance(i, dict) and i.get("absolute_url")
                ]
            else:
                self.instructors = []

            # 2. Language
            self.language = self.find_key_recursive(
                dma, "localeSimpleEnglishTitle")

            # 3. Category
            breadcrumbs = self.find_key_recursive(dma, "breadcrumbs")
            if breadcrumbs and isinstance(breadcrumbs, list) and len(breadcrumbs) > 0:
                self.category = breadcrumbs[0].get("title")
            else:
                self.category = None

            # 4. Rating
            self.rating = self.find_key_recursive(dma, "rating")

            # 5. Last update
            self.last_update = self.find_key_recursive(dma, "lastUpdateDate")

            # 6. Is Free
            is_paid = self.find_key_recursive(dma, "isPaid")
            if is_paid is not None:
                self.is_free = not is_paid
            else:
                price_detail = self.find_key_recursive(dma, "price_detail")
                if price_detail:
                    self.is_free = False
                else:
                    self.is_free = False

        except Exception as e:
            traceback.print_exc()
            self.is_valid = False
            self.error = f"Error parsing course metadata: {str(e)}"

    def __eq__(self, other):
        if not isinstance(other, Course):
            return False
        # Normalize slug and coupon code to ensure case-insensitive, space-insensitive deduplication
        self_slug = str(self.slug).strip().lower() if self.slug else ""
        other_slug = str(other.slug).strip().lower() if other.slug else ""

        self_coupon = str(self.coupon_code).strip(
        ).upper() if self.coupon_code else ""
        other_coupon = str(other.coupon_code).strip(
        ).upper() if other.coupon_code else ""

        return self_slug == other_slug and self_coupon == other_coupon

    def __hash__(self):
        self_slug = str(self.slug).strip().lower() if self.slug else ""
        self_coupon = str(self.coupon_code).strip(
        ).upper() if self.coupon_code else ""
        return hash((self_slug, self_coupon))
