"""Runnable demo for headless-ads-manager.

Runs fully offline with no credentials: it builds REAL Meta API payloads but,
because no write here passes apply=True (and SAFE_MODE defaults on), the guard
logs every write as a dry-run and touches nothing.

    python -m headless_ads.demo            # dry-run a couple of writes
    python -m headless_ads.demo --check    # show config + read test
    python -m headless_ads.demo --insights # pull last 7d insights (read)
"""
from __future__ import annotations
import argparse
import json

from . import config, safety
from .client import MetaClient


def cmd_check(client: MetaClient) -> None:
    print("config.status():")
    print(json.dumps(config.status(), indent=2))
    print("\nclient.check():")
    print(json.dumps(client.check(), indent=2))


def cmd_insights(client: MetaClient) -> None:
    rows = client.get_insights(level="account", date_preset="last_7d")
    print(f"pulled {len(rows)} insight row(s) (empty is expected with no token)")
    for r in rows[:5]:
        print(json.dumps(r, indent=2))


def cmd_demo_write(client: MetaClient) -> None:
    print("Building REAL Meta payloads — watch the guard gate them to dry-run:\n")
    client.create_campaign(
        {
            "name": "Headless Demo — Sales",
            "objective": "OUTCOME_SALES",
            "special_ad_categories": [],
        }
    )
    client.update_adset_budget("123456789", 25000, adset_name="Demo Ad Set")
    print()
    safety.print_summary()
    print(
        "\nNothing above touched Meta. A live write needs BOTH gates open:\n"
        "  1) SAFE_MODE=false in the environment\n"
        "  2) apply=True passed to the write call\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="headless-ads-manager demo")
    ap.add_argument("--check", action="store_true", help="print config + read test")
    ap.add_argument("--insights", action="store_true", help="pull last 7d account insights")
    args = ap.parse_args()

    client = MetaClient()
    if args.check:
        cmd_check(client)
    elif args.insights:
        cmd_insights(client)
    else:
        cmd_demo_write(client)


if __name__ == "__main__":
    main()
