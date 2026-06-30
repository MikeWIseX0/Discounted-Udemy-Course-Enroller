import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
import requests

from duce.scrapers.du import scrape_du
from duce.scrapers.cj import scrape_cj
from duce.scrapers.uf import scrape_uf


class MockResponse:
    def __init__(self, content, status_code=200, headers=None):
        self.content = content
        self.text = content.decode("utf-8") if isinstance(content, bytes) else str(content)
        self.status_code = status_code
        self.headers = headers or {}
        self.url = "https://www.udemy.com/course/mock-url/"

    def json(self):
        import json
        return json.loads(self.text)


class TestScrapersOffline(unittest.TestCase):
    def setUp(self):
        # Create a mock Scraper object
        self.scraper = MagicMock()
        self.scraper.sites = []
        self.scraper.scraped_list = []
        
        # Setup append_to_list mock to collect values
        def mock_append(title, link, code):
            self.scraper.scraped_list.append({"title": title, "link": link, "code": code})
        self.scraper.append_to_list.side_effect = mock_append
        self.scraper.parse_html = lambda c: BeautifulSoup(c, "html.parser")
        self.scraper.cleanup_link = lambda l: l

    def test_discudemy_scraper_parsing(self):
        # Simulated main list page HTML containing card-headers
        main_page_html = b"""
        <html>
            <body>
                <a class="card-header" href="https://www.discudemy.com/all/test-course-slug">Test Course Title</a>
            </body>
        </html>
        """
        
        # Simulated details page HTML containing the actual udemy link
        details_page_html = b"""
        <html>
            <body>
                <div class="ui segment">
                    <a href="https://www.udemy.com/course/test-course-slug/?couponCode=FREE100">Take Course</a>
                </div>
            </body>
        </html>
        """

        # Set up fetch_page mock to return main page, then details page
        def mock_fetch(url, headers=None):
            if "all/" in url:
                return MockResponse(main_page_html)
            elif "go/" in url:
                return MockResponse(details_page_html)
            return None

        self.scraper.fetch_page.side_effect = mock_fetch

        # Run scraper
        scrape_du(self.scraper)

        # Assert results
        self.assertEqual(len(self.scraper.scraped_list), 10)
        self.assertEqual(self.scraper.scraped_list[0]["title"], "Test Course Title")
        self.assertEqual(self.scraper.scraped_list[0]["link"], "https://www.udemy.com/course/test-course-slug/?couponCode=FREE100")
        self.assertEqual(self.scraper.scraped_list[0]["code"], "du")

    def test_course_joiner_scraper_parsing(self):
        # Simulated WordPress REST API JSON response list
        wp_api_json = """
        [
            {
                "title": {"rendered": "Python Programming Course"},
                "content": {"rendered": "<a href='https://www.udemy.com/course/python-course/?couponCode=JOINFREE'>APPLY HERE</a>"}
            }
        ]
        """

        # Set up fetch_page mock
        def mock_fetch(url, headers=None):
            if "posts" in url:
                return MockResponse(wp_api_json.encode("utf-8"))
            return None

        self.scraper.fetch_page.side_effect = mock_fetch

        # Run scraper
        scrape_cj(self.scraper)

        # Assert results
        self.assertEqual(len(self.scraper.scraped_list), 4)
        self.assertEqual(self.scraper.scraped_list[0]["title"], "Python Programming Course")
        self.assertEqual(self.scraper.scraped_list[0]["link"], "https://www.udemy.com/course/python-course/?couponCode=JOINFREE")
        self.assertEqual(self.scraper.scraped_list[0]["code"], "cj")

    @patch("duce.scrapers.uf.session")
    def test_udemy_freebies_scraper_parsing(self, mock_session):
        # Simulated main page HTML containing course cards
        main_page_html = b"""
        <html>
            <body>
                <a class="theme-img" href="https://www.udemyfreebies.com/free-udemy-course/test-freebie-course">
                    <img alt="Details"/>
                </a>
            </body>
        </html>
        """

        # Set up fetch_page mock
        self.scraper.fetch_page.return_value = MockResponse(main_page_html)
        
        # Set up requests session mock to return redirect headers
        mock_session.get.return_value = MockResponse(
            b"", status_code=302, headers={"Location": "https://www.udemy.com/course/test-freebie-course/?couponCode=FREEBIE"}
        )

        # Run scraper
        scrape_uf(self.scraper)

        # Assert results
        self.assertEqual(len(self.scraper.scraped_list), 5)
        self.assertEqual(self.scraper.scraped_list[0]["title"], "Details")
        self.assertEqual(self.scraper.scraped_list[0]["link"], "https://www.udemy.com/course/test-freebie-course/?couponCode=FREEBIE")
        self.assertEqual(self.scraper.scraped_list[0]["code"], "uf")


if __name__ == "__main__":
    unittest.main()
