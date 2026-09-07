import unittest
from unittest.mock import patch

from lib import social_platforms
from tests.helpers import temp_business


class RenderTests(unittest.TestCase):
    def test_facebook_appends_up_to_two_hashtags(self):
        text = social_platforms.FacebookPlatform().render(
            "Great visit!", ["#One", "#Two", "#Three"]
        )
        self.assertEqual(text, "Great visit! #One #Two")

    def test_instagram_appends_up_to_ten_hashtags(self):
        tags = [f"#Tag{i}" for i in range(15)]
        text = social_platforms.InstagramPlatform().render("Caption", tags)
        self.assertEqual(text, "Caption " + " ".join(tags[:10]))

    def test_no_hashtags_leaves_caption_unchanged(self):
        text = social_platforms.FacebookPlatform().render("Just the caption.", [])
        self.assertEqual(text, "Just the caption.")

    def test_twitter_drops_lowest_priority_hashtag_first(self):
        caption = "x" * 270
        text = social_platforms.TwitterPlatform().render(caption, ["#Brows", "#City"])
        self.assertEqual(text, caption + " #Brows")
        self.assertLessEqual(len(text), 280)

    def test_twitter_drops_all_hashtags_when_none_fit(self):
        caption = "x" * 279
        text = social_platforms.TwitterPlatform().render(caption, ["#Brows", "#City"])
        self.assertEqual(text, caption)
        self.assertLessEqual(len(text), 280)

    def test_twitter_truncates_caption_on_word_boundary_as_last_resort(self):
        caption = " ".join(["word"] * 100)
        text = social_platforms.TwitterPlatform().render(caption, [])
        self.assertLessEqual(len(text), 280)
        self.assertTrue(text.endswith("…"))
        self.assertNotIn(" …", text[-2:])

    def test_no_char_limit_never_truncates(self):
        caption = "x" * 5000
        text = social_platforms.FacebookPlatform().render(caption, [])
        self.assertEqual(text, caption)


class RenderAllTests(unittest.TestCase):
    def test_defaults_to_every_registered_platform(self):
        rendered = social_platforms.render_all("Caption", [])
        self.assertEqual(set(rendered), set(social_platforms.available_platforms()))

    def test_respects_platform_allow_list(self):
        rendered = social_platforms.render_all("Caption", [], platforms=["facebook", "tiktok"])
        self.assertEqual(set(rendered), {"facebook", "tiktok"})

    def test_explicit_empty_list_renders_nothing(self):
        rendered = social_platforms.render_all("Caption", [], platforms=[])
        self.assertEqual(rendered, {})

    def test_unknown_platform_name_is_skipped(self):
        rendered = social_platforms.render_all("Caption", [], platforms=["facebook", "myspace"])
        self.assertEqual(set(rendered), {"facebook"})


class PostNotImplementedTests(unittest.TestCase):
    def test_post_raises_until_phase_two(self):
        with temp_business() as business:
            for platform in social_platforms.available_platforms():
                if platform == "facebook":
                    continue  # facebook is implemented - see FacebookPostTests
                with self.assertRaises(NotImplementedError):
                    social_platforms.get_platform(platform).post(business, "/tmp/card.png", "text")


class FacebookPostTests(unittest.TestCase):
    def test_raises_without_credentials(self):
        with temp_business() as business:
            with self.assertRaises(RuntimeError):
                social_platforms.FacebookPlatform().post(business, "/tmp/card.png", "caption")

    def test_raises_without_image(self):
        with temp_business() as business:
            business.save_secret("FACEBOOK_PAGE_ID", "123")
            business.save_secret("FACEBOOK_PAGE_ACCESS_TOKEN", "tok")
            with self.assertRaises(RuntimeError):
                social_platforms.FacebookPlatform().post(business, None, "caption")

    def test_posts_via_graph_api_and_returns_post_id(self):
        with temp_business() as business:
            business.save_secret("FACEBOOK_PAGE_ID", "123")
            business.save_secret("FACEBOOK_PAGE_ACCESS_TOKEN", "tok")
            with patch.object(
                social_platforms, "post_multipart", return_value={"id": "123_456"}
            ) as mock_post:
                post_id = social_platforms.FacebookPlatform().post(business, "/tmp/card.png", "caption")
            self.assertEqual(post_id, "123_456")
            args, _ = mock_post.call_args
            url, fields, file_field, file_path = args
            self.assertIn("123/photos", url)
            self.assertEqual(fields["caption"], "caption")
            self.assertEqual(fields["access_token"], "tok")
            self.assertEqual(file_field, "source")
            self.assertEqual(file_path, "/tmp/card.png")

    def test_raises_on_unexpected_response(self):
        with temp_business() as business:
            business.save_secret("FACEBOOK_PAGE_ID", "123")
            business.save_secret("FACEBOOK_PAGE_ACCESS_TOKEN", "tok")
            with patch.object(social_platforms, "post_multipart", return_value={"error": "nope"}):
                with self.assertRaises(RuntimeError):
                    social_platforms.FacebookPlatform().post(business, "/tmp/card.png", "caption")


if __name__ == "__main__":
    unittest.main()
