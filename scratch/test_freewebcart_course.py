import requests
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# Let's check a course page
url = "https://www.freewebcart.com/course/complete-photography-course"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=15)
    print("Status Code:", response.status_code)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        # Let's print all external links or links containing "udemy.com" or links with class containing "button" or similar.
        links = soup.find_all("a")
        print("Total links on course page:", len(links))
        for idx, link in enumerate(links):
            href = link.get("href", "")
            text = link.get_text().strip()
            if "udemy.com" in href or "free" in href.lower() or "coupon" in href.lower() or "enroll" in href.lower() or "button" in str(link.get("class", [])):
                print(f"Link: {href} | Text: {text} | Class: {link.get('class')}")
except Exception as e:
    print("Error:", e)
