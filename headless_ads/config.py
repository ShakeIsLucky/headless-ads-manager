"""Config loader for headless-ads-manager.

Precedence: real process environment > a local ``.env`` file in the current
working directory. No external dependencies, no magic — just enough to read a
Meta access token and the global ``SAFE_MODE`` switch.
"""
from __future__ import annotations
import os
from pathlib import Path

_BOOL_TRUE = {"1", "true", "yes", "on", "y"}


def _load_env_file(path: Path) -> dict:
    data: dict[str, str] = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip().strip('"').strip("'")
    except (FileNotFoundError, IsADirectoryError):
        pass
    return data


_LOCAL = _load_env_file(Path.cwd() / ".env")


def get(key: str, default=None):
    if key in os.environ:
        return os.environ[key]
    if key in _LOCAL:
        return _LOCAL[key]
    return default


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key)
    if val is None:
        return default
    return val.strip().lower() in _BOOL_TRUE


def require(key: str) -> str:
    val = get(key)
    if not val:
        raise RuntimeError(
            f"Missing required config '{key}'. Set it in your environment "
            f"or a .env file (see .env.example)."
        )
    return val


def has(key: str) -> bool:
    return bool(get(key))


# ---------------------------------------------------------------------------
# GLOBAL SAFETY SWITCH
# SAFE_MODE defaults TRUE. It must be *explicitly* set false to allow any live
# write to the Meta ad account. Even then, each write call also requires an
# apply=True flag. Two independent gates protect against accidental spend.
# ---------------------------------------------------------------------------
SAFE_MODE = get_bool("SAFE_MODE", True)

# Meta Marketing API
META_ACCESS_TOKEN = get("META_ACCESS_TOKEN")
META_AD_ACCOUNT_ID = get("META_AD_ACCOUNT_ID")  # e.g. act_1234567890
META_API_VERSION = get("META_API_VERSION", "v21.0")
META_APP_ID = get("META_APP_ID")
META_APP_SECRET = get("META_APP_SECRET")
META_PIXEL_ID = get("META_PIXEL_ID")
META_BUSINESS_ID = get("META_BUSINESS_ID")


def _normalized_account() -> str | None:
    acct = META_AD_ACCOUNT_ID or ""
    if not acct:
        return None
    return acct if acct.startswith("act_") else f"act_{acct}"


def status() -> dict:
    """Non-secret summary of what's configured — for diagnostics."""
    return {
        "SAFE_MODE": SAFE_MODE,
        "meta_configured": bool(META_ACCESS_TOKEN and META_AD_ACCOUNT_ID),
        "ad_account_id": _normalized_account(),
        "pixel_configured": bool(META_PIXEL_ID),
        "api_version": META_API_VERSION,
    }
