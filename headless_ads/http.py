"""Tiny stdlib HTTP client with JSON + retry/backoff. No third-party deps required."""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.parse
import urllib.error

from . import log


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Unsupported URL: {log.sanitize_url(url)}")


class HttpError(Exception):
    def __init__(self, status: int, body: str, url: str):
        self.status = status
        self.body = log.sanitize(body)
        self.url = log.sanitize_url(url)
        super().__init__(f"HTTP {status} for {self.url}: {self.body[:400]}")


def request(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json_body=None,
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 45,
    retries: int = 3,
    backoff: float = 1.5,
):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    _validate_url(url)
    hdrs = {"Accept": "application/json", "User-Agent": "headless-ads-manager/0.1"}
    body = data
    if json_body is not None:
        body = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    last_exc = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                raw = resp.read().decode("utf-8", "replace")
                ctype = resp.headers.get("Content-Type", "")
                if "application/json" in ctype or (raw[:1] in "{["):
                    try:
                        return json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        return raw
                return raw
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace") if e.fp else ""
            # 4xx (except 429) are not retryable
            if e.code != 429 and 400 <= e.code < 500:
                raise HttpError(e.code, err_body, url)
            last_exc = HttpError(e.code, err_body, url)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
        if attempt < retries:
            sleep = backoff ** attempt
            log.warn(f"http retry {attempt}/{retries} in {sleep:.1f}s", url=log.sanitize_url(url))
            time.sleep(sleep)
    raise last_exc if last_exc else HttpError(0, "unknown", url)


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)
