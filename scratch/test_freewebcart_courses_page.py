import requests
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.freewebcart.com/courses"
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
        for idx, link in enumerate(links):
            href = link.get("href", "")
            text = link.get_text().strip()
            # If relative path starts with /course/
            if href.startswith("/course/") and len(href) > 8:
                if href not in seen_courses:
                    seen_courses.add(href)
                    print(f"Course: {href} | Text: {text}")
        print("Total unique courses on /courses:", len(seen_courses))
except Exception as e:
    print("Error:", e)
