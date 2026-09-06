"""Google Business Profile client — mock (seeded from data/seed_reviews.json)
and live (real API, stdlib urllib only). See README for how to get from mock
to live once Google grants Business Profile API access for this listing.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from lib import config


@dataclass
class RawReview:
    external_id: str
    author_name: str
    rating: int
    text: str
    create_time: str


class GoogleBusinessProfileClient(ABC):
    """Both clients implement this so tools/agent code never changes when
    swapping mock -> live."""

    @abstractmethod
    def fetch_reviews(self) -> List[RawReview]:
        ...

    @abstractmethod
    def post_reply(self, external_id: str, reply_text: str) -> None:
        ...


class MockGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Stands in until Google Business Profile API access is granted for the
    active business (config.BUSINESS_SLUG) — see README."""

    def fetch_reviews(self) -> List[RawReview]:
        raw = json.loads(config.SEED_REVIEWS_PATH.read_text())
        return [RawReview(**item) for item in raw]

    def post_reply(self, external_id: str, reply_text: str) -> None:
        print(f"[mock-google] would post reply to review {external_id}:\n{reply_text}")


def _request(method: str, url: str, headers: Optional[dict] = None, json_body: Optional[dict] = None) -> dict:
    body = json.dumps(json_body).encode() if json_body is not None else None
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
        raise RuntimeError(f"{method} {url} failed: {exc.code} {detail}") from exc


class LiveGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Real Google Business Profile API client.

    Not usable until:
      1. The "Brows & Threading City" listing is verified in Business Profile
         Manager, and
      2. Google approves API access for a Cloud project against that
         verified listing (manual review — see README), and
      3. GOOGLE_OAUTH_* and GOOGLE_BUSINESS_* are filled in .env.

    Uses the My Business reviews sub-resource:
      GET https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews
      PUT https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews/{reviewId}/reply
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    BASE_URL = "https://mybusiness.googleapis.com/v4"

    RATING_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

    def __init__(self) -> None:
        missing_env = [
            name
            for name, value in [
                ("GOOGLE_OAUTH_CLIENT_ID", config.GOOGLE_OAUTH_CLIENT_ID),
                ("GOOGLE_OAUTH_CLIENT_SECRET", config.GOOGLE_OAUTH_CLIENT_SECRET),
                ("GOOGLE_OAUTH_REFRESH_TOKEN", config.GOOGLE_OAUTH_REFRESH_TOKEN),
            ]
            if not value
        ]
        missing_business = [
            name
            for name, value in [
                ("google_account_id", config.GOOGLE_BUSINESS_ACCOUNT_ID),
                ("google_location_id", config.GOOGLE_BUSINESS_LOCATION_ID),
            ]
            if not value
        ]
        if missing_env or missing_business:
            parts = []
            if missing_env:
                parts.append(".env: " + ", ".join(missing_env))
            if missing_business:
                parts.append(
                    f"businesses/{config.BUSINESS_SLUG}/business.json: " + ", ".join(missing_business)
                )
            raise RuntimeError(
                "GOOGLE_CLIENT_MODE=live but missing required settings — "
                + "; ".join(parts)
                + ". See docs/API_SETUP.md."
            )
        self._account_id = config.GOOGLE_BUSINESS_ACCOUNT_ID
        self._location_id = config.GOOGLE_BUSINESS_LOCATION_ID

    def _access_token(self) -> str:
        data = urllib.parse.urlencode(
            {
                "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": config.GOOGLE_OAUTH_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(self.TOKEN_URL, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def fetch_reviews(self) -> List[RawReview]:
        url = f"{self.BASE_URL}/accounts/{self._account_id}/locations/{self._location_id}/reviews"
        data = _request("GET", url, headers=self._headers())
        reviews = []
        for item in data.get("reviews", []):
            reviews.append(
                RawReview(
                    external_id=item["reviewId"],
                    author_name=item.get("reviewer", {}).get("displayName", "Anonymous"),
                    rating=self.RATING_MAP.get(item.get("starRating", "FIVE"), 5),
                    text=item.get("comment", ""),
                    create_time=item["createTime"],
                )
            )
        return reviews

    def post_reply(self, external_id: str, reply_text: str) -> None:
        url = (
            f"{self.BASE_URL}/accounts/{self._account_id}/locations/{self._location_id}"
            f"/reviews/{external_id}/reply"
        )
        _request("PUT", url, headers=self._headers(), json_body={"comment": reply_text})


def get_google_client() -> GoogleBusinessProfileClient:
    if config.GOOGLE_CLIENT_MODE == "live":
        return LiveGoogleBusinessProfileClient()
    return MockGoogleBusinessProfileClient()
