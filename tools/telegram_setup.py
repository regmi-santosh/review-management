#!/usr/bin/env python3
"""One-time helper to connect a Telegram bot for escalation alerts.

Setup (for the business owner, done once, no coding involved):
  1. Open Telegram and search for "BotFather" (the official bot, verified
     blue checkmark). Start a chat with it.
  2. Send: /newbot
  3. Follow the prompts: pick a display name (e.g. "Brows and Threading
     Alerts"), then a username ending in "bot" (e.g. "BrowsThreadingAlertsBot").
  4. BotFather replies with a token that looks like "123456789:AAF...".
     Copy it.
  5. Open a chat with your new bot (search its username, or tap the link
     BotFather gave you) and send it any message, e.g. "hi".
  6. Hand the token from step 4 to whoever is running this script.

Then, from the repo:
  python3 tools/telegram_setup.py --business <slug> --bot-token <token>

This finds the chat you started in step 5, saves the bot token and chat id
into businesses/<slug>/.env, and sends a confirmation message so you can
verify it's working immediately.

Usage: python3 tools/telegram_setup.py [--business <slug>] --bot-token <token>
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config
from lib.cli import add_business_arg, apply_business_arg


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"error: {exc.code} {exc.read().decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    add_business_arg(parser)
    parser.add_argument("--bot-token", required=True)
    args = parser.parse_args()
    apply_business_arg(args)

    business = config.active()

    updates = _get(f"https://api.telegram.org/bot{args.bot_token}/getUpdates")
    if not updates.get("ok"):
        print(f"error: Telegram API rejected this token: {updates}", file=sys.stderr)
        sys.exit(1)

    results = updates.get("result", [])
    if not results:
        print(
            "No messages found yet. In Telegram, open a chat with your bot and send it "
            "any message (e.g. 'hi'), then re-run this exact command.",
            file=sys.stderr,
        )
        sys.exit(1)

    chat = results[-1].get("message", {}).get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        print(f"error: couldn't find a chat id in the response: {results[-1]}", file=sys.stderr)
        sys.exit(1)
    name = chat.get("first_name") or chat.get("title") or "unknown"

    business.save_secret("TELEGRAM_BOT_TOKEN", args.bot_token)
    business.save_secret("TELEGRAM_CHAT_ID", str(chat_id))
    print(f"Found chat with {name} (chat_id={chat_id}). Saved to businesses/{business.slug}/.env.")

    print("Sending a confirmation message...")
    confirm_url = f"https://api.telegram.org/bot{args.bot_token}/sendMessage"
    body = json.dumps(
        {
            "chat_id": chat_id,
            "text": (
                f"✅ Connected! You'll get an alert here whenever a review for "
                f"{business.name} needs urgent attention."
            ),
        }
    ).encode()
    req = urllib.request.Request(confirm_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10):
        pass
    print("Confirmation sent - check Telegram.")


if __name__ == "__main__":
    main()
