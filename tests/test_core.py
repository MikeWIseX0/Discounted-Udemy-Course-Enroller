import os
import unittest
from duce.core.models import Course
from duce.core.db import DatabaseManager


class TestCourseModel(unittest.TestCase):
    def test_cleanup_link(self):
        from duce.utils.url import cleanup_link
        # Test standard trk.udemy.com with "u"
        url_u = "https://trk.udemy.com/c/123/456/789?u=https://www.udemy.com/course/python-course/"
        self.assertEqual(cleanup_link(url_u), "https://www.udemy.com/course/python-course/")

        # Test trk.udemy.com with "url"
        url_url = "https://trk.udemy.com/c/123/456/789?url=https://www.udemy.com/course/python-course-2/"
        self.assertEqual(cleanup_link(url_url), "https://www.udemy.com/course/python-course-2/")

        # Test trk.udemy.com with fallback scan of other parameters
        url_other = "https://trk.udemy.com/c/123/456/789?custom_param=https://www.udemy.com/course/python-course-3/"
        self.assertEqual(cleanup_link(url_other), "https://www.udemy.com/course/python-course-3/")

        # Test Linksynergy
        url_ls = "https://click.linksynergy.com/fs-bin/click?id=123&offerid=456&type=3&subid=0&RD_PARM1=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Fpython-course-4%2F"
        self.assertEqual(cleanup_link(url_ls), "https://www.udemy.com/course/python-course-4/")

        # Test short trk.udemy.com redirect path
        url_short = "https://trk.udemy.com/zzRbN0/"
        self.assertEqual(cleanup_link(url_short), "https://trk.udemy.com/zzRbN0/")

    def test_url_normalization_and_slug(self):
        url = "https://www.udemy.com/course/python-programming-for-beginners/?couponCode=FREEPYTHON"
        course = Course("Python Course", url)
        self.assertEqual(course.slug, "python-programming-for-beginners")
        self.assertEqual(course.coupon_code, "FREEPYTHON")
        self.assertTrue(course.is_valid)

    def test_recursive_metadata_parsing(self):
        # Sample simulated nested data-module-args dict with direct path matching
        dma_direct = {
            "serverSideProps": {
                "course": {
                    "instructors": {
                        "instructors_info": [
                            {"absolute_url": "/user/john-doe-4/"}
                        ]
                    },
                    "localeSimpleEnglishTitle": "English",
                    "rating": 4.6,
                    "lastUpdateDate": "2026-06-19",
                    "isPaid": False
                },
                "topicMenu": {
                    "breadcrumbs": [
                        {"title": "Development"}
                    ]
                }
            }
        }
        course = Course(
            "Test Course", "https://www.udemy.com/course/test-slug/")
        course.set_metadata(dma_direct)
        self.assertTrue(course.is_valid)
        self.assertEqual(course.instructors, ["john-doe-4"])
        self.assertEqual(course.language, "English")
        self.assertEqual(course.category, "Development")
        self.assertEqual(course.rating, 4.6)
        self.assertEqual(course.last_update, "2026-06-19")
        self.assertTrue(course.is_free)

    def test_recursive_metadata_parsing_fallback(self):
        # Sample restructured/altered nested data-module-args dict
        dma_altered = {
            "someRandomNest": {
                "instructors_info": [
                    {"absolute_url": "/user/jane-smith-9/"}
                ],
                "localeSimpleEnglishTitle": "Spanish",
                "breadcrumbs": [
                    {"title": "Business"}
                ],
                "rating": 4.8,
                "lastUpdateDate": "2026-05-10",
                "isPaid": True
            }
        }
        course = Course("Test Course Altered",
                        "https://www.udemy.com/course/altered-slug/")
        course.set_metadata(dma_altered)
        self.assertTrue(course.is_valid)
        self.assertEqual(course.instructors, ["jane-smith-9"])
        self.assertEqual(course.language, "Spanish")
        self.assertEqual(course.category, "Business")
        self.assertEqual(course.rating, 4.8)
        self.assertEqual(course.last_update, "2026-05-10")
        self.assertFalse(course.is_free)


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        from duce.core.config import get_user_data_path
        self.db_file = get_user_data_path("test_duce.db")
        if os.path.exists(self.db_file):
            try:
                os.remove(self.db_file)
            except Exception:
                pass
        self.db = DatabaseManager("test_duce.db")

    def tearDown(self):
        if hasattr(self, "db_file") and os.path.exists(self.db_file):
            try:
                os.remove(self.db_file)
            except Exception:
                pass

    def test_schema_initialization(self):
        # Verify tables exist
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        self.assertIn("enrolled_courses", tables)
        self.assertIn("validation_cache", tables)
        self.assertIn("db_metadata", tables)
        conn.close()

    def test_save_and_get_enrolled_courses(self):
        courses = {"python-slug": "2026-06-19T23:00:00Z"}
        self.db.save_enrolled_courses(courses)
        result = self.db.get_enrolled_courses()
        self.assertIn("python-slug", result)
        self.assertEqual(result["python-slug"], "2026-06-19T23:00:00Z")

    def test_validation_cache_ttl(self):
        # Create a mock course details object
        course = Course("Test TTL Course",
                        "https://www.udemy.com/course/ttl-slug/")
        course.course_id = "ttl123"
        course.coupon_code = "TTLCODE"
        course.is_valid = True

        # Save it
        self.db.save_validation(course)

        # Verify it exists in cache
        cached = self.db.get_validation("ttl-slug", "TTLCODE")
        self.assertIsNotNone(cached)
        self.assertTrue(cached["is_valid"])

        # Manually alter the cached_at timestamp in SQLite to 8 days ago
        import datetime
        eight_days_ago = (datetime.datetime.now(
            datetime.timezone.utc) - datetime.timedelta(days=8)).isoformat()

        conn1 = self.db._get_connection()
        try:
            with conn1:
                cursor = conn1.cursor()
                cursor.execute("UPDATE validation_cache SET cached_at = ? WHERE slug = ? AND coupon_code = ?",
                               (eight_days_ago, "ttl-slug", "TTLCODE"))
        finally:
            conn1.close()

        # Retrieve again - it should be expired (return None) and deleted
        cached_expired = self.db.get_validation("ttl-slug", "TTLCODE")
        self.assertIsNone(cached_expired)

        # Confirm it's gone from database entirely
        conn2 = self.db._get_connection()
        try:
            cursor = conn2.cursor()
            cursor.execute("SELECT COUNT(*) FROM validation_cache WHERE slug = ? AND coupon_code = ?",
                           ("ttl-slug", "TTLCODE"))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn2.close()


class TestUdemyClientSettings(unittest.TestCase):
    def test_validate_settings(self):
        from duce.core.client import Udemy

        # Instantiate Udemy in cli or gui mode
        client = Udemy("cli")

        # Set up mock settings
        client.settings = {
            "sites": {"Real Discount": True},
            "categories": {"Development": True},
            "languages": {"English": True},
            "instructor_exclude": [],
            "title_exclude": [],
            "min_rating": 0.0,
            "course_update_threshold_months": 12,
            "save_txt": False
        }

        # Validation should succeed (return False, because "not all" is False when all are true)
        self.assertFalse(client.validate_settings())
        self.assertEqual(client.sites, ["Real Discount"])
        self.assertEqual(client.categories, ["Development"])
        self.assertEqual(client.languages, ["English"])

        # Test failure case (empty sites)
        client.settings["sites"] = {"Real Discount": False}
        # Returns True (is invalid)
        self.assertTrue(client.validate_settings())

    def test_network_timeout_enforcement(self):
        from duce.utils.network import RobustRequestsSession, RobustCffiSession, use_cffi
        from unittest.mock import patch, MagicMock

        # Test RobustRequestsSession
        session_req = RobustRequestsSession()
        session_req.network_timeout = 75

        with patch('requests.Session.request') as mock_req:
            mock_req.return_value = MagicMock()
            
            # Case 1: No timeout passed
            session_req.get("https://example.com")
            kwargs = mock_req.call_args[1]
            self.assertEqual(kwargs["timeout"], 75)

            # Case 2: Smaller timeout passed
            session_req.get("https://example.com", timeout=10)
            kwargs = mock_req.call_args[1]
            self.assertEqual(kwargs["timeout"], 75)

            # Case 3: Larger timeout passed
            session_req.get("https://example.com", timeout=100)
            kwargs = mock_req.call_args[1]
            self.assertEqual(kwargs["timeout"], 100)

            # Case 4: Tuple timeout passed
            session_req.get("https://example.com", timeout=(5, 10))
            kwargs = mock_req.call_args[1]
            self.assertEqual(kwargs["timeout"], (75, 75))

        # Test RobustCffiSession if cffi is used
        if use_cffi:
            session_cffi = RobustCffiSession()
            session_cffi.network_timeout = 85
            with patch('curl_cffi.requests.Session.request') as mock_cffi_req:
                mock_cffi_req.return_value = MagicMock()
                
                # Case 1: No timeout passed
                session_cffi.get("https://example.com")
                kwargs = mock_cffi_req.call_args[1]
                self.assertEqual(kwargs["timeout"], 85)

                # Case 2: Smaller timeout passed
                session_cffi.get("https://example.com", timeout=12)
                kwargs = mock_cffi_req.call_args[1]
                self.assertEqual(kwargs["timeout"], 85)


if __name__ == "__main__":
    unittest.main()
