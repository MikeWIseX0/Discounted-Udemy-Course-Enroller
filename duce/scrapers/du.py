import concurrent.futures
from loguru import logger
from duce.core.config import SCRAPER_URLS, get_scraper_headers


def scrape_du(scraper):
    code_name = "du"
    try:
        all_items = []
        base_url = SCRAPER_URLS["du"]
        head = get_scraper_headers()
        head["referer"] = base_url

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/all/{page}",
                    headers=head,
                )
                for page in range(1, 11)
            ]
            scraper.set_attr(code_name, "length", 11)

            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                try:
                    result = future.result()
                    if result is None or result.status_code != 200:
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    content = result.content
                    soup = scraper.parse_html(content)
                    page_items = soup.find_all("a", {"class": "card-header"})
                    all_items.extend(page_items)
                except Exception as e:
                    logger.error(f"Error fetching page in Discudemy: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

            scraper.set_attr(code_name, "length", len(all_items))

        def _fetch_course_details(item, headers):
            """Helper method to fetch course details"""
            try:
                title = item.string or "Discudemy Course"
                href = item.get("href")
                if not href:
                    return title, ""
                from urllib.parse import urlparse
                path_segments = [seg for seg in urlparse(href).path.split("/") if seg]
                if not path_segments:
                    return title, ""
                url = path_segments[-1]
                result = scraper.fetch_page(
                    f"{base_url}/go/{url}", headers=headers
                )
                if result is None or result.status_code != 200:
                    return title, ""
                soup = scraper.parse_html(result.content)
                div = soup.find("div", {"class": "ui segment"})
                link = div.a.get("href") if (div and div.a) else ""
                return title, link
            except Exception as e:
                logger.error(f"Error parsing Discudemy details: {e}")
                return "Discudemy Course", ""

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_course_details = [
                executor.submit(_fetch_course_details, item, head)
                for item in all_items
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_course_details)
            ):
                try:
                    title, link = future.result()
                    if link and "udemy.com" in link:
                        link = scraper.cleanup_link(link)
                        scraper.append_to_list(title, link, code_name)
                except Exception as e:
                    logger.error(f"Error resolving Discudemy course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
