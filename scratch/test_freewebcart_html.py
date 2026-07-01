import requests
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.freewebcart.com/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        links = soup.find_all("a")
        print("Total links found:", len(links))
        for idx, link in enumerate(links[:60]):
            print(f"{idx+1}. href={link.get('href')} | text={link.get_text().strip()}")
except Exception as e:
    print("Error:", e)
