"""Shared --business flag handling for tool scripts."""
import argparse

from lib import config


def add_business_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--business",
        default=None,
        help="businesses/<slug> to operate on (default: BUSINESS_SLUG from .env, "
        "or the only directory under businesses/ if there's exactly one).",
    )


def apply_business_arg(args: argparse.Namespace) -> None:
    if args.business:
        config.use_business(args.business)
