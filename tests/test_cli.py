import argparse
import unittest

from lib import config
from lib.cli import add_business_arg, apply_business_arg
from tests.helpers import temp_businesses_root, make_business_dir


def _parse(argv):
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    return parser.parse_args(argv)


class CliBusinessArgTests(unittest.TestCase):
    def test_explicit_business_flag_switches_active(self):
        with temp_businesses_root() as root:
            make_business_dir(root, "biz-a", {"name": "A"})
            make_business_dir(root, "biz-b", {"name": "B"})
            config.use_business("biz-a")

            args = _parse(["--business", "biz-b"])
            apply_business_arg(args)

            self.assertEqual(config.active().slug, "biz-b")
            self.assertEqual(config.active().name, "B")

    def test_omitted_flag_leaves_active_business_unchanged(self):
        with temp_businesses_root() as root:
            make_business_dir(root, "biz-a", {"name": "A"})
            config.use_business("biz-a")

            args = _parse([])
            apply_business_arg(args)

            self.assertEqual(config.active().slug, "biz-a")


if __name__ == "__main__":
    unittest.main()
