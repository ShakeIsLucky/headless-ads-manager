"""Thin Meta (Facebook) Graph / Marketing API client.

READ methods (insights + list endpoints) hit the API directly with http.get and
return ``[]`` when no access token is configured, so pipelines run dry offline.

WRITE methods (budget, status, create campaign/adset/ad, upload creative) build
the real payload + an ``apply_fn`` closure that performs the actual POST, then
route everything through ``safety.guard(...)``. The per-run ``apply`` flag must
be threaded in as ``apply=apply``; a live call only fires when SAFE_MODE is off
AND apply is True. Otherwise the intended action is logged dry-run and skipped.
"""
from __future__ import annotations
from pathlib import Path

from . import config, safety, log, http
from .http import HttpError


class MetaClient:
    """Graph API wrapper. Auth via bearer headers for reads, token body for writes."""

    def __init__(self, access_token: str | None = None,
                 ad_account_id: str | None = None,
                 api_version: str | None = None):
        self.access_token = access_token or config.META_ACCESS_TOKEN
        self.ad_account_id = ad_account_id or config.META_AD_ACCOUNT_ID
        self.api_version = api_version or config.META_API_VERSION
        self.base = f"https://graph.facebook.com/{self.api_version}"

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    def _acct(self) -> str:
        """Normalize ad account id to the ``act_<id>`` form Graph expects."""
        acct = self.ad_account_id or ""
        if acct and not acct.startswith("act_"):
            acct = f"act_{acct}"
        return acct

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _params(self, extra: dict | None = None) -> dict:
        params = {}
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def _strip_auth_from_url(self, url: str) -> str:
        import urllib.parse

        parts = urllib.parse.urlsplit(url)
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "access_token"
        ]
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
        )

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """GET a Graph edge, transparently following ``paging.next``. Returns
        the concatenated ``data`` array, or [] if unconfigured / on error."""
        if not self.configured:
            log.warn("MetaClient read skipped — META_ACCESS_TOKEN not set", path=path)
            return []
        url = f"{self.base}/{path.lstrip('/')}"
        out: list[dict] = []
        next_url: str | None = None
        try:
            resp = http.get(url, params=self._params(params), headers=self._auth_headers())
            while True:
                if isinstance(resp, dict):
                    out.extend(resp.get("data", []) or [])
                    next_url = (resp.get("paging") or {}).get("next")
                else:
                    break
                if not next_url:
                    break
                resp = http.get(self._strip_auth_from_url(next_url), headers=self._auth_headers())
            return out
        except HttpError as e:
            log.error("Meta read failed", path=path, status=e.status, body=e.body[:200])
            return []
        except Exception as e:  # noqa: BLE001 - reads must never crash a pipeline
            log.error("Meta read error", path=path, err=str(e))
            return []

    # ------------------------------------------------------------------ #
    # READ methods (free, no guard)
    # ------------------------------------------------------------------ #
    def get_insights(self, level: str = "ad",
                     fields: list[str] | None = None,
                     time_range: dict | None = None,
                     date_preset: str | None = None,
                     extra_params: dict | None = None) -> list[dict]:
        """Pull insights at a given level ('account'|'campaign'|'adset'|'ad').

        ``time_range`` is a {'since','until'} dict (YYYY-MM-DD); if omitted you
        may pass ``date_preset`` (e.g. 'last_7d'). Returns raw insight rows.
        """
        if fields is None:
            fields = [
                "date_start", "date_stop", "account_id", "campaign_id",
                "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
                "spend", "impressions", "clicks", "ctr", "frequency",
                "actions", "action_values",
            ]
        params: dict = {"level": level, "fields": ",".join(fields)}
        if time_range:
            import json as _json
            params["time_range"] = _json.dumps(time_range)
        elif date_preset:
            params["date_preset"] = date_preset
        else:
            params["date_preset"] = "last_7d"
        params["time_increment"] = 1  # one row per day
        if extra_params:
            params.update(extra_params)
        acct = self._acct()
        if not acct:
            log.warn("get_insights skipped — META_AD_ACCOUNT_ID not set")
            return []
        return self._get(f"{acct}/insights", params)

    def list_campaigns(self, fields: list[str] | None = None) -> list[dict]:
        fields = fields or ["id", "name", "status", "objective", "daily_budget",
                            "lifetime_budget", "effective_status"]
        acct = self._acct()
        if not acct:
            return []
        return self._get(f"{acct}/campaigns", {"fields": ",".join(fields), "limit": 200})

    def list_adsets(self, fields: list[str] | None = None) -> list[dict]:
        fields = fields or ["id", "name", "status", "effective_status",
                            "daily_budget", "lifetime_budget", "campaign_id",
                            "optimization_goal", "bid_amount"]
        acct = self._acct()
        if not acct:
            return []
        return self._get(f"{acct}/adsets", {"fields": ",".join(fields), "limit": 500})

    def list_ads(self, fields: list[str] | None = None) -> list[dict]:
        fields = fields or ["id", "name", "status", "effective_status",
                            "adset_id", "campaign_id", "creative"]
        acct = self._acct()
        if not acct:
            return []
        return self._get(f"{acct}/ads", {"fields": ",".join(fields), "limit": 500})

    def get_adset(self, adset_id: str, fields: list[str] | None = None) -> dict:
        """Fetch a single adset object. Returns {} if unconfigured / error."""
        if not self.configured:
            log.warn("get_adset skipped — META_ACCESS_TOKEN not set", adset_id=adset_id)
            return {}
        fields = fields or ["id", "name", "status", "effective_status",
                            "daily_budget", "lifetime_budget", "campaign_id",
                            "optimization_goal", "bid_amount"]
        url = f"{self.base}/{adset_id}"
        try:
            resp = http.get(
                url,
                params=self._params({"fields": ",".join(fields)}),
                headers=self._auth_headers(),
            )
            return resp if isinstance(resp, dict) else {}
        except HttpError as e:
            log.error("get_adset failed", adset_id=adset_id, status=e.status)
            return {}
        except Exception as e:  # noqa: BLE001
            log.error("get_adset error", adset_id=adset_id, err=str(e))
            return {}

    # ------------------------------------------------------------------ #
    # WRITE methods (ALWAYS via safety.guard)
    # ------------------------------------------------------------------ #
    def _post(self, path: str, payload: dict):
        """Perform a real authenticated POST. Only ever called inside an
        apply_fn closure that safety.guard decides to execute."""
        url = f"{self.base}/{path.lstrip('/')}"
        body = dict(payload)
        body["access_token"] = self.access_token
        return http.post(url, json_body=body)

    def _post_image(self, path: str, image_path: Path):
        """Multipart image upload. Only called inside safety.guard apply_fn."""
        import requests

        url = f"{self.base}/{path.lstrip('/')}"
        with image_path.open("rb") as fh:
            resp = requests.post(
                url,
                data={"access_token": self.access_token},
                files={"filename": (image_path.name, fh, "image/jpeg")},
                timeout=90,
            )
        if resp.status_code >= 400:
            raise HttpError(resp.status_code, resp.text, url)
        return resp.json()

    def update_adset_budget(self, adset_id: str, daily_budget_cents: int,
                            *, adset_name: str = "", apply: bool = False):
        """Set an adset's daily budget (Meta budgets are in minor units/cents)."""
        payload = {"daily_budget": int(daily_budget_cents)}

        def apply_fn():
            return self._post(adset_id, payload)

        return safety.guard(
            "meta.adset.update_budget",
            adset_name or adset_id,
            {"adset_id": adset_id, **payload},
            apply_fn if self.configured else None,
            apply=apply,
        )

    def set_adset_status(self, adset_id: str, status: str,
                         *, adset_name: str = "", apply: bool = False):
        """Pause/activate an adset. status in {'ACTIVE','PAUSED'}."""
        status = str(status).upper()
        payload = {"status": status}

        def apply_fn():
            return self._post(adset_id, payload)

        return safety.guard(
            "meta.adset.set_status",
            adset_name or adset_id,
            {"adset_id": adset_id, **payload},
            apply_fn if self.configured else None,
            apply=apply,
        )

    def update_adset_targeting(
        self,
        adset_id: str,
        targeting: dict,
        *,
        adset_name: str = "",
        apply: bool = False,
    ):
        """Replace an adset's targeting payload."""
        payload = {"targeting": targeting}

        def apply_fn():
            return self._post(adset_id, payload)

        return safety.guard(
            "meta.adset.update_targeting",
            adset_name or adset_id,
            {"adset_id": adset_id, **payload},
            apply_fn if self.configured else None,
            apply=apply,
        )

    def create_campaign(self, spec: dict, *, apply: bool = False):
        """Create a campaign under the ad account. ``spec`` is the raw payload
        (name, objective, status, special_ad_categories, ...)."""
        acct = self._acct()
        payload = dict(spec)
        payload.setdefault("status", "PAUSED")  # never auto-launch live

        def apply_fn():
            return self._post(f"{acct}/campaigns", payload)

        return safety.guard(
            "meta.campaign.create",
            spec.get("name", "<new campaign>"),
            payload,
            apply_fn if (self.configured and acct) else None,
            apply=apply,
        )

    def create_adset(self, spec: dict, *, apply: bool = False):
        """Create an adset. ``spec`` carries campaign_id, daily_budget, targeting,
        billing_event, optimization_goal, etc."""
        acct = self._acct()
        payload = dict(spec)
        payload.setdefault("status", "PAUSED")

        def apply_fn():
            return self._post(f"{acct}/adsets", payload)

        return safety.guard(
            "meta.adset.create",
            spec.get("name", "<new adset>"),
            payload,
            apply_fn if (self.configured and acct) else None,
            apply=apply,
        )

    def create_ad(self, spec: dict, *, apply: bool = False):
        """Create an ad. ``spec`` carries adset_id, creative {creative_id}, name."""
        acct = self._acct()
        payload = dict(spec)
        payload.setdefault("status", "PAUSED")

        def apply_fn():
            return self._post(f"{acct}/ads", payload)

        return safety.guard(
            "meta.ad.create",
            spec.get("name", "<new ad>"),
            payload,
            apply_fn if (self.configured and acct) else None,
            apply=apply,
        )

    def update_ad_creative(
        self,
        ad_id: str,
        creative_id: str,
        *,
        ad_name: str = "",
        apply: bool = False,
    ):
        """Swap an existing ad to a new creative (e.g. after re-uploading video)."""
        payload = {"creative": {"creative_id": creative_id}}

        def apply_fn():
            return self._post(ad_id, payload)

        return safety.guard(
            "meta.ad.update_creative",
            ad_name or ad_id,
            {"ad_id": ad_id, **payload},
            apply_fn if self.configured else None,
            apply=apply,
        )

    def set_ad_status(self, ad_id: str, status: str, *, ad_name: str = "", apply: bool = False):
        """Pause/activate an ad. status in {'ACTIVE','PAUSED'}."""
        status = str(status).upper()
        payload = {"status": status}

        def apply_fn():
            return self._post(ad_id, payload)

        return safety.guard(
            "meta.ad.set_status",
            ad_name or ad_id,
            {"ad_id": ad_id, **payload},
            apply_fn if self.configured else None,
            apply=apply,
        )

    def upload_creative(self, spec: dict, *, apply: bool = False):
        """Create an ad creative in the account creative library. ``spec`` carries
        name + object_story_spec (or asset_feed_spec)."""
        acct = self._acct()
        payload = dict(spec)

        def apply_fn():
            return self._post(f"{acct}/adcreatives", payload)

        return safety.guard(
            "meta.creative.upload",
            spec.get("name", "<new creative>"),
            payload,
            apply_fn if (self.configured and acct) else None,
            apply=apply,
        )

    def upload_image(self, image_path: str | Path, *, name: str | None = None, apply: bool = False):
        """Upload an image to the ad account image library and return image hashes."""
        acct = self._acct()
        src = Path(image_path)
        payload = {"path": str(src), "name": name or src.name}

        def apply_fn():
            return self._post_image(f"{acct}/adimages", src)

        return safety.guard(
            "meta.image.upload",
            name or src.name,
            payload,
            apply_fn if (self.configured and acct and src.exists()) else None,
            apply=apply,
        )

    def _post_video(self, path: str, video_path: Path):
        """Multipart video upload to advideos. Only called inside safety.guard apply_fn."""
        import requests

        url = f"{self.base}/{path.lstrip('/')}"
        suffix = video_path.suffix.lower()
        mime = "video/quicktime" if suffix in {".mov", ".qt"} else "video/mp4"
        with video_path.open("rb") as fh:
            resp = requests.post(
                url,
                data={"access_token": self.access_token, "title": video_path.stem},
                files={"source": (video_path.name, fh, mime)},
                timeout=300,
            )
        if resp.status_code >= 400:
            raise HttpError(resp.status_code, resp.text, url)
        return resp.json()

    def upload_video(self, video_path: str | Path, *, name: str | None = None, apply: bool = False):
        """Upload a video to the ad account video library; returns {id: video_id, ...}."""
        acct = self._acct()
        src = Path(video_path)
        payload = {"path": str(src), "name": name or src.name}

        def apply_fn():
            return self._post_video(f"{acct}/advideos", src)

        return safety.guard(
            "meta.video.upload",
            name or src.name,
            payload,
            apply_fn if (self.configured and acct and src.exists()) else None,
            apply=apply,
        )

    # ------------------------------------------------------------------ #
    # diagnostics
    # ------------------------------------------------------------------ #
    def check(self) -> dict:
        """Safe read test for --check. Returns a small status dict."""
        out = {
            "configured": self.configured,
            "ad_account_id": self._acct() or None,
            "api_version": self.api_version,
        }
        if not self.configured:
            out["read_test"] = "skipped (no token)"
            return out
        campaigns = self.list_campaigns()
        out["read_test"] = "ok"
        out["campaigns_found"] = len(campaigns)
        return out
