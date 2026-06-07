"""Minimal structured logging — stderr + a best-effort per-run JSONL trail.

The trail is written to ``./.runs/events.jsonl`` by default (override with the
``HEADLESS_ADS_RUN_DIR`` env var). If that directory can't be created the trail
is silently skipped — logging must never crash a run.
"""
from __future__ import annotations
import os
import sys
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

_RUN_DIR = Path(os.getenv("HEADLESS_ADS_RUN_DIR", ".runs"))
try:
    _RUN_DIR.mkdir(exist_ok=True)
    _TRAIL: Path | None = _RUN_DIR / "events.jsonl"
except OSError:
    _TRAIL = None

_COLORS = {"INFO": "\033[36m", "WARN": "\033[33m", "ERROR": "\033[31m", "OK": "\033[32m"}
_RESET = "\033[0m"
_REDACTED = "[REDACTED]"
_SECRET_KEYS = {
    "access_token",
    "appsecret_proof",
    "client_secret",
    "app_secret",
    "token",
    "password",
    "secret",
    "authorization",
}
_SECRET_QUERY_RE = re.compile(
    r"(?i)(access_token|appsecret_proof|client_secret|app_secret|token|password|secret)=([^&\s]+)"
)
_SECRET_JSON_RE = re.compile(
    r'(?i)("?(?:access_token|appsecret_proof|client_secret|app_secret|token|password|secret|authorization)"?\s*:\s*")([^"]+)(")'
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    text = _SECRET_JSON_RE.sub(r"\1" + _REDACTED + r"\3", url)
    text = _BEARER_RE.sub(r"\1" + _REDACTED, text)
    if not parts.query:
        return _SECRET_QUERY_RE.sub(r"\1=" + _REDACTED, text)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe_query = [
        (key, _REDACTED if key.lower() in _SECRET_KEYS else value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(safe_query, safe="[]"), parts.fragment)
    )


def sanitize(value):
    if isinstance(value, dict):
        return {
            key: (_REDACTED if str(key).lower() in _SECRET_KEYS else sanitize(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize(item) for item in value)
    if isinstance(value, str):
        return sanitize_url(value)
    return value


def _emit(level: str, msg: str, **fields):
    color = _COLORS.get(level, "")
    line = f"{color}[{level}]{_RESET} {msg}"
    fields = sanitize(fields)
    if fields:
        line += "  " + json.dumps(fields, default=str)
    print(line, file=sys.stderr, flush=True)
    if _TRAIL is None:
        return
    try:
        with _TRAIL.open("a") as fh:
            fh.write(json.dumps({"ts": _now(), "level": level, "msg": msg, **fields}, default=str) + "\n")
    except OSError:
        pass


def info(msg: str, **f):
    _emit("INFO", msg, **f)


def ok(msg: str, **f):
    _emit("OK", msg, **f)


def warn(msg: str, **f):
    _emit("WARN", msg, **f)


def error(msg: str, **f):
    _emit("ERROR", msg, **f)
