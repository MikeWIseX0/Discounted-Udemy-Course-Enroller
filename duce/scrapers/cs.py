import concurrent.futures
from loguru import logger
from duce.utils.network import RobustCffiSession
from duce.core.config import SCRAPER_URLS


def scrape_cs(scraper):
    code_name = "cs"
    try:
        all_items = []
        scraper.set_attr(code_name, "length", 5)
        base_url = SCRAPER_URLS.get("cs", "https://couponscorpion.com")

        with RobustCffiSession(impersonate="chrome") as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"{base_url}/",
            }

            def _fetch_list_page(page):
                url = f"{base_url}/category/100-off-coupons/"
                if page > 1:
                    url += f"page/{page}/"
                try:
                    r = session.get(url, headers=headers, timeout=30)
                    if r.status_code == 200:
                        return r.content
                except Exception as e:
                    logger.error(
                        f"Coupon Scorpion list page {page} fetch failed: {e}")
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_page = [
                    executor.submit(_fetch_list_page, page)
                    for page in range(1, 6)
                ]
                for i, future in enumerate(
                    concurrent.futures.as_completed(future_page)
                ):
                    try:
                        result = future.result()
                        if result is None:
                            scraper.set_attr(code_name, "progress", i + 1)
                            continue
                        soup = scraper.parse_html(result)
                        h2_elements = soup.find_all("h2")
                        page_items = []
                        for h2 in h2_elements:
                            a_tag = h2.find("a")
                            if a_tag and a_tag.get("href"):
                                href = a_tag["href"]
                                if "couponscorpion.com" in href and href != "https://couponscorpion.com" and href != "https://couponscorpion.com/":
                                    page_items.append(a_tag)
                        all_items.extend(page_items)
                    except Exception as e:
                        logger.error(
                            f"Error fetching page in Coupon Scorpion: {e}")
                    scraper.set_attr(code_name, "progress", i + 1)

            scraper.set_attr(code_name, "length", len(all_items))

            def _fetch_course_details(item):
                title = item.get("title") or item.text or ""
                title = title.strip()
                post_url = item["href"]
                try:
                    r = session.get(post_url, headers=headers, timeout=30)
                    if r.status_code != 200:
                        return title, ""
                    soup = scraper.parse_html(r.content)
                    btn = soup.find("a", class_="btn_offer_block")
                    if not btn or not btn.get("href"):
                        btn = soup.find(
                            "a", href=lambda x: x and "scripts/udemy/out.php" in x)

                    if btn and btn.get("href"):
                        redirect_url = btn["href"]
                        r_red = session.get(
                            redirect_url, headers=headers, allow_redirects=True, timeout=30)
                        if "udemy.com" in r_red.url:
                            return title, r_red.url
                except Exception as e:
                    logger.error(
                        f"Error fetching Coupon Scorpion details for {title}: {e}")
                return title, ""

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
                    except Exception as e:
                        logger.error(
                            f"Error resolving Coupon Scorpion course: {e}")
                    scraper.set_attr(code_name, "progress", i + 1)
    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
