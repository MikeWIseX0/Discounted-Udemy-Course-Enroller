from bs4 import BeautifulSoup as bs
from loguru import logger


def parse_html(content: str):
    """Parses HTML content with lxml parser and falls back to html.parser if needed."""
    try:
        return bs(content, "lxml")
    except Exception as e:
        logger.warning(f"lxml parser failed: {e}. Falling back to html.parser")
        return bs(content, "html.parser")
