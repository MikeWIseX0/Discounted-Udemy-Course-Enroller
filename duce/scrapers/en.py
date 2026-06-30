import concurrent.futures
from loguru import logger
from duce.core.config import SCRAPER_URLS


def scrape_en(scraper):
    code_name = "en"
    try:
        all_items = []
        base_url = SCRAPER_URLS["en"].replace("https://e-next.in", "https://jobs.e-next.in")
        scraper.set_attr(code_name, "length", 5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/course/udemy/{page}",
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
                    page_items = soup.find_all(
                        "a", {"class": "btn btn-secondary btn-sm btn-block"}
                    )
                    all_items.extend(page_items)
                except Exception as e:
                    logger.error(f"Error fetching page in E-next: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

        scraper.set_attr(code_name, "length", len(all_items))
        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
            future_course_details = [
                executor.submit(
                    scraper.fetch_page,
                    item["href"],
                )
                for item in all_items
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_course_details)
            ):
                try:
                    result = future.result()
                    if result is None or result.status_code != 200:
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    content = result.content
                    soup = scraper.parse_html(content)
                    title_el = soup.find("h3")
                    title = title_el.string.strip() if title_el else "E-next Course"
                    btn = soup.find("a", {"class": "btn btn-primary"})
                    link = btn.get("href") if btn else ""
                    if link:
                        link = scraper.cleanup_link(link)
                        scraper.append_to_list(title, link, code_name)
                except Exception as e:
                    logger.error(f"Error resolving E-next course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
