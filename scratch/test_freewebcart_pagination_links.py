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
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        links = soup.find_all("a")
        for link in links:
            href = link.get("href", "")
            text = link.get_text().strip()
            # If href has pagination or numbers or next/prev
            if "page" in href or "next" in href or "prev" in href or text.isdigit():
                print(f"Pagination Link: {href} | Text: {text}")
except Exception as e:
    print("Error:", e)
