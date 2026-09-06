"""Google Business Profile client — mock (seeded from each business's own
seed_reviews.json) and live (real API, stdlib urllib only). See
docs/API_SETUP.md for how to get from mock to live once Google grants
Business Profile API access for a given business's listing.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from lib import config
from lib.logging_setup import get_logger

# Retry-with-backoff for transient failures (rate limiting, Google-side
# hiccups, network blips) - matters once this runs unattended/scheduled
# rather than always under a human's eye. Non-transient errors (4xx other
# than 429 - bad auth, bad request, not found) fail immediately since
# retrying won't fix them.
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


def _sleep_backoff(attempt: int) -> None:
    time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))


@dataclass
class RawReview:
    external_id: str
    author_name: str
    rating: int
    text: str
    create_time: str
    existing_reply: Optional[str] = None  # set if Google already has an owner reply on this review
    location_id: Optional[str] = None  # which of the business's locations this came from


class GoogleBusinessProfileClient(ABC):
    """Both clients implement this so tools/agent code never changes when
    swapping mock -> live."""

    @abstractmethod
    def fetch_reviews(self) -> List[RawReview]:
        ...

    @abstractmethod
    def post_reply(self, external_id: str, location_id: Optional[str], reply_text: str) -> None:
        ...


class MockGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Stands in until Google Business Profile API access is granted for the
    active business — see README."""

    def fetch_reviews(self) -> List[RawReview]:
        raw = json.loads(config.active().seed_reviews_path.read_text())
        return [RawReview(**item) for item in raw]

    def post_reply(self, external_id: str, location_id: Optional[str], reply_text: str) -> None:
        get_logger("google_client").info(f"[mock] would post reply to review {external_id}")
        print(f"[mock-google] would post reply to review {external_id}:\n{reply_text}")


def _request(method: str, url: str, headers: Optional[dict] = None, json_body: Optional[dict] = None) -> dict:
    body = json.dumps(json_body).encode() if json_body is not None else None
    attempt = 0
    while True:
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                _sleep_backoff(attempt)
                attempt += 1
                continue
            raise RuntimeError(f"{method} {url} failed: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < _MAX_RETRIES:
                _sleep_backoff(attempt)
                attempt += 1
                continue
            raise RuntimeError(f"{method} {url} failed: {exc}") from exc


class LiveGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Real Google Business Profile API client. Supports one or many
    locations under the same account (business.json's google_location_id
    for one, google_location_ids for several) - fetch_reviews() pulls from
    every configured location and tags each review with which one it came
    from, since posting a reply requires knowing the specific location.

    Not usable until:
      1. The business's listing is verified in Business Profile Manager, and
      2. Google approves API access for a Cloud project against that
         verified listing (manual review — see docs/API_SETUP.md), and
      3. The business has its own OAuth credentials and location IDs set —
         see businesses/<slug>/.env and business.json.

    Uses the My Business reviews sub-resource:
      GET https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews
      PUT https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews/{reviewId}/reply
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    BASE_URL = "https://mybusiness.googleapis.com/v4"

    RATING_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

    def __init__(self) -> None:
        business = config.active()
        missing_secrets = [
            name
            for name, value in [
                ("GOOGLE_OAUTH_CLIENT_ID", business.google_oauth_client_id),
                ("GOOGLE_OAUTH_CLIENT_SECRET", business.google_oauth_client_secret),
                ("GOOGLE_OAUTH_REFRESH_TOKEN", business.google_oauth_refresh_token),
            ]
            if not value
        ]
        missing_facts = [
            name
            for name, value in [
                ("google_account_id", business.google_account_id),
                ("google_location_id(s)", "yes" if business.google_location_ids else ""),
            ]
            if not value
        ]
        if missing_secrets or missing_facts:
            parts = []
            if missing_secrets:
                parts.append(f"businesses/{business.slug}/.env (or top-level .env): " + ", ".join(missing_secrets))
            if missing_facts:
                parts.append(f"businesses/{business.slug}/business.json: " + ", ".join(missing_facts))
            raise RuntimeError(
                "GOOGLE_CLIENT_MODE=live but missing required settings — "
                + "; ".join(parts)
                + ". See docs/API_SETUP.md."
            )
        self._account_id = business.google_account_id
        self._location_ids = business.google_location_ids
        self._client_id = business.google_oauth_client_id
        self._client_secret = business.google_oauth_client_secret
        self._refresh_token = business.google_oauth_refresh_token

    def _access_token(self) -> str:
        data = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()
        attempt = 0
        while True:
            try:
                req = urllib.request.Request(self.TOKEN_URL, data=data, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())["access_token"]
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                if exc.code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                    _sleep_backoff(attempt)
                    attempt += 1
                    continue
                raise RuntimeError(f"token refresh failed: {exc.code} {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_RETRIES:
                    _sleep_backoff(attempt)
                    attempt += 1
                    continue
                raise RuntimeError(f"token refresh failed: {exc}") from exc

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def fetch_reviews(self) -> List[RawReview]:
        headers = self._headers()
        reviews = []
        for location_id in self._location_ids:
            base_url = f"{self.BASE_URL}/accounts/{self._account_id}/locations/{location_id}/reviews"
            page_token = None
            while True:
                url = f"{base_url}?pageToken={page_token}" if page_token else base_url
                data = _request("GET", url, headers=headers)
                for item in data.get("reviews", []):
                    reviews.append(
                        RawReview(
                            external_id=item["reviewId"],
                            author_name=item.get("reviewer", {}).get("displayName", "Anonymous"),
                            rating=self.RATING_MAP.get(item.get("starRating", "FIVE"), 5),
                            text=item.get("comment", ""),
                            create_time=item["createTime"],
                            existing_reply=item.get("reviewReply", {}).get("comment") or None,
                            location_id=location_id,
                        )
                    )
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
        get_logger("google_client").info(f"fetched {len(reviews)} reviews from Google (account={self._account_id})")
        return reviews

    def post_reply(self, external_id: str, location_id: Optional[str], reply_text: str) -> None:
        if not location_id:
            raise ValueError(
                f"review {external_id} has no location_id recorded - can't post a reply without "
                "knowing which location it belongs to (this shouldn't happen for reviews fetched "
                "after multi-location support was added; check the DB migration)."
            )
        url = f"{self.BASE_URL}/accounts/{self._account_id}/locations/{location_id}/reviews/{external_id}/reply"
        _request("PUT", url, headers=self._headers(), json_body={"comment": reply_text})
        get_logger("google_client").info(f"posted reply to Google for review {external_id}")


def get_google_client() -> GoogleBusinessProfileClient:
    if config.active().google_client_mode == "live":
        return LiveGoogleBusinessProfileClient()
    return MockGoogleBusinessProfileClient()
