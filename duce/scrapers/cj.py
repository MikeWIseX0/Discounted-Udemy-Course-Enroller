import concurrent.futures
# pyrefly: ignore [missing-import]
from loguru import logger
from html import unescape


def scrape_cj(scraper):
    code_name = "cj"
    try:
        scraper.set_attr(code_name, "length", 4)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Sec-GPC": "1",
            "Alt-Used": "www.coursejoiner.com",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Priority": "u=4",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"https://www.coursejoiner.com/wp-json/wp/v2/posts?categories=1000&per_page=100&page={page}",
                    headers=headers,
                )
                for page in range(1, 5)
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                try:
                    result = future.result()
                    if result is None or result.status_code != 200:
                        status = "failed" if result is None else f"status {result.status_code}"
                        logger.warning(
                            f"Course Joiner page request failed ({status})")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    try:
                        content = result.json()
                    except Exception as json_err:
                        logger.warning(
                            f"Failed to parse Course Joiner JSON: {json_err}")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    if not content:
                        logger.debug("No more coupons")
                        break
                    if not isinstance(content, list):
                        logger.warning(
                            f"Invalid Course Joiner response format: expected list, got {type(content)}")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    for item in content:
                        try:
                            title = unescape(item["title"]["rendered"])
                            title = (
                                title.replace("–", "-")
                                .strip()
                                .removesuffix("- (Free Course)")
                                .strip()
                            )
                            rendered_content = item["content"]["rendered"]
                            soup = scraper.parse_html(rendered_content)
                            link = soup.find("a", string="APPLY HERE")

                            if link and link.has_attr("href"):
                                link = link["href"]
                                if "udemy.com" in link:
                                    scraper.append_to_list(
                                        title, link, code_name)
                        except Exception as item_e:
                            logger.error(
                                f"Error parsing Course Joiner post item: {item_e}")
                except Exception as page_e:
                    logger.error(
                        f"Error resolving Course Joiner page future: {page_e}")
                scraper.set_attr(code_name, "progress", i + 1)

    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
