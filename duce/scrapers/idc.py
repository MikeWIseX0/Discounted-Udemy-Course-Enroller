import concurrent.futures
from loguru import logger
from duce.utils.network import session
from urllib.parse import unquote
from duce.core.config import SCRAPER_URLS


def scrape_idc(scraper):
    code_name = "idc"
    try:
        all_items = []
        scraper.set_attr(code_name, "length", 3)

        base_url = SCRAPER_URLS.get("idc", "https://idownloadcoupon.com")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(
                    scraper.fetch_page,
                    f"{base_url}/wp-json/wp/v2/product?product_cat=15&per_page=100&page={page}",
                )
                for page in range(1, 4)
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                result = future.result()
                if result is None:
                    scraper.set_attr(code_name, "progress", i + 1)
                    continue
                try:
                    if result.status_code != 200:
                        raise Exception(
                            f"Received status code {result.status_code}")
                    content = result.json()
                    if isinstance(content, list):
                        all_items.extend(content)
                    else:
                        logger.error(
                            f"Invalid IDownloadCoupons response format: expected list, got {type(content)}")
                except Exception as e:
                    logger.error(
                        f"Error parsing IDownloadCoupons page result: {e}")
                scraper.set_attr(code_name, "progress", i + 1)

        scraper.set_attr(code_name, "length", len(all_items))

        def _fetch_course_details(item):
            """Helper method to fetch course details"""
            try:
                title = item["title"]["rendered"]
                link_num = item["id"]
                if link_num in [85, 81]:
                    return None, None
                link = f"{base_url}/udemy/{link_num}/"
                try:
                    r = session.get(
                        link,
                        allow_redirects=False,
                        timeout=15
                    )
                except Exception as req_e:
                    logger.error(
                        f"Request error in IDownloadCoupons for {link}: {req_e}")
                    return None, None
                if "comidoc.net" in link or "comidoc.com" in link:
                    logger.info("Comidoc link: " + link)
                    return None, None
                try:
                    link = unquote(r.headers["Location"])
                except KeyError:
                    logger.error(f"No Location header found for {link}")
                    return None, None
                if "comidoc.com" in link:
                    logger.info("Comidoc link: " + link)
                    return None, None
                link = scraper.cleanup_link(link)
                return title, link
            except Exception as e:
                logger.error(
                    f"Error resolving IDownloadCoupons course details: {e}")
                return None, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
            future_course_details = [
                executor.submit(_fetch_course_details, item) for item in all_items
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_course_details)
            ):
                try:
                    title, link = future.result()
                    if title and link:
                        scraper.append_to_list(title, link, code_name)
                except Exception as e:
                    logger.error(
                        f"Error resolving IDownloadCoupons course: {e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
