import time
import threading
import traceback
from loguru import logger
from duce.core.config import scraper_dict
from duce.core.models import Course
from duce.utils.network import fetch_page
from duce.utils.html import parse_html
from duce.utils.url import cleanup_link

from duce.scrapers.rd import scrape_rd
from duce.scrapers.cxyz import scrape_cxyz
from duce.scrapers.idc import scrape_idc
from duce.scrapers.fwc import scrape_fwc
from duce.scrapers.en import scrape_en
from duce.scrapers.du import scrape_du
from duce.scrapers.uf import scrape_uf
from duce.scrapers.cj import scrape_cj
from duce.scrapers.cv import scrape_cv
from duce.scrapers.cs import scrape_cs

scraper_funcs = {
    "rd": scrape_rd,
    "cxyz": scrape_cxyz,
    "idc": scrape_idc,
    "fwc": scrape_fwc,
    "en": scrape_en,
    "du": scrape_du,
    "uf": scrape_uf,
    "cj": scrape_cj,
    "cv": scrape_cv,
    "cs": scrape_cs,
}


class Scraper:
    """
    Registry class that provides backward compatibility for Scraper calls.
    Delegates site-specific scraping to modular scraper functions.
    """

    def __init__(self, site_to_scrape: list = None, debug: bool = False):
        self.sites = site_to_scrape if site_to_scrape is not None else list(
            scraper_dict.keys())
        self.debug = debug
        for site in self.sites:
            code_name = scraper_dict[site]
            setattr(self, f"{code_name}_length", 0)
            setattr(self, f"{code_name}_data", [])
            setattr(self, f"{code_name}_done", False)
            setattr(self, f"{code_name}_progress", 0)
            setattr(self, f"{code_name}_error", "")

            # Dynamically bind the scraper method to this instance
            method = self._get_scraper_method(code_name)
            setattr(self, code_name, method)

    def _get_scraper_method(self, code_name):
        def run_scraper():
            try:
                scrape_func = scraper_funcs[code_name]
                scrape_func(self)
            except Exception:
                self.handle_exception(code_name)
        return run_scraper

    def get_scraped_courses(self, target: object) -> list:
        logger.info(f"Starting scrape for sites: {self.sites}")
        threads = []
        scraped_data = set()
        for site in self.sites:
            logger.info(f"Scraping site: {site}")
            t = threading.Thread(
                target=target,
                args=(site,),
                daemon=True,
            )
            t.start()
            threads.append(t)
            time.sleep(0.2)
        for t in threads:
            t.join()
        logger.info("All scraping threads completed, combining results")
        for site in self.sites:
            courses: list[Course] = getattr(self, f"{scraper_dict[site]}_data")
            for course in courses:
                course.site = site
                scraped_data.add(course)

        logger.info(
            f"Scraping finished. Found {len(scraped_data)} unique courses.")
        return list(scraped_data)

    def append_to_list(self, title: str, link: str, code_name: str):
        target = getattr(self, f"{code_name}_data")
        course = Course(title, link)
        target.append(course)

    def fetch_page(self, url: str, headers: dict = None):
        import random
        # Pacing: sleep random delay between 0.8 and 2.0 seconds
        delay = random.uniform(0.8, 2.0)
        logger.debug(f"Pacing request to {url} - sleeping for {delay:.2f}s")
        time.sleep(delay)
        return fetch_page(url, headers)

    def parse_html(self, content: str):
        return parse_html(content)

    def set_attr(self, code_name: str, attr: str, value):
        setattr(self, f"{code_name}_{attr}", value)

    def handle_exception(self, code_name: str):
        logger.exception(f"An error occurred in scraper: {code_name}")
        error_trace = traceback.format_exc()
        setattr(self, f"{code_name}_error", error_trace)
        setattr(self, f"{code_name}_length", -1)
        setattr(self, f"{code_name}_done", True)

    def cleanup_link(self, link: str) -> str:
        return cleanup_link(link)
