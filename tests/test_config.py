import stat
import unittest
import unittest.mock

from lib import config
from tests.helpers import temp_business, temp_businesses_root, make_business_dir


class BusinessFactsTests(unittest.TestCase):
    def test_facts_resolve_from_business_json(self):
        facts = {"name": "Test Co", "maps_url": "https://example.com/place"}
        with temp_business(business_facts=facts) as business:
            self.assertEqual(business.name, "Test Co")
            self.assertEqual(business.maps_url, "https://example.com/place")

    def test_name_falls_back_to_slug_when_no_business_json(self):
        with temp_business(slug="no-facts-biz") as business:
            self.assertEqual(business.name, "no-facts-biz")

    def test_confidence_threshold_override(self):
        with temp_business(business_facts={"confidence_threshold": 0.7}) as business:
            self.assertEqual(business.confidence_threshold, 0.7)

    def test_confidence_threshold_default_when_unset(self):
        with temp_business(business_facts={}) as business:
            self.assertEqual(business.confidence_threshold, 0.85)

    def test_google_client_mode_override(self):
        with temp_business(business_facts={"google_client_mode": "live"}) as business:
            self.assertEqual(business.google_client_mode, "live")

    def test_google_client_mode_default_is_mock(self):
        # Isolated from the real project's top-level .env, which sets this
        # process-wide (GOOGLE_CLIENT_MODE=live for the real business) -
        # without this, the test would see that real value instead of the
        # true "nothing set" default.
        import os

        with temp_business(business_facts={}) as business:
            with unittest.mock.patch.dict(os.environ):
                os.environ.pop("GOOGLE_CLIENT_MODE", None)
                self.assertEqual(business.google_client_mode, "mock")


class SecretsTests(unittest.TestCase):
    def test_save_secret_persists_and_is_readable(self):
        with temp_business() as business:
            business.save_secret("GOOGLE_OAUTH_CLIENT_ID", "abc123")
            self.assertEqual(business.google_oauth_client_id, "abc123")
            # Re-read from disk (still under the patched BUSINESSES_DIR).
            reloaded = config.Business(business.slug)
            self.assertEqual(reloaded.google_oauth_client_id, "abc123")

    def test_save_secret_locks_file_permissions(self):
        with temp_business() as business:
            business.save_secret("GOOGLE_OAUTH_CLIENT_SECRET", "shh")
            mode = stat.S_IMODE(business.env_path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_secret_falls_back_to_process_env(self):
        import os

        with temp_business() as business:
            os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"] = "fallback-token"
            try:
                self.assertEqual(business.google_oauth_refresh_token, "fallback-token")
            finally:
                del os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]

    def test_business_own_secret_wins_over_process_env(self):
        import os

        with temp_business() as business:
            os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "global-id"
            try:
                business.save_secret("GOOGLE_OAUTH_CLIENT_ID", "business-specific-id")
                self.assertEqual(business.google_oauth_client_id, "business-specific-id")
            finally:
                del os.environ["GOOGLE_OAUTH_CLIENT_ID"]


class MultiBusinessTests(unittest.TestCase):
    def test_use_business_switches_active_context(self):
        with temp_businesses_root() as root:
            make_business_dir(root, "biz-a", {"name": "A"})
            make_business_dir(root, "biz-b", {"name": "B"})
            config.use_business("biz-a")
            self.assertEqual(config.active().name, "A")
            config.use_business("biz-b")
            self.assertEqual(config.active().name, "B")

    def test_businesses_are_isolated(self):
        with temp_businesses_root() as root:
            make_business_dir(root, "biz-a", {"name": "A"})
            make_business_dir(root, "biz-b", {"name": "B"})

            config.use_business("biz-a")
            config.active().save_secret("GOOGLE_OAUTH_CLIENT_ID", "a-secret")

            config.use_business("biz-b")
            self.assertEqual(config.active().google_oauth_client_id, "")


if __name__ == "__main__":
    unittest.main()
