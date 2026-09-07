import io
import unittest
import unittest.mock

from PIL import Image

from lib import social_image
from tests.helpers import temp_business

REVIEW = {"id": 1, "rating": 5, "author_name": "Alice", "text": "Absolutely loved the service here!"}


class RenderQuoteCardTests(unittest.TestCase):
    def test_produces_valid_png_at_requested_size(self):
        with temp_business() as business:
            png_bytes = social_image.render_quote_card(business, REVIEW, (1080, 1080))
            image = Image.open(io.BytesIO(png_bytes))
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1080, 1080))

    def test_works_at_every_platform_aspect_ratio(self):
        with temp_business() as business:
            for size in [(1200, 630), (1080, 1080), (1200, 675), (1080, 1920)]:
                png_bytes = social_image.render_quote_card(business, REVIEW, size)
                image = Image.open(io.BytesIO(png_bytes))
                self.assertEqual(image.size, size)

    def test_degrades_gracefully_with_no_logo_file(self):
        with temp_business() as business:
            self.assertIsNone(business.logo_path)  # no logo.png in this temp business
            png_bytes = social_image.render_quote_card(business, REVIEW, (1080, 1080))
            self.assertGreater(len(png_bytes), 0)

    def test_handles_very_long_review_text_without_error(self):
        with temp_business() as business:
            long_review = {**REVIEW, "text": " ".join(["amazing"] * 200)}
            png_bytes = social_image.render_quote_card(business, long_review, (1080, 1080))
            self.assertGreater(len(png_bytes), 0)

    def test_handles_empty_review_text_without_error(self):
        with temp_business() as business:
            png_bytes = social_image.render_quote_card(business, {**REVIEW, "text": ""}, (1080, 1080))
            self.assertGreater(len(png_bytes), 0)

    def test_respects_custom_brand_color(self):
        facts = {"brand_color": "#112233"}
        with temp_business(business_facts=facts) as business:
            png_bytes = social_image.render_quote_card(business, REVIEW, (1080, 1080))
            image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            self.assertEqual(image.getpixel((1, 1)), (0x11, 0x22, 0x33))

    def test_is_available_true_when_pillow_importable(self):
        self.assertTrue(social_image.is_available())

    def test_raises_clear_runtime_error_when_pillow_unavailable(self):
        with temp_business() as business:
            with unittest.mock.patch.object(social_image, "_PIL_IMPORT_ERROR", ImportError("no module")):
                with self.assertRaisesRegex(RuntimeError, "Pillow not installed"):
                    social_image.render_quote_card(business, REVIEW, (1080, 1080))


if __name__ == "__main__":
    unittest.main()
