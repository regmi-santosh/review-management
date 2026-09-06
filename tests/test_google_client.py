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

    def test_post_reply_does_not_raise(self):
        with temp_business(seed_reviews=[]):
            MockGoogleBusinessProfileClient().post_reply("x", "hello")  # should not raise


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
