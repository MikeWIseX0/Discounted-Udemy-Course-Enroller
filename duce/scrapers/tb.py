import concurrent.futures
from loguru import logger
from duce.core.config import SCRAPER_URLS


def scrape_tb(scraper):
    code_name = "tb"
    try:
        all_items = []
        scraper.set_attr(code_name, "length", 5)
        base_url = SCRAPER_URLS.get("tb", "https://www.tutorialbar.com")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/wp-json/wp/v2/posts?categories=55&per_page=100&page={page}",
                )
                for page in range(1, 6)
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                try:
                    result = future.result()
                    if result is not None and result.status_code == 403 and ("account suspensed" in result.text.lower() or "access denied" in result.text.lower()):
                        logger.warning(
                            "Tutorial Bar website hosting account is suspended or blocked by its provider (Hostinger). Skipping Tutorial Bar.")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    if result is None or result.status_code != 200:
                        status = "failed" if result is None else f"status {result.status_code}"
                        logger.warning(
                            f"Tutorial Bar page request failed ({status})")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    try:
                        content = result.json()
                        if isinstance(content, list):
                            all_items.extend(content)
                        else:
                            logger.warning(
                                "Tutorial Bar response content is not a JSON list")
                    except Exception as json_err:
                        logger.warning(
                            f"Failed to parse Tutorial Bar JSON: {json_err}")
                except Exception as e:
                    logger.error(f"Error fetching page in Tutorial Bar: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

        scraper.set_attr(code_name, "length", len(all_items))

        for i, item in enumerate(all_items):
            try:
                title = item["title"]["rendered"]
                link = item["acf"]["course_url"]
                if link and "www.udemy.com" in link:
                    scraper.append_to_list(title, link, code_name)
            except Exception as e:
                logger.error(f"Error parsing Tutorial Bar post: {e}")
            scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
