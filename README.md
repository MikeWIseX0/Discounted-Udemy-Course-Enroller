<p align="center">
    <img src="https://raw.githubusercontent.com/MikeWIseX0/Discounted-Udemy-Course-Enroller/refs/heads/master/extra/promo.gif" alt="DUCE Promotion" width="600">
    <br/>
    <img src="https://forthebadge.com/images/badges/made-with-python.svg" alt="Made with Python">
    <br/>
    <a href="https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller/graphs/commit-activity">
        <img alt="Maintenance" src="https://img.shields.io/badge/Maintained%3F-yes-green.svg?style=for-the-badge">
    </a>
    <a target="_blank" href="https://discord.gg/wFsfhJh4Rh">
        <img alt="Discord" src="https://img.shields.io/discord/703266580846346361.svg?label=Discord&logo=Discord&colorB=7289da&style=for-the-badge">
    </a>
    <br/>
    <a href="https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller">
        <img src="https://cdn.discordapp.com/attachments/823472016999972884/841661124410736710/standard_13.gif" alt="Stats">
    </a>
</p>

# Discounted Udemy Course Enroller (DUCE) — v3.0.1

A powerful, modernized automation tool designed to scrape discounted or free Udemy courses with active coupon codes from popular scraper platforms and automatically enroll them directly into your Udemy account.

Everything you need can be found on our documentation website: **https://techtanic.github.io/duce/**

---

## Key Features

- **Beautiful & Modern GUI**: Implements a dark charcoal theme with a single-window navigation sidebar built on CustomTkinter.
- **One-Click Cookie Login**: Safe, instantaneous authentication utilizing exported or local browser cookies (supports Chrome, Edge, Brave, Firefox, Opera, and more).
- **TLS Fingerprint Impersonation**: Built on top of `curl_cffi` to mimic real browser TLS signatures, cleanly bypassing basic Cloudflare checks and bot detection.
- **Smart Validation Caching**: Employs a local SQLite database cache with a 7-day TTL to avoid redundant API checks, with dynamic filter re-evaluation when settings change.
- **Dynamic Thread-Safe UI Log Box**: Features live log streaming with custom syntax highlighting, tag-based severity colors, and auto-scrolling log limits.
- **Advanced Course Filtering**: Precise exclusion lists for instructors, custom title keywords, minimum rating levels, and specific languages/categories.
- **Codebase-wide Auto-Healing**: Dynamic fail-safes that automatically recover from `curl_cffi` runtime crashes, retry database transaction locks, and clean up corrupted/expired cookies to prevent app lockout loops.
- **Automated Cookie Rotation/Refresh**: Captures rotated session cookies from successful API responses during enrollment runs and automatically saves them back to `cookies.json` and `udemy-cookies.json` (encrypted) to refresh expiration timestamps and prevent session expiration.
- **CLI Automation Support**: A terminal-based companion mode using `rich` interactive live progress grids, ideal for cron jobs and headless servers.

---

## Downloads

<table>
<thead>
  <tr align="center">
    <th>GUI Version (Windows)</th>
    <th>CLI Version (Windows)</th>
    <th>Release Details</th>
  </tr>
</thead>
<tbody>
  <tr align="center">
    <td>
      <a href="https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller/releases/download/v3.0.1/DUCE-GUI-windows.exe">
         <img alt="GUI Windows exe" src="https://img.shields.io/static/v1?message=Download&logo=windows&labelColor=5c5c5c&color=1182c3&label=%20&style=for-the-badge">
      </a>
    </td>
    <td>
      <a href="https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller/releases/download/v3.0.1/DUCE-CLI-windows.exe">
         <img alt="CLI Windows exe" src="https://img.shields.io/static/v1?message=Download&logo=windows&labelColor=5c5c5c&color=1182c3&label=%20&style=for-the-badge">
      </a>
    </td>
    <td>
      <a href="https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller/releases/tag/v3.0.1">
         <img alt="Release Info" src="https://img.shields.io/static/v1?message=v3.0.1&logo=github&labelColor=5c5c5c&color=28a745&label=Release&style=for-the-badge">
      </a>
    </td>
  </tr>
</tbody>
</table>

---

## Running from Source

If you prefer to run DUCE directly from Python, follow these setup instructions:

### Prerequisites
- **Python 3.10 to 3.13** installed on your system.
- Standard C++ build tools (required for compiles of some third-party modules like `curl_cffi` on some platforms).

### Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/MikeWIseX0/Discounted-Udemy-Course-Enroller.git
   cd Discounted-Udemy-Course-Enroller
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate
   ```
3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Execution
- **To run the GUI version**:
  ```bash
  python gui.py
  ```
- **To run the CLI version (Interactive Menu)**:
  ```bash
  python cli.py
  ```
- **To run the CLI version in Non-Interactive / Automated Mode**:
  ```bash
  python cli.py --non-interactive
  ```
- **To run the CLI version in an automation loop (repeating every N minutes)**:
  ```bash
  python cli.py --interval 60
  ```

### CLI Command Options

You can view all available CLI arguments by running:
```bash
python cli.py --help
```

| Argument | Description |
| --- | --- |
| `-h`, `--help` | Show this help message and exit. |
| `-v`, `--version` | Show the program version number and exit. |
| `-n`, `--non-interactive` | Run the course enroller in non-interactive/automated mode. Defaults to this automatically if standard input is not a TTY (e.g. VPS, cron job). |
| `-i`, `--interval <N>` | Run the enroller continuously in a loop, repeating the run once every `<N>` minutes. |

### Compilation / Building Standalone Binaries

Standalone executables for Windows can be generated using PyInstaller:
- **Build GUI**:
  ```bash
  pyinstaller --clean DUCE-GUI-windows.spec
  ```
- **Build CLI**:
  ```bash
  pyinstaller --clean DUCE-CLI-windows.spec
  ```

---

## Testing

DUCE includes a fully offline automated unit test suite. Run the tests using:
```bash
python -m unittest discover -s tests -v
```

---

## Cookie Extraction & Login

Automatic browser cookie extraction is deprecated and no longer supported due to browser security restrictions (such as App-Bound Encryption on Chromium v120+). 

To log in using cookies:
1. Install a cookie exporter extension (such as **Cookie-Editor**) on your browser.
2. Log in to [Udemy](https://www.udemy.com/) in your web browser.
3. Click the **Cookie-Editor** extension icon, click **Export** (JSON format), which automatically copies your cookies to your clipboard.
4. Click **Extract & Auto Login** in the DUCE app. It will automatically detect your clipboard cookies, import them, and log you in!
5. (Optional) Alternatively, you can paste the copied JSON cookies directly into the `cookies.json` file in the application directory.

---

## GUI Screenshots

<details>
<summary>View Screenshots</summary>

### Login Window
![Login](/extra/gui-login.png)

### Settings & Controls
![Dashboard](/extra/gui-main.png)

### Scraper Status
![Scraping](/extra/gui-scraping.png)

### Live Enrollment Console
![Enrolling](/extra/gui-enrolling.png)

</details>

---

## Disclaimer

![](/extra/disclaimer.png)

This software is for educational and personal use only. Use at your own risk.

---

## Support the Project

If you find DUCE helpful, feel free to support the developer:

- **Bitcoin (BTC)**: `bc1qdyjwj0eqxjk5hxejah4gyclrumwtqs3hqp63uz`
- **Bitcoin (BTC Legacy)**: `14JNjiNoiKcbCHcxcqUxgJcVgyDfhGbxQF`

<p align="center">Made with ❤️ for the open-source community</p>