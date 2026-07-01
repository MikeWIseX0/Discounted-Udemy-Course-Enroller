import requests
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.freewebcart.com/page/2/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=15)
    print("Status Code:", response.status_code)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        links = soup.find_all("a")
        seen_courses = set()
        for link in links:
            href = link.get("href", "")
            if href.startswith("/course/") and len(href) > 8:
                if href not in seen_courses:
                    seen_courses.add(href)
        print("Total unique courses found on page 2:", len(seen_courses))
except Exception as e:
    print("Error:", e)
