import logging
import unittest

from lib import logging_setup
from tests.helpers import temp_business


class GetLoggerTests(unittest.TestCase):
    def tearDown(self):
        # get_logger's per-business handler cache is process-global; clear
        # it and drop handlers so temp business dirs from earlier tests
        # don't leak handlers pointed at now-deleted directories.
        for slug in list(logging_setup._configured_businesses):
            root = logging.getLogger(f"review_management.{slug}")
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
        logging_setup._configured_businesses.clear()

    def test_creates_log_dir_and_file(self):
        with temp_business(slug="log-test-biz") as business:
            logger = logging_setup.get_logger("mymodule")
            logger.info("hello")
            for handler in logging.getLogger(f"review_management.{business.slug}").handlers:
                handler.flush()

            log_path = business.dir / "logs" / "app.log"
            self.assertTrue(log_path.exists())
            self.assertIn("hello", log_path.read_text())
            self.assertIn("mymodule", log_path.read_text())

    def test_separate_businesses_get_separate_log_files(self):
        from lib import config
        from tests.helpers import temp_businesses_root, make_business_dir

        with temp_businesses_root() as root:
            make_business_dir(root, "log-test-biz-a")
            make_business_dir(root, "log-test-biz-b")

            config.use_business("log-test-biz-a")
            logging_setup.get_logger("mod").info("from a")
            config.use_business("log-test-biz-b")
            logging_setup.get_logger("mod").info("from b")

            for slug in ("log-test-biz-a", "log-test-biz-b"):
                for handler in logging.getLogger(f"review_management.{slug}").handlers:
                    handler.flush()

            a_log = (root / "log-test-biz-a" / "logs" / "app.log").read_text()
            b_log = (root / "log-test-biz-b" / "logs" / "app.log").read_text()
            self.assertIn("from a", a_log)
            self.assertNotIn("from b", a_log)
            self.assertIn("from b", b_log)
            self.assertNotIn("from a", b_log)


if __name__ == "__main__":
    unittest.main()
