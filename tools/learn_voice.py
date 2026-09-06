#!/usr/bin/env python3
"""Sample a business's own pre-existing review replies (genuinely written by
a human before this system existed — never ones this system posted, to
avoid learning from its own drafts) and write them to a file for a human
(or an agent-assisted pass) to turn into businesses/<slug>/profile.md's
voice section.

This automates the mechanical part of what was done by hand for Brows &
Threading City: sample owner-written replies, pair them with their review,
format them for reading. The judgment of turning that sample into prose
voice guidance is still a separate step — read the output file and write
profile.md yourself (or ask an agent to).

Requires the business to have been fetched at least once in live mode
(GOOGLE_CLIENT_MODE=live / business.json's google_client_mode=live) so its
DB actually has real historic replies to sample from.

Usage:
  python3 tools/learn_voice.py --business <slug>
  python3 tools/learn_voice.py --business <slug> --sample-size 30 --seed 1
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store
from lib.cli import add_business_arg, apply_business_arg


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for reproducible sampling.")
    parser.add_argument(
        "--out", default=None, help="Output path (default: businesses/<slug>/voice_sample.md)."
    )
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()
    conn = store.connect()
    rows = [
        r
        for r in store.list_reviews(conn)
        if r["status"] == "posted" and r["reply_source"] == "owner" and r["posted_reply"]
    ]

    if not rows:
        print(
            f"error: no pre-existing owner replies found for business '{business.slug}'. "
            "This needs at least one live fetch (GOOGLE_CLIENT_MODE=live) against a listing "
            "that already has some owner replies on Google.",
            file=sys.stderr,
        )
        sys.exit(1)

    with_text = [r for r in rows if r["text"].strip()]
    without_text = [r for r in rows if not r["text"].strip()]

    rng = random.Random(args.seed)
    sample_size = min(args.sample_size, len(with_text))
    sample = rng.sample(with_text, sample_size)
    # A couple of no-review-text examples too, if any exist - the generic
    # thank-you pattern used for those is worth capturing separately.
    blank_sample = rng.sample(without_text, min(2, len(without_text)))

    out_path = Path(args.out) if args.out else business.dir / "voice_sample.md"
    lines = [
        f"# Voice sample for {business.name}",
        "",
        f"{len(rows)} pre-existing owner replies found; {len(sample)} with review text sampled below"
        + (f", plus {len(blank_sample)} from reviews with no written text." if blank_sample else "."),
        "",
        "Read these, then write/update `profile.md`'s voice section: note the opening pattern, "
        "recurring phrases, emoji use, how specific details get echoed back, and the closing pattern.",
        "",
    ]
    for r in sample + blank_sample:
        lines.append(f"---\n**{r['rating']}★ review:** {r['text'] or '(no written text)'}")
        lines.append(f"**Reply:** {r['posted_reply']}")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"Sampled {len(sample) + len(blank_sample)} of {len(rows)} owner replies.")
    print(f"Written to {out_path}")
    print("Next: read that file and update businesses/<slug>/profile.md's voice section.")


if __name__ == "__main__":
    main()
