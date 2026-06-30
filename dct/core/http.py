"""
dct.core.http
Shared resilient HTTP client with automatic retries for transient errors.
"""

import httpx
import time
import atexit

class ResilientClient(httpx.Client):
    def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        retries = 3
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                response = super().send(request, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    response.close()
                    time.sleep(backoff * (2 ** attempt))
                    continue
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                if attempt < retries:
                    time.sleep(backoff * (2 ** attempt))
                    continue
                raise

client = ResilientClient(http2=True, transport=httpx.HTTPTransport(retries=3))
atexit.register(client.close)
