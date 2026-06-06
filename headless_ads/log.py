"""Minimal structured logging — stderr + a best-effort per-run JSONL trail.

The trail is written to ``./.runs/events.jsonl`` by default (override with the
``HEADLESS_ADS_RUN_DIR`` env var). If that directory can't be created the trail
is silently skipped — logging must never crash a run.
"""
from __future__ import annotations
import os
import sys
import json
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(level: str, msg: str, **fields):
    color = _COLORS.get(level, "")
    line = f"{color}[{level}]{_RESET} {msg}"
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
