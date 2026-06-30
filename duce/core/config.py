import os
import sys

VERSION = "v3.0.0"

SCRAPER_URLS: dict = {
    "rd": "https://www.real-discount.com",
    "cxyz": "https://courson.xyz",
    "idc": "https://idownloadcoupon.com",
    "tb": "https://www.tutorialbar.com",
    "en": "https://e-next.in",
    "du": "https://www.discudemy.com",
    "uf": "https://www.udemyfreebies.com",
    "cj": "https://www.coursejoiner.com",
    "cv": "https://coursevania.com",
    "cs": "https://couponscorpion.com",
}

def get_scraper_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

scraper_dict: dict = {
    "Real Discount": "rd",
    "Courson": "cxyz",
    "IDownloadCoupons": "idc",
    "Tutorial Bar": "tb",
    "E-next": "en",
    "Discudemy": "du",
    "Udemy Freebies": "uf",
    "Course Joiner": "cj",
    "Course Vania": "cv",
    "Coupon Scorpion": "cs",
}

LINKS = {
    "github": "https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller",
    "support": "https://techtanic.github.io/duce/support",
    "discord": "https://discord.gg/wFsfhJh4Rh",
}


def get_user_data_path(filename):
    """Get the path for user data files """
    if getattr(sys, 'frozen', False):
        # If running as PyInstaller exe, put user data files next to the executable
        return os.path.join(os.path.dirname(sys.executable), filename)
    else:
        # If running as script, put files in current directory
        return os.path.join(os.path.abspath("."), filename)


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
