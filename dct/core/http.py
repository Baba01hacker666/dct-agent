"""
dct.core.http
Shared resilient HTTP client with automatic retries for transient errors.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _get_retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "DELETE"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


client = _get_retry_session()
