from loguru import logger
from duce.utils.network import session


def scrape_rd(scraper):
    code_name = "rd"
    try:
        all_items = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36 Edg/92.0.902.84",
            "Host": "cdn.real.discount",
            "Connection": "Keep-Alive",
            "dnt": "1",
            "referer": "https://www.real.discount/",
        }
        try:
            res = session.get(
                "https://cdn.real.discount/api/courses?page=1&limit=500&sortBy=sale_start&store=Udemy&freeOnly=true",
                headers=headers,
                timeout=(10, 30),
            )
            if res.status_code != 200:
                raise Exception(f"Received status code {res.status_code}")
            r = res.json()
            if not isinstance(r, dict) or "items" not in r:
                raise Exception(
                    "Invalid API response format (expected dict containing 'items')")
        except Exception as e:
            # We catch general exceptions here too because session.get or JSON parsing can raise errors
            logger.error(f"Real Discount API request failed: {e}")
            scraper.set_attr(code_name, "error", str(e))
            scraper.set_attr(code_name, "length", -1)
            scraper.set_attr(code_name, "done", True)
            return
        all_items.extend(r["items"])

        scraper.set_attr(code_name, "length", len(all_items))
        for index, item in enumerate(all_items):
            try:
                scraper.set_attr(code_name, "progress", index)
                if item["store"] == "Sponsored":
                    continue
                title: str = item["name"]
                link: str = item["url"]
                link = scraper.cleanup_link(link)
                if link:
                    scraper.append_to_list(title, link, code_name)
            except Exception as e:
                logger.error(f"Error parsing Real Discount item: {e}")

    except Exception:
        scraper.handle_exception(code_name)
    scraper.set_attr(code_name, "done", True)
