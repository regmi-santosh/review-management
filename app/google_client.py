import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List

import httpx
from pydantic import BaseModel

from app.config import settings

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_reviews.json"


class RawReview(BaseModel):
    external_id: str
    author_name: str
    rating: int
    text: str
    create_time: datetime


class GoogleBusinessProfileClient(ABC):
    """Interface both the mock and live clients implement.

    Keeping this interface stable is what lets the pipeline/agent code stay
    untouched when swapping from mock data to the real Google Business
    Profile API once access is granted (see README).
    """

    @abstractmethod
    def fetch_reviews(self) -> List[RawReview]:
        ...

    @abstractmethod
    def post_reply(self, external_id: str, reply_text: str) -> None:
        ...


class MockGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Reads seed data from data/seed_reviews.json.

    Stands in for the real Google Business Profile API until API access for
    this listing is approved (README: "Google Business Profile API access").
    Posted replies are just logged, not sent anywhere.
    """

    def fetch_reviews(self) -> List[RawReview]:
        raw = json.loads(SEED_PATH.read_text())
        return [RawReview(**item) for item in raw]

    def post_reply(self, external_id: str, reply_text: str) -> None:
        print(f"[mock-google] would post reply to review {external_id}:\n{reply_text}")


class LiveGoogleBusinessProfileClient(GoogleBusinessProfileClient):
    """Real Google Business Profile API client.

    Not usable until:
      1. The "Brows & Threading City" listing is verified in Business Profile
         Manager, and
      2. Google approves API access for a Cloud project against that
         verified listing (manual review — see README), and
      3. GOOGLE_OAUTH_* and GOOGLE_BUSINESS_* env vars are filled in.

    Uses the My Business Account Management / Business Information APIs'
    reviews sub-resource:
      GET  https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews
      PUT  https://mybusiness.googleapis.com/v4/accounts/{accountId}/locations/{locationId}/reviews/{reviewId}/reply
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    BASE_URL = "https://mybusiness.googleapis.com/v4"

    def __init__(self) -> None:
        missing = [
            name
            for name, value in [
                ("GOOGLE_OAUTH_CLIENT_ID", settings.google_oauth_client_id),
                ("GOOGLE_OAUTH_CLIENT_SECRET", settings.google_oauth_client_secret),
                ("GOOGLE_OAUTH_REFRESH_TOKEN", settings.google_oauth_refresh_token),
                ("GOOGLE_BUSINESS_ACCOUNT_ID", settings.google_business_account_id),
                ("GOOGLE_BUSINESS_LOCATION_ID", settings.google_business_location_id),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "GOOGLE_CLIENT_MODE=live but missing required settings: "
                + ", ".join(missing)
                + ". See README 'Google Business Profile API access'."
            )
        self._account_id = settings.google_business_account_id
        self._location_id = settings.google_business_location_id

    def _access_token(self) -> str:
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": settings.google_oauth_refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def fetch_reviews(self) -> List[RawReview]:
        url = f"{self.BASE_URL}/accounts/{self._account_id}/locations/{self._location_id}/reviews"
        resp = httpx.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        reviews = []
        for item in resp.json().get("reviews", []):
            rating_map = {
                "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
            }
            reviews.append(
                RawReview(
                    external_id=item["reviewId"],
                    author_name=item.get("reviewer", {}).get("displayName", "Anonymous"),
                    rating=rating_map.get(item.get("starRating", "FIVE"), 5),
                    text=item.get("comment", ""),
                    create_time=datetime.fromisoformat(
                        item["createTime"].replace("Z", "+00:00")
                    ),
                )
            )
        return reviews

    def post_reply(self, external_id: str, reply_text: str) -> None:
        url = (
            f"{self.BASE_URL}/accounts/{self._account_id}/locations/{self._location_id}"
            f"/reviews/{external_id}/reply"
        )
        resp = httpx.put(
            url, headers=self._headers(), json={"comment": reply_text}, timeout=15
        )
        resp.raise_for_status()


def get_google_client() -> GoogleBusinessProfileClient:
    if settings.google_client_mode == "live":
        return LiveGoogleBusinessProfileClient()
    return MockGoogleBusinessProfileClient()
