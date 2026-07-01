import concurrent.futures
from loguru import logger
from duce.core.config import SCRAPER_URLS


def scrape_fwc(scraper):
    code_name = "fwc"
    try:
        all_items = []
        base_url = SCRAPER_URLS.get("fwc", "https://www.freewebcart.com")
        scraper.set_attr(code_name, "length", 5)

        # Step 1: Fetch pagination pages 1 to 5 in parallel to collect course paths
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/courses?page={page}",
                )
                for page in range(1, 6)
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                try:
                    result = future.result()
                    if result is None or result.status_code != 200:
                        status = "failed" if result is None else f"status {result.status_code}"
                        logger.warning(f"FreeWebCart page request failed ({status})")
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    content = result.content
                    soup = scraper.parse_html(content)
                    links = soup.find_all("a")
                    page_items = []
                    for link in links:
                        href = link.get("href", "")
                        if href.startswith("/course/") and len(href) > 8:
                            if href not in page_items:
                                page_items.append(href)
                    all_items.extend(page_items)
                except Exception as e:
                    logger.error(f"Error fetching page in FreeWebCart: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

        # De-duplicate collected course paths
        unique_paths = list(set(all_items))
        scraper.set_attr(code_name, "length", len(unique_paths))

        # Helper function to fetch course details page and resolve direct Udemy coupon link
        def _fetch_course_details(path):
            try:
                url = f"{base_url}{path}"
                result = scraper.fetch_page(url)
                if result is None or result.status_code != 200:
                    return None, None
                soup = scraper.parse_html(result.content)
                title_tag = soup.find("h1")
                title = title_tag.get_text().strip() if title_tag else "FreeWebCart Course"
                
                # Extract first link containing "udemy.com"
                links = soup.find_all("a")
                for link in links:
                    href = link.get("href", "")
                    if "udemy.com" in href:
                        return title, href
            except Exception as e:
                logger.error(f"Error fetching course details in fwc scraper: {e}")
            return None, None

        # Step 2: Resolve course paths to Udemy coupon links in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_course_details = [
                executor.submit(_fetch_course_details, path) for path in unique_paths
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
                    logger.error(f"Error resolving FreeWebCart course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
