# Changelog

## v3.0.0 (Major Overhaul & Modularization Upgrade)

This release represents a complete visual, architectural, and component-level overhaul of the Discounted Udemy Course Enroller (DUCE). The codebase has been modernized to eliminate resource leaks, improve database concurrency, ensure secure SSL default settings, and provide robust multi-browser cookie extraction.

### Architecture and Package Restructuring
- **Modular Namespace**: Migrated loose root scripts into a structured and clean package layout under the `duce/` namespace directory.
- **Client & Models Segregation**: Separated core Udemy client coordination (`duce/core/client.py`) from database operations (`duce/core/db.py`) and data models (`duce/core/models.py`).
- **Site URL Centralization**: Consolidated all scraper base URLs into a single, clean registry (`SCRAPER_URLS`) inside `duce/core/config.py` along with common user-agent signatures.
- **Scraper Facade Registry**: Modularized all 10 scrapers into dedicated source files under `duce/scrapers/` and bound them dynamically through a clean facade registry class (`Scraper`).
- **Utility Libraries**: Restructured HTML parsing, URL cleaning, and robust network wrappers into lightweight utility modules (`duce/utils/html.py`, `duce/utils/url.py`, `duce/utils/network.py`).

### Bug Fixes and Filter Enhancements
- **Filter Bypass Fix**: Resolved a critical logic bug where courses marked as excluded by user preferences (languages/categories) were incorrectly queued and enrolled if their coupon code was valid.
- **Dynamic Exclusion Cache Re-evaluation**: Upgraded the validation cache loader to re-run filter checks against the *current* user settings. Cached exclusions now adapt instantly to setting changes without requiring a 7-day TTL cache expiration.
- **WordPress JSON Array Type Guard**: Enhanced WordPress REST API parser (`duce/scrapers/cj.py`) to confirm response structures are valid lists before iteration, preventing crashes on rate-limiting responses.
- **Discudemy & Udemy Freebies URL Parsing**: Replaced brittle string splitting with robust `urllib.parse.urlparse` segment extractions to handle dynamic directories and trailing slashes safely.

### Database and Concurrency Optimizations
- **SQLite WAL Mode Integration**: Configured SQLite connections to use Write-Ahead Logging (`WAL`), enabling parallel reads/writes and eliminating multi-threaded write lock crashes.
- **Database Connection Leak Resolution**: Wrapped database manager queries in try/finally blocks to guarantee connections are closed, resolving warnings and accelerating unit test runtimes.
- **Startup Validation Cache Purging**: Implemented automated cache cleanup routines to sweep cache entries older than 7 days on application start, preventing SQLite size bloat.

### Robust Network Stack and SSL Fallbacks
- **Browser Impersonation Stack**: Upgraded requests to use `curl_cffi` (impersonating Chrome TLS fingerprints) as the default network transport to bypass Cloudflare protection layers.
- **Corporate Decryption SSL Fallbacks**: Configured `RobustCffiSession` and `RobustRequestsSession` to retry requests with a fresh, one-off session on TLS verification errors, ensuring safe bypasses on corporate SSL-intercepting firewalls.
- **Secure SSL Defaults**: Hardcoded the `"allow_insecure_ssl_fallback": false` setting by default to ensure secure communication with `udemy.com`. Users can opt-in to fallbacks via GUI options or config files.
- **Connection Pool Tuning**: Mounted a tuned `HTTPAdapter` with connection limits set to 50 to prevent thread pooling bottlenecks.
- **Brotli Compression Support**: Enabled automated Brotli content-encoding parsing, saving 15-30% in network bandwidth payloads.

### GUI and CLI Client Overhaul
- **Premium Theme System**: Redesigned UI styling with a Dark Charcoal background (`#121212`), high-contrast mint green highlights, rounded frames, and clean layouts.
- **Single-Window Navigation**: Replaced disjointed popup windows with a modern single-window design, using a Left Sidebar to transition smoothly between pages.
- **Thread-Safe Event Queue Processing**: Implemented a thread-safe Queue polling mechanism to coordinate updates between background threads and the main Tkinter thread.
- **Logs Console Monospace Font**: Updated logs to use `Consolas` with color-coded logging tags for easy monitoring.
- **GUI Log Trimming**: Integrated an auto-pruning routine to keep logs within the last 1000 lines, preventing Tkinter slow-downs.
- **Cancellation & Graceful Thread Shutdowns**: Added cancellation capabilities ("Stop Enroller") to safely abort execution and return accumulated metrics.
- **CLI Argparse Arguments**: Added custom CLI argument parser supporting `-h` / `--help` usage documentation, `-v` / `--version` flags, and automated execution.
- **CLI Non-Interactive Mode**: Implemented `-n` / `--non-interactive` flag to bypass interactive menus, allowing immediate enrollment runs suitable for scripts.
- **CLI Scheduler Loop**: Added `-i` / `--interval` argument to run DUCE in a continuous execution loop, automatically repeating the run once every N minutes.
- **CLI Automatic Headless Fallback**: Configured CLI to automatically default to non-interactive mode if executed without a TTY terminal attached (e.g. cron jobs, VPS, or CI/CD pipelines).

### Cookie Discovery and Encryption Support
- **Dynamic Browser Scanning**: Supported profile detection for Chrome, Edge, Brave, Vivaldi, Opera, Opera GX, Firefox, LibreWolf, and Waterfox.
- **App-Bound Encryption Warning**: Detects when Chromium App-Bound Encryption (v20) blocks decryption of Udemy sessions, providing an action-guided warning to paste exported cookies from the clipboard.
- **Thread-Safe Clipboard API**: Replaced Tkinter clipboard calls with direct `win32clipboard` calls to prevent multi-thread access crashes.
- **Shared Plaintext Cookie Cache**: Stores session cookies in a unified, plaintext `cookies.json` file accessible by both GUI and CLI clients.

### Automated Verification and Testing
- **Scraper Testing Suite**: Added mock-based scraper validation tests in `tests/test_scrapers.py`.
- **Core Verification**: Created comprehensive unit tests in `tests/test_core.py`.

---

## v2.3.6
- Fix settings and log file not saving

## v2.3.5
- Fixed `IDownloadCoupons`


## v2.3.4

- Remove unnecessary key bindings from login window
- Fixed Some scrappers
- Fixed Errors during enrollment
- Optimized enrollment process
- Fixed few edge cases where the course was already enrolled but not detected

## v2.3.3

- Improved all scrapers for better performance.
- Added `Courson` as a new coupon source
- Added `Course Joiner` as a new coupon source
- Added Course class for better course management
- Added better error handling and logging
- Added Vietnamese language support
- Implemented bulk checkout for more efficient enrollment
- Improved CLI with rich text interface and live progress displays
- Enhanced GUI with detailed enrollment statistics
- Fixed RealDiscount again
- Fixed minor bugs and optimizations

## v2.3.2

- Fixed `RealDiscount`
- Tried to reduce throttling


## v2.3.1

- Fixed missing color in print
- Improve update checker
- Improved Already enrolled course detection


## v2.3

- Removed getting settings from github is file not found. Default settings will be included in exe.
- Changed Manual Login API
- Fixed `TutorialBar`
- Fixed Error for Courses that are no longer accepting new enrollments
- Refactored some code

## v2.2

- Fixed `CourseVania`
- Refactored code
- Added Course last Updated filter

## v2.1

- Fixed Scrappers
- Optimized some code
- Fixed multiple issues
- Hopefully all known errors are fixed
- CLI now supports Browser Cookie Login (Can be changed in settings)

## v2.0

- Fix Retrying error

## v1.9

- Potential fix for Manual Login
- Fixed error on encountering free course with coupons
- Fixed IDownloadCoupons
- Added support for Urdu and Nepali language

## v1.8

- Refactored code
- Fixed Course not enrolling
- Fixed real discount
- Fixed enext
- Fixed coursevania
- Fixed Manual Login
- Fixed scrapers
- Fixed a lot of things
- Removed Colab Version because Login not possible

## v1.7

- Fixed Auto-Login

## v1.6

- Fixed Login issues
- Fixed `CourseVania`
- Fixed Enrolling
- Some minor fixes

## v1.5

- Fixed login problem.
- Fixed my ego.

## v1.4

- Added `e-next.in`
- Added Discounted only filter
- Hopeful fix for `Amount saved` not showing
- Hopeful fix for Manual login
- Fixed not saving courses to file on unexpected exit.
- Simplified some logic

## v1.3

- Added Save to txt file option in CLI and GUI
- Fixed some logic

## v1.2

- Fixed RealDiscount and CourseVania

## v1.1

- Fixed RealDiscount and CourseVania
- Added Russian Language filter

## v1.0

- Fresh start
