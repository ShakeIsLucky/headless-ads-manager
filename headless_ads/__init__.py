"""headless-ads-manager — drive Meta Ads from code, not the Ads Manager UI.

Reads are free and offline-safe; every write routes through a two-gate guard
(SAFE_MODE + per-call apply) so nothing touches the live account by accident.
"""
from .client import MetaClient
from .safety import guard, GuardResult, session_summary, print_summary
from . import config

__version__ = "0.1.0"

__all__ = [
    "MetaClient",
    "guard",
    "GuardResult",
    "session_summary",
    "print_summary",
    "config",
    "__version__",
]
