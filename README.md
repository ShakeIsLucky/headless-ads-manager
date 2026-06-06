# Headless Ads Manager

Drive Meta Ads from code, not the Ads Manager UI.

The Ads Manager UI is atrocious — endless nested tabs, mystery-meat toggles, and
a "publish" button that's one slip away from spending real money. So I stopped
opening it. This is the thin Python client my coding agent uses to run Meta Ads
*headless*: pull analytics, edit ads, publish campaigns — all from the terminal,
and with a hard safety gate so nothing goes live by accident.

Reads are free and offline-safe. Every write is behind **two switches** so the
agent can set up an entire campaign, show me the exact payload, and not touch the
live account until I flip both.

> Extracted from a production setup that actually runs my ad account. Trimmed to
> the parts worth sharing.

## What it is

- One wrapper, `MetaClient`, around the Meta Graph / Marketing API. No SDK —
  just authed GET/POST calls (`urllib` for JSON, `requests` only for multipart
  image/video upload).
- Auth is an access token + ad account ID in `.env`
  (`META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`). Every call passes the token.
- One mutation gate, `safety.guard()`, that every write funnels through.

It's all the **same Graph API** (`graph.facebook.com/v21.0`) — "reads" and
"writes" are just different endpoints on it.

## The API surface

| You want to… | Method(s) | Type |
|---|---|---|
| **Pull analytics** | `get_insights(level=…, date_preset=…)` — spend, impressions, clicks, CTR, ROAS, actions/revenue at account/campaign/ad set/ad level | read |
| List the account | `list_campaigns()` · `list_adsets()` · `list_ads()` · `get_adset(id)` | read |
| **Edit existing ads** | `set_ad_status()` · `update_ad_creative()` · `update_adset_budget()` · `set_adset_status()` · `update_adset_targeting()` | write |
| **Publish ads** | `create_campaign()` · `create_adset()` · `create_ad()` | write |
| Upload creative | `upload_creative()` · `upload_image()` · `upload_video()` | write |
| Sanity check | `check()` — safe read test | read |

Reads return `[]`/`{}` when no token is set, so pipelines run dry offline
instead of crashing. New campaigns/ad sets/ads are created **PAUSED** by default —
"publishing" something live is create → then `set_ad_status(ACTIVE)`.

## The safety bit (the whole point)

A live write only fires if **both** switches are open:

1. `SAFE_MODE=false` — global env switch, defaults to ON (safe).
2. `apply=True` — per-call flag, defaults off.

Miss either one and the guard logs exactly what it *would* have done and does
nothing:

```text
[DRY_RUN:SAFE_MODE=on] would meta.campaign.create → Headless Demo — Sales  {"name": "Headless Demo — Sales", "objective": "OUTCOME_SALES", ...}
[OK] action summary — DRY-RUN ONLY (no external changes made)  {"total": 2, "live": 0, "dry_run": 2, ...}
```

Every write returns a `GuardResult` (`applied`, `mode`, `payload`, …) and gets
recorded for an end-of-run summary.

## Quickstart

```bash
git clone https://github.com/ShakeIsLucky/headless-ads-manager
cd headless-ads-manager
pip install -r requirements.txt        # only dependency is `requests`
cp .env.example .env                   # fill in your token (optional for the demo)

python -m headless_ads.demo            # dry-run a write — touches nothing
python -m headless_ads.demo --check    # show config + read test
python -m headless_ads.demo --insights # pull last 7d insights (needs a token)
```

The demo runs **with no credentials** — it builds real payloads and shows the
guard refusing to fire them.

In code:

```python
from headless_ads import MetaClient

meta = MetaClient()                                  # reads token from env/.env
rows = meta.get_insights(level="campaign", date_preset="last_30d")   # read

meta.create_campaign({"name": "Q3 Prospecting",      # dry-run unless both gates open
                      "objective": "OUTCOME_SALES",
                      "special_ad_categories": []})

# To actually write: set SAFE_MODE=false in the env AND pass apply=True
meta.set_ad_status("120xxxxxxxxxxx", "ACTIVE", apply=True)
```

## Getting a Meta token

Grab a token from the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
or your own app. You need scopes `ads_read` (reads) and `ads_management`
(writes), plus your ad account ID (`act_…`). Drop both in `.env`.

## Caveats

1. **That token is the keys to the kingdom.** It's a long-lived token sitting in
   `.env` with full write access to the ad account — the two-switch gate is the
   only thing between the agent and real spend. Guard the token, and note that
   tokens expire, so they need re-pulling now and then.

2. **Dry-run by default cuts both ways.** Runs "succeed" without doing anything
   live unless you remember `SAFE_MODE=false` + `apply=True`. Easy to think
   something published when it didn't — always confirm in Ads Manager. (Yes,
   you still open it sometimes. To *check*. Not to *click*.)

## License

MIT — see [LICENSE](LICENSE).
