# flake8: noqa
# base.py Facade - Discounted Udemy Course Enroller
# Re-exposes public classes, functions, and variables from the modular duce package
# to maintain complete compatibility with gui.py, cli.py, spec files, and external scripts.

from loguru import logger

from duce.core.config import (
    VERSION,
    scraper_dict,
    LINKS,
    get_user_data_path,
    resource_path,
    SCRAPER_URLS,
    get_scraper_headers
)
from duce.core.exceptions import LoginException
from duce.core.models import Course
from duce.core.client import Udemy
from duce.scrapers.base_scraper import Scraper
from duce.utils.html import parse_html
from duce.utils.url import cleanup_link
