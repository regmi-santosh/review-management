import stat
import tempfile
import unittest
import unittest.mock
from pathlib import Path

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

    def test_social_platforms_unset_means_none(self):
        with temp_business(business_facts={}) as business:
            self.assertIsNone(business.social_platforms)

    def test_social_platforms_explicit_empty_list_is_preserved(self):
        with temp_business(business_facts={"social_platforms": []}) as business:
            self.assertEqual(business.social_platforms, [])

    def test_social_platforms_explicit_list_is_preserved(self):
        with temp_business(business_facts={"social_platforms": ["facebook"]}) as business:
            self.assertEqual(business.social_platforms, ["facebook"])


class LocationIdsTests(unittest.TestCase):
    def test_no_location_configured(self):
        with temp_business(business_facts={}) as business:
            self.assertEqual(business.google_location_ids, [])

    def test_single_location_id_wrapped_in_list(self):
        with temp_business(business_facts={"google_location_id": "loc-1"}) as business:
            self.assertEqual(business.google_location_ids, ["loc-1"])

    def test_multiple_location_ids(self):
        with temp_business(business_facts={"google_location_ids": ["loc-1", "loc-2"]}) as business:
            self.assertEqual(business.google_location_ids, ["loc-1", "loc-2"])

    def test_plural_list_takes_priority_over_singular(self):
        facts = {"google_location_id": "loc-1", "google_location_ids": ["loc-2", "loc-3"]}
        with temp_business(business_facts=facts) as business:
            self.assertEqual(business.google_location_ids, ["loc-2", "loc-3"])

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

    def test_meta_and_instagram_secrets_persist_and_are_readable(self):
        with temp_business() as business:
            business.save_secret("META_APP_ID", "app-1")
            business.save_secret("META_APP_SECRET", "secret-1")
            business.save_secret("META_CONFIG_ID", "config-1")
            business.save_secret("INSTAGRAM_BUSINESS_ACCOUNT_ID", "ig-1")
            self.assertEqual(business.meta_app_id, "app-1")
            self.assertEqual(business.meta_app_secret, "secret-1")
            self.assertEqual(business.meta_config_id, "config-1")
            self.assertEqual(business.instagram_business_account_id, "ig-1")

    def test_meta_app_id_falls_back_to_process_env(self):
        import os

        with temp_business() as business:
            os.environ["META_APP_ID"] = "top-level-app-id"
            try:
                self.assertEqual(business.meta_app_id, "top-level-app-id")
            finally:
                del os.environ["META_APP_ID"]


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


class ResolvedConfigTests(unittest.TestCase):
    """use_resolved_config()/Business.from_resolved_config() - the seam an
    external caller (e.g. tenant-registry) uses to supply facts/secrets
    directly instead of this process reading local business.json/.env
    files itself."""

    def test_populates_facts_and_secrets(self):
        config.use_resolved_config(
            "acme-salon",
            facts={"name": "Acme Salon", "maps_url": "https://maps.example/acme"},
            secrets={"GOOGLE_OAUTH_CLIENT_ID": "resolved-client-id"},
        )
        business = config.active()
        self.assertEqual(business.slug, "acme-salon")
        self.assertEqual(business.name, "Acme Salon")
        self.assertEqual(business.maps_url, "https://maps.example/acme")
        self.assertEqual(business.google_oauth_client_id, "resolved-client-id")

    def test_defaults_name_to_slug_when_facts_omit_it(self):
        config.use_resolved_config("acme-salon", facts={}, secrets={})
        self.assertEqual(config.active().name, "acme-salon")

    def test_dir_still_points_at_local_businesses_layout(self):
        # db_path/logs/social_images still live under this repo's local
        # businesses/<slug>/ tree for now, even though facts/secrets came
        # from elsewhere - see from_resolved_config()'s docstring.
        config.use_resolved_config("acme-salon", facts={"name": "Acme"}, secrets={})
        business = config.active()
        self.assertTrue(str(business.db_path).endswith("businesses/acme-salon/reviews.db"))

    def test_business_dir_override_redirects_everything_relative_to_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp) / "some-other-location"
            config.use_resolved_config(
                "acme-salon", facts={"name": "Acme"}, secrets={}, business_dir=custom_dir
            )
            business = config.active()
            self.assertEqual(business.dir, custom_dir)
            self.assertEqual(business.db_path, custom_dir / "reviews.db")
            self.assertEqual(business.profile_path, custom_dir / "profile.md")
            self.assertEqual(business.env_path, custom_dir / ".env")

    def test_business_dir_override_defaults_to_local_layout_when_omitted(self):
        config.use_resolved_config("acme-salon", facts={"name": "Acme"}, secrets={}, business_dir=None)
        business = config.active()
        self.assertTrue(str(business.dir).endswith("businesses/acme-salon"))

    def test_equivalent_to_reading_the_same_data_from_files(self):
        with temp_businesses_root() as root:
            facts = {"name": "File Business", "maps_url": "https://maps.example/file"}
            make_business_dir(root, "file-biz", facts)
            config.use_business("file-biz")
            config.active().save_secret("GOOGLE_OAUTH_CLIENT_ID", "file-secret")
            from_file = config.active()

            config.use_resolved_config("file-biz", facts=facts, secrets={"GOOGLE_OAUTH_CLIENT_ID": "file-secret"})
            from_resolved = config.active()

            self.assertEqual(from_file.name, from_resolved.name)
            self.assertEqual(from_file.maps_url, from_resolved.maps_url)
            self.assertEqual(from_file.google_oauth_client_id, from_resolved.google_oauth_client_id)


if __name__ == "__main__":
    unittest.main()
