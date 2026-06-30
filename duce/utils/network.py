import ssl
import time
import urllib3
import requests
from requests.adapters import HTTPAdapter
from loguru import logger

# Suppress InsecureRequestWarning for SSL fallback scenarios
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try importing curl_cffi, fallback to normal requests
try:
    from curl_cffi import requests as cffi_requests
    use_cffi = True
    logger.info("Using curl_cffi for network operations.")
except ImportError:
    use_cffi = False
    logger.warning("curl_cffi not available, falling back to standard requests.")


class SystemCertHTTPAdapter(HTTPAdapter):
    """HTTP Adapter that loads system certificates on Windows/Linux/macOS to trust local antivirus/proxies."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        try:
            context.load_default_certs()
        except Exception:
            pass
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        context = ssl.create_default_context()
        try:
            context.load_default_certs()
        except Exception:
            pass
        kwargs['ssl_context'] = context
        return super().proxy_manager_for(*args, **kwargs)


class RobustRequestsSession(requests.Session):
    """requests Session that automatically retries with verify=False on SSL/TLS verification errors."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_insecure_fallback = True

    def request(self, method, url, *args, **kwargs):
        try:
            return super().request(method, url, *args, **kwargs)
        except Exception as e:
            if not getattr(self, "allow_insecure_fallback", True):
                raise e
            err_str = str(e).lower()
            if "ssl" in err_str or "cert" in err_str or "verify" in err_str or "unable to get local issuer certificate" in err_str:
                logger.warning(
                    f"SSL/TLS error occurred in requests session for {url}: {e}. Retrying with verify=False...")
                kwargs["verify"] = False
                try:
                    return super().request(method, url, *args, **kwargs)
                except Exception as inner_e:
                    logger.error(f"Requests fallback to verify=False failed: {inner_e}")
                    raise inner_e
            else:
                raise e


if use_cffi:
    class RobustCffiSession(cffi_requests.Session):
        """curl_cffi Session that automatically retries with verify=False on SSL/TLS verification errors."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.allow_insecure_fallback = True
            self._impersonate = kwargs.get("impersonate", "chrome")

        def request(self, method, url, *args, **kwargs):
            try:
                return super().request(method, url, *args, **kwargs)
            except Exception as e:
                if not getattr(self, "allow_insecure_fallback", True):
                    raise e
                err_str = str(e).lower()
                if "ssl" in err_str or "cert" in err_str or "verify" in err_str or "unable to get local issuer certificate" in err_str:
                    logger.warning(
                        f"SSL/TLS error occurred in curl_cffi session for {url}: {e}. Retrying with verify=False...")
                    kwargs["verify"] = False
                    try:
                        # Use a fresh one-off session for the insecure retry,
                        # as curl_cffi may cache SSL settings per-session.
                        with cffi_requests.Session(impersonate=self._impersonate) as temp_session:
                            return temp_session.request(method, url, *args, **kwargs)
                    except Exception as inner_e:
                        logger.error(f"curl_cffi fallback to verify=False failed: {inner_e}")
                        raise inner_e
                else:
                    raise e

    session = RobustCffiSession(impersonate="chrome")
else:
    class RobustCffiSession(RobustRequestsSession):
        """Fallback to requests.Session when curl_cffi is not available."""
        def __init__(self, *args, **kwargs):
            kwargs.pop("impersonate", None)
            super().__init__(*args, **kwargs)
            adapter = SystemCertHTTPAdapter(pool_connections=50, pool_maxsize=50)
            self.mount("https://", adapter)
            self.mount("http://", adapter)

    session = RobustRequestsSession()
    adapter = SystemCertHTTPAdapter(pool_connections=50, pool_maxsize=50)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })


def fetch_page(url: str, headers: dict = None) -> requests.Response:
    """Fetches a page with 3 retries and error handling using the robust session."""
    for attempt in range(3):
        try:
            return session.get(url, headers=headers, timeout=30)
        except Exception as e:
            logger.error(f"Error fetching page {url} (attempt {attempt + 1}): {e}")
            time.sleep(1.5)
    logger.warning(f"Failed to fetch page after 3 attempts: {url}")
    return None
