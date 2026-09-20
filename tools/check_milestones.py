#!/usr/bin/env python3
"""Detect newly-crossed milestones for the active business (see
lib/milestones.py for the detection rules) and record them. Called by the
review-handler agent right after tools/fetch_reviews.py, once per run,
regardless of whether that run found any new reviews.

Usage:
  python3 tools/check_milestones.py [--business <slug>]

Prints JSON:
  {"crossed": [{"milestone_id": 1, "type": "review_count", "threshold": 500,
                "reached_review_id": 368}, ...]}
Empty list means nothing new this run - still exit 0, this is the normal case.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store
from lib.cli import add_business_arg, apply_business_arg
from lib.milestones import check_milestones


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    crossed = check_milestones(conn, config.active())

    print(json.dumps({"crossed": crossed}, indent=2))


if __name__ == "__main__":
    main()
