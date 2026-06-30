from urllib.parse import parse_qs, unquote, urlparse, urlunparse
from loguru import logger


def cleanup_link(link: str) -> str:
    """
    Cleans and resolves affiliate redirect links to direct udemy.com links.
    Handles linksynergy, trk.udemy.com, and recursively extracts any embedded udemy links in query parameters.
    """
    if not link or not isinstance(link, str):
        return ""
    try:
        parsed_url = urlparse(link)
        domain = parsed_url.netloc.lower()

        # If it's already a direct udemy link, return it
        if domain == "www.udemy.com" or domain == "udemy.com":
            return link

        # Linksynergy affiliate redirect
        if domain == "click.linksynergy.com":
            query_params = parse_qs(parsed_url.query)
            if "RD_PARM1" in query_params:
                return cleanup_link(unquote(query_params["RD_PARM1"][0]))
            elif "murl" in query_params:
                return cleanup_link(unquote(query_params["murl"][0]))
            else:
                logger.warning(f"Unknown LinkSynergy format: {link}")
                return link

        # trk.udemy.com affiliate redirect
        if domain == "trk.udemy.com":
            query_params = parse_qs(parsed_url.query)
            if "u" in query_params:
                return cleanup_link(unquote(query_params["u"][0]))
            else:
                logger.warning(f"Unknown trk.udemy.com format: {link}")
                return link

        # Generic redirect extraction (recursively check all query parameter values for udemy.com)
        query_params = parse_qs(parsed_url.query)
        for val_list in query_params.values():
            for val in val_list:
                if "udemy.com" in val:
                    return cleanup_link(unquote(val))

    except Exception as e:
        logger.error(f"Error cleaning up link {link}: {e}")

    return link


def normalize_link(url: str) -> str:
    parsed_url = urlparse(url)
    path = (
        parsed_url.path if parsed_url.path.endswith(
            "/") else parsed_url.path + "/"
    )
    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )
