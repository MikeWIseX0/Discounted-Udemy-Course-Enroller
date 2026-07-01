from bs4 import BeautifulSoup as bs
from loguru import logger


def parse_html(content: str):
    """Parses HTML content with built-in html.parser."""
    return bs(content, "html.parser")
