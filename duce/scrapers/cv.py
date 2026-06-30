import re
import concurrent.futures
from loguru import logger
from duce.utils.network import session
from duce.core.config import SCRAPER_URLS


def scrape_cv(scraper):
    code_name = "cv"
    try:
        base_url = SCRAPER_URLS.get("cv", "https://coursevania.com")
        _cv_result = scraper.fetch_page(f"{base_url}/courses/")
        if _cv_result is None or _cv_result.status_code != 200:
            status = "failed" if _cv_result is None else f"status {_cv_result.status_code}"
            raise Exception(f"Failed to fetch CourseVania page: {status}")
        content = _cv_result.content

        try:
            nonce = re.search(
                r"load_content\"\:\"(.*?)\"", _cv_result.text, re.DOTALL
            ).group(1)
            logger.debug(f"Nonce: {nonce}")
        except (IndexError, AttributeError) as e:
            scraper.set_attr(code_name, "error", f"Nonce not found: {e}")
            scraper.set_attr(code_name, "length", -1)
            scraper.set_attr(code_name, "done", True)
            return
        res = session.get(
            f"{base_url}/wp-admin/admin-ajax.php?&template=courses/grid&args={{%22posts_per_page%22:%22150%22}}&action=stm_lms_load_content&sort=date_high&nonce={nonce}",
            timeout=15
        )
        if res.status_code != 200:
            raise Exception(
                f"Failed to fetch CourseVania grid content: status {res.status_code}")
        r = res.json()

        soup = scraper.parse_html(r["content"])
        page_items = soup.find_all(
            "div", {"class": "stm_lms_courses__single--title"}
        )[:150]

        scraper.set_attr(code_name, "length", len(page_items))

        def _fetch_course_details(item):
            """Helper method to fetch course details"""
            h5_el = item.find("h5")
            title = h5_el.text.strip() if h5_el else "CourseVania Course"
            
            a_tag = item.find("a")
            if not a_tag or not a_tag.get("href"):
                return title, ""
            
            result = scraper.fetch_page(a_tag["href"])
            if result is None or result.status_code != 200:
                return title, ""
            
            soup = scraper.parse_html(result.content)
            # Find the buy button, which can have various classes
            btn = soup.find("a", class_=lambda x: x and any(c in x for c in ["masterstudy-buy-button__link", "masterstudy-button-affiliate__link"]))
            if not btn:
                btn = soup.find("a", class_="masterstudy-button-affiliate__link")
                
            if btn and btn.has_attr("href"):
                link = btn["href"]
                if link == "#" or btn.has_attr("data-authorization-modal"):
                    logger.debug(f"Course Vania: '{title}' requires login, skipping.")
                    return title, ""
                return title, link
            return title, ""

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_course_details = [
                executor.submit(_fetch_course_details, item) for item in page_items
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
                    logger.error(f"Error resolving CourseVania course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
