#!/usr/bin/env python3
"""Record a summary of one review-handler run, so run history survives
beyond the chat transcript it happened in. Called by the agent at the end
of Step 6 (Summarize), using the tallies it already tracked while
processing this run's reviews.

Usage:
  python3 tools/log_run.py --fetched 362 --already-replied 331 --processed 31 \
    --posted 28 --escalated 1 --queued 2 --notes "one escalation: skin reaction complaint"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--fetched", type=int, required=True)
    parser.add_argument("--already-replied", type=int, required=True)
    parser.add_argument("--processed", type=int, required=True)
    parser.add_argument("--posted", type=int, required=True)
    parser.add_argument("--escalated", type=int, required=True)
    parser.add_argument("--queued", type=int, required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    apply_business_arg(args)

    conn = store.connect()
    store.log_run(
        conn,
        fetched=args.fetched,
        already_replied=args.already_replied,
        processed=args.processed,
        posted=args.posted,
        escalated=args.escalated,
        queued=args.queued,
        notes=args.notes,
    )
    print("Run logged.")


if __name__ == "__main__":
    main()
