import concurrent.futures
from loguru import logger
from duce.utils.network import session
from duce.core.config import SCRAPER_URLS


def scrape_uf(scraper):
    code_name = "uf"
    try:
        all_items = []
        base_url = SCRAPER_URLS.get("uf", "https://www.udemyfreebies.com")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            scraper.set_attr(code_name, "length", 5)
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/free-udemy-courses/{page}",
                )
                for page in range(1, 6)
            ]
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
                    page_items = soup.find_all("a", {"class": "theme-img"})
                    all_items.extend(page_items)
                except Exception as e:
                    logger.error(f"Error fetching page in Udemy Freebies: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

        def _fetch_course_details(item):
            """Helper method to fetch course details"""
            try:
                title = item.img["alt"] if (item.img and item.img.has_attr(
                    "alt")) else "Udemy Freebies Course"
                href = item.get("href")
                if not href:
                    return title, ""
                from urllib.parse import urlparse
                path_segments = [seg for seg in urlparse(href).path.split("/") if seg]
                if not path_segments:
                    return title, ""
                out_id = path_segments[-1]
                r = session.get(
                    f"{base_url}/out/{out_id}",
                    allow_redirects=False,
                    timeout=10
                )
                link = r.headers.get("Location") or r.url
                return title, link
            except Exception as e:
                logger.error(
                    f"Error fetching course details in uf scraper: {e}")
                return "Udemy Freebies Course", ""

        scraper.set_attr(code_name, "length", len(all_items))

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_course_details = [
                executor.submit(_fetch_course_details, item) for item in all_items
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_course_details)
            ):
                try:
                    title, link = future.result()
                    if link and "udemy.com" in link:
                        link = scraper.cleanup_link(link)
                        scraper.append_to_list(title, link, code_name)
                    elif link:
                        logger.error(f"Unknown link format: {link}")
                except Exception as e:
                    logger.error(f"Error resolving Udemy Freebies course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
