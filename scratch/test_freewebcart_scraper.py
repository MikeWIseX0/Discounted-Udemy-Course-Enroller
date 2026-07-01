import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time

base_url = "https://www.freewebcart.com"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_page(url):
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

def resolve_course(course_path):
    url = f"{base_url}{course_path}"
    content = fetch_page(url)
    if not content:
        return None
    soup = BeautifulSoup(content, "html.parser")
    # Find title
    title_tag = soup.find("h1")
    title = title_tag.get_text().strip() if title_tag else "FreeWebCart Course"
    
    # Find link to Udemy
    links = soup.find_all("a")
    for link in links:
        href = link.get("href", "")
        if "udemy.com" in href:
            return title, href
    return None

def main():
    print("Scraping FreeWebCart page 1 and 2...")
    all_course_paths = set()
    
    # Page 1 & 2
    for page in range(1, 3):
        url = f"{base_url}/courses?page={page}"
        content = fetch_page(url)
        if not content:
            continue
        soup = BeautifulSoup(content, "html.parser")
        links = soup.find_all("a")
        for link in links:
            href = link.get("href", "")
            if href.startswith("/course/") and len(href) > 8:
                all_course_paths.add(href)
                
    print(f"Found {len(all_course_paths)} course paths to resolve.")
    
    # Resolve in parallel
    resolved = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(resolve_course, path): path for path in list(all_course_paths)[:10]}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                resolved.append(res)
                print(f"Resolved: {res[0]} -> {res[1]}")

if __name__ == "__main__":
    main()
