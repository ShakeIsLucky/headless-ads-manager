# Headless Ads Manager

Run Meta Ads from code instead of clicking through Ads Manager. Pull analytics, edit ads, and publish campaigns from a script or an agent.

## What it does

A small Python client over the Meta Marketing API. From a script (or an agent) you can:

- pull analytics: spend, ROAS, clicks and the rest, at account / campaign / ad set / ad level
- edit existing ads: budgets, pause or activate, swap creative, change targeting
- publish new campaigns, ad sets, and ads, plus upload image and video creative

It's all one Graph API; reads and writes are just different endpoints on it. Reads are offline-safe (no token gives you empty results instead of a crash), and every write is dry-run by default: the client builds the real payload, prints what it would send, and changes nothing until you set `SAFE_MODE=false` and pass `apply=True`.

```bash
pip install -r requirements.txt
python -m headless_ads.demo      # builds real payloads, runs them dry, touches nothing
```

## What's rough about it right now

It's intentionally small and blunt. A few things worth knowing before you point it at a real account:

1. Dry-run is the default, which is correct but can fool you: a script can finish clean and still have changed nothing live. A real write needs both `SAFE_MODE=false` and `apply=True`, and you should confirm the result in Ads Manager afterward.

2. A failed read looks like an empty one. Reads return `[]` or `{}` when credentials are missing, by design, but some API errors also come back empty after logging to stderr. If a read returns nothing unexpectedly, check stderr or run `python -m headless_ads.demo --check`.

3. Config is read once, at import. Set `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, and `SAFE_MODE` before you start Python. Change them inside a running process and the client won't notice, so start a fresh process instead.

4. Uploads are basic. The image and video helpers handle the common path, not a full creative-asset manager. Stick to normal JPEG/MP4 inputs and check the Meta response before wiring an asset into an ad.

5. Your token is full account access. Treat `.env` like a private key. The guard stops this package from writing by accident; it does nothing for a token that's already leaked.

## License

MIT.
