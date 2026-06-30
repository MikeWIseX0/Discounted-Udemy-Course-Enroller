import time
import concurrent.futures
from loguru import logger
from duce.utils.network import session
from duce.core.config import SCRAPER_URLS, get_scraper_headers


def scrape_cxyz(scraper):
    code_name = "cxyz"
    try:
        scraper.set_attr(code_name, "length", 10)

        def _fetch_cxyz_page(page):
            headers = get_scraper_headers()
            base_url = SCRAPER_URLS.get("cxyz", "https://courson.xyz")
            for _ in range(3):
                try:
                    r = session.post(
                        f"{base_url}/load-more-coupons",
                        json={"filters": {}, "offset": (page - 1) * 30},
                        headers=headers,
                        timeout=(15, 15)
                    )
                    if r.status_code == 200:
                        return r.json()
                except Exception as e:
                    logger.debug(
                        f"cxyz page {page} attempt {_ + 1} failed: {e}")
                    time.sleep(2)
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_page = [
                executor.submit(_fetch_cxyz_page, page)
                for page in range(1, 11)
            ]
            for i, future in enumerate(
                concurrent.futures.as_completed(future_page)
            ):
                try:
                    result = future.result()
                    if result is None or "coupons" not in result:
                        scraper.set_attr(code_name, "progress", i + 1)
                        continue
                    content = result["coupons"]
                    if not content:
                        logger.debug("No more coupons")
                        continue
                    for item in content:
                        try:
                            title = item["headline"].strip(' "')
                            link = f"https://www.udemy.com/course/{item['id_name']}/?couponCode={item['coupon_code']}"
                            scraper.append_to_list(title, link, code_name)
                        except Exception as item_e:
                            logger.error(
                                f"Error parsing Courson item: {item_e}")
                except Exception as page_e:
                    logger.error(
                        f"Error resolving Courson page future: {page_e}")
                scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)

    scraper.set_attr(code_name, "done", True)
