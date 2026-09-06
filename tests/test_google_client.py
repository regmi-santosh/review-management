import io
import unittest
import urllib.error
from unittest.mock import patch

from lib import google_client
from lib.google_client import MockGoogleBusinessProfileClient
from tests.helpers import temp_business


class MockClientTests(unittest.TestCase):
    def test_fetch_reviews_reads_seed_file(self):
        seed = [
            {
                "external_id": "s1",
                "author_name": "A",
                "rating": 5,
                "text": "hi",
                "create_time": "2026-01-01T00:00:00Z",
            }
        ]
        with temp_business(seed_reviews=seed):
            reviews = MockGoogleBusinessProfileClient().fetch_reviews()
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].external_id, "s1")
            self.assertIsNone(reviews[0].existing_reply)
            self.assertIsNone(reviews[0].location_id)
            self.assertIsNone(reviews[0].profile_photo_url)
            self.assertFalse(reviews[0].is_anonymous)

    def test_fetch_reviews_picks_up_reviewer_detail_from_seed(self):
        seed = [
            {
                "external_id": "s3",
                "author_name": "A Google User",
                "rating": 5,
                "text": "hi",
                "create_time": "2026-01-01T00:00:00Z",
                "profile_photo_url": "https://example.com/photo.jpg",
                "is_anonymous": True,
            }
        ]
        with temp_business(seed_reviews=seed):
            reviews = MockGoogleBusinessProfileClient().fetch_reviews()
            self.assertEqual(reviews[0].profile_photo_url, "https://example.com/photo.jpg")
            self.assertTrue(reviews[0].is_anonymous)

    def test_fetch_reviews_picks_up_location_id_from_seed(self):
        seed = [
            {
                "external_id": "s2",
                "author_name": "B",
                "rating": 4,
                "text": "ok",
                "create_time": "2026-01-01T00:00:00Z",
                "location_id": "loc-42",
            }
        ]
        with temp_business(seed_reviews=seed):
            reviews = MockGoogleBusinessProfileClient().fetch_reviews()
            self.assertEqual(reviews[0].location_id, "loc-42")

    def test_post_reply_does_not_raise(self):
        with temp_business(seed_reviews=[]):
            MockGoogleBusinessProfileClient().post_reply("x", "loc-1", "hello")  # should not raise


def _authorized_business_facts(location_ids):
    return {"google_account_id": "acct-1", "google_location_ids": location_ids}


def _with_oauth_secrets(business):
    business.save_secret("GOOGLE_OAUTH_CLIENT_ID", "cid")
    business.save_secret("GOOGLE_OAUTH_CLIENT_SECRET", "csecret")
    business.save_secret("GOOGLE_OAUTH_REFRESH_TOKEN", "rtoken")
    return business


class LiveClientMultiLocationTests(unittest.TestCase):
    def test_fetch_reviews_pulls_from_every_location_and_tags_them(self):
        facts = _authorized_business_facts(["loc-1", "loc-2"])
        with temp_business(business_facts=facts) as business:
            _with_oauth_secrets(business)
            client = google_client.LiveGoogleBusinessProfileClient()

            def fake_request(method, url, headers=None, json_body=None):
                if "loc-1" in url:
                    return {
                        "reviews": [
                            {
                                "reviewId": "r1",
                                "reviewer": {"displayName": "A"},
                                "starRating": "FIVE",
                                "comment": "hi",
                                "createTime": "2026-01-01T00:00:00Z",
                            }
                        ]
                    }
                if "loc-2" in url:
                    return {
                        "reviews": [
                            {
                                "reviewId": "r2",
                                "reviewer": {"displayName": "B"},
                                "starRating": "FOUR",
                                "comment": "ok",
                                "createTime": "2026-01-02T00:00:00Z",
                            }
                        ]
                    }
                return {"reviews": []}

            with patch.object(client, "_headers", return_value={}):
                with patch("lib.google_client._request", side_effect=fake_request):
                    reviews = client.fetch_reviews()

            by_id = {r.external_id: r for r in reviews}
            self.assertEqual(set(by_id), {"r1", "r2"})
            self.assertEqual(by_id["r1"].location_id, "loc-1")
            self.assertEqual(by_id["r2"].location_id, "loc-2")

    def test_fetch_reviews_parses_reviewer_detail_from_response(self):
        facts = _authorized_business_facts(["loc-1"])
        with temp_business(business_facts=facts) as business:
            _with_oauth_secrets(business)
            client = google_client.LiveGoogleBusinessProfileClient()

            def fake_request(method, url, headers=None, json_body=None):
                return {
                    "reviews": [
                        {
                            "reviewId": "r1",
                            "reviewer": {
                                "displayName": "A Google User",
                                "profilePhotoUrl": "https://example.com/photo.jpg",
                                "isAnonymous": True,
                            },
                            "starRating": "FIVE",
                            "comment": "hi",
                            "createTime": "2026-01-01T00:00:00Z",
                        }
                    ]
                }

            with patch.object(client, "_headers", return_value={}):
                with patch("lib.google_client._request", side_effect=fake_request):
                    reviews = client.fetch_reviews()

            self.assertEqual(reviews[0].profile_photo_url, "https://example.com/photo.jpg")
            self.assertTrue(reviews[0].is_anonymous)

    def test_fetch_reviews_defaults_reviewer_detail_when_absent(self):
        facts = _authorized_business_facts(["loc-1"])
        with temp_business(business_facts=facts) as business:
            _with_oauth_secrets(business)
            client = google_client.LiveGoogleBusinessProfileClient()

            def fake_request(method, url, headers=None, json_body=None):
                return {
                    "reviews": [
                        {
                            "reviewId": "r1",
                            "reviewer": {"displayName": "A"},
                            "starRating": "FIVE",
                            "comment": "hi",
                            "createTime": "2026-01-01T00:00:00Z",
                        }
                    ]
                }

            with patch.object(client, "_headers", return_value={}):
                with patch("lib.google_client._request", side_effect=fake_request):
                    reviews = client.fetch_reviews()

            self.assertIsNone(reviews[0].profile_photo_url)
            self.assertFalse(reviews[0].is_anonymous)

    def test_post_reply_uses_given_location_in_url(self):
        facts = _authorized_business_facts(["loc-1", "loc-2"])
        with temp_business(business_facts=facts) as business:
            _with_oauth_secrets(business)
            client = google_client.LiveGoogleBusinessProfileClient()

            captured = {}

            def fake_request(method, url, headers=None, json_body=None):
                captured.update(method=method, url=url, json_body=json_body)
                return {}

            with patch.object(client, "_headers", return_value={}):
                with patch("lib.google_client._request", side_effect=fake_request):
                    client.post_reply("r2", "loc-2", "Thanks!")

            self.assertIn("loc-2", captured["url"])
            self.assertEqual(captured["method"], "PUT")
            self.assertEqual(captured["json_body"], {"comment": "Thanks!"})

    def test_post_reply_without_location_id_raises(self):
        facts = _authorized_business_facts(["loc-1"])
        with temp_business(business_facts=facts) as business:
            _with_oauth_secrets(business)
            client = google_client.LiveGoogleBusinessProfileClient()
            with self.assertRaises(ValueError):
                client.post_reply("r1", None, "Thanks!")

    def test_init_raises_when_no_location_configured(self):
        with temp_business(business_facts={"google_account_id": "acct-1"}) as business:
            _with_oauth_secrets(business)
            with self.assertRaises(RuntimeError):
                google_client.LiveGoogleBusinessProfileClient()


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.com", code=code, msg="err", hdrs=None, fp=io.BytesIO(b'{"error":"x"}')
    )


class RequestRetryTests(unittest.TestCase):
    @patch("time.sleep", return_value=None)
    @patch("urllib.request.urlopen")
    def test_retries_on_503_then_succeeds(self, mock_urlopen, mock_sleep):
        # io.BytesIO already supports the `with ... as resp:` protocol natively.
        success_resp = io.BytesIO(b'{"ok": true}')
        mock_urlopen.side_effect = [_http_error(503), success_resp]

        result = google_client._request("GET", "https://example.com/reviews")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    @patch("urllib.request.urlopen")
    def test_gives_up_after_max_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _http_error(503)

        with self.assertRaises(RuntimeError):
            google_client._request("GET", "https://example.com/reviews")
        # initial attempt + _MAX_RETRIES retries
        self.assertEqual(mock_urlopen.call_count, 1 + google_client._MAX_RETRIES)

    @patch("time.sleep", return_value=None)
    @patch("urllib.request.urlopen")
    def test_non_retryable_error_fails_immediately(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _http_error(404)

        with self.assertRaises(RuntimeError):
            google_client._request("GET", "https://example.com/reviews")
        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
