from __future__ import annotations
import time, urllib.error, urllib.request
from dataclasses import dataclass
from typing import Protocol
from .errors import SourceUnavailableError
from .normalization import sanitize_url

@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    body: bytes

class HttpTransport(Protocol):
    def get(self, url: str, timeout: float) -> HttpResponse: ...

class UrllibTransport:
    def get(self, url: str, timeout: float) -> HttpResponse:
        req = urllib.request.Request(url, headers={"User-Agent":"TWstock-data-adapter/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(resp.geturl(), resp.status, resp.read())

def get_with_retry(url: str, transport: HttpTransport | None = None, timeout: float = 10, retries: int = 2, backoff: float = 0.25) -> HttpResponse:
    transport = transport or UrllibTransport(); last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = transport.get(url, timeout)
            if 200 <= r.status < 300: return r
            last = SourceUnavailableError(f"HTTP {r.status} for {sanitize_url(url)}")
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            last = e
        if attempt < retries: time.sleep(backoff * (2 ** attempt))
    raise SourceUnavailableError(f"failed to fetch {sanitize_url(url)}: {last}")
