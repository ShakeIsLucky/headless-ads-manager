"""The mutation gate. ALL external writes route through guard().

Two independent gates must BOTH open for a live write:
  1. config.SAFE_MODE must be False   (global env switch, defaults True)
  2. the caller must pass apply=True   (per-run flag, defaults False)

If either is closed, the intended action is logged (dry-run) and NOT executed.
This is what enforces "set everything up, but don't touch the live ad account".
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Callable, Any

from . import config, log


@dataclass
class GuardResult:
    applied: bool          # True only if the live action actually executed
    kind: str              # e.g. "meta.adset.update_budget"
    target: str            # human id of the thing being changed
    payload: dict          # what would have been / was sent
    result: Any = None     # API response if applied
    mode: str = "DRY_RUN"  # "LIVE" | "DRY_RUN"

    @property
    def dry_run(self) -> bool:
        return not self.applied


# In-memory record of everything guard() saw this process (for run summaries).
SESSION_ACTIONS: list[dict] = []


def _persist(entry: dict) -> None:
    SESSION_ACTIONS.append(entry)


def guard(
    kind: str,
    target: str,
    payload: dict,
    apply_fn: Callable[[], Any] | None = None,
    *,
    apply: bool = False,
) -> GuardResult:
    """Central write gate. Returns a GuardResult describing intended/actual action."""
    live = (not config.SAFE_MODE) and apply and (apply_fn is not None)
    mode = "LIVE" if live else "DRY_RUN"
    entry = {
        "ts": time.time(),
        "kind": kind,
        "target": target,
        "payload": payload,
        "mode": mode,
        "safe_mode": config.SAFE_MODE,
        "apply_flag": apply,
    }

    if live:
        log.warn(f"[LIVE] {kind} → {target}", payload=_trim(payload))
        try:
            res = apply_fn()
        except Exception as e:  # noqa: BLE001
            entry["mode"] = "ERROR"
            entry["error"] = str(e)
            _persist(entry)
            log.error(f"[LIVE FAILED] {kind} → {target}", err=str(e))
            raise
        entry["result"] = "ok"
        _persist(entry)
        return GuardResult(True, kind, target, payload, res, "LIVE")

    reason = "SAFE_MODE=on" if config.SAFE_MODE else ("--apply not set" if not apply else "no apply_fn")
    log.info(f"[DRY_RUN:{reason}] would {kind} → {target}", payload=_trim(payload))
    _persist(entry)
    return GuardResult(False, kind, target, payload, None, "DRY_RUN")


def _trim(payload: dict) -> str:
    s = json.dumps(payload, default=str)
    return s if len(s) <= 400 else s[:400] + "…"


def session_summary() -> dict:
    live = [a for a in SESSION_ACTIONS if a["mode"] == "LIVE"]
    dry = [a for a in SESSION_ACTIONS if a["mode"] == "DRY_RUN"]
    errs = [a for a in SESSION_ACTIONS if a["mode"] == "ERROR"]
    return {
        "total": len(SESSION_ACTIONS),
        "live": len(live),
        "dry_run": len(dry),
        "errors": len(errs),
        "by_kind": _count_by(SESSION_ACTIONS, "kind"),
    }


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def print_summary() -> None:
    s = session_summary()
    banner = "LIVE WRITES" if s["live"] else "DRY-RUN ONLY (no external changes made)"
    log.ok(f"action summary — {banner}", **s)
