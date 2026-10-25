#!/usr/bin/env python3
"""Interactive utility to generate data/cookies.json from browser cookies.

Because X frequently updates its unauthenticated client scripts (causing
'Couldn't get KEY_BYTE indices' on programmatic username/password logins),
providing session cookies directly (auth_token and ct0) is the most reliable,
ToS-safe method to authenticate twikit without triggering captchas.
"""

import json
import os
import sys
from pathlib import Path


def main():
    print("=" * 60)
    print("  NotifyMe - X Session Cookies Setup")
    print("=" * 60)
    print("\nTo bypass X bot challenges and avoid login transaction errors,")
    print("you can extract 2 cookies from your browser session on x.com:\n")
    print("  1. Log into your dedicated X account in Chrome/Firefox/Safari.")
    print("  2. Open Developer Tools (Press F12 or Right-click -> Inspect).")
    print("  3. Go to the 'Application' (or 'Storage') tab -> Cookies -> 'https://x.com'.")
    print("  4. Locate the values for:")
    print("       • auth_token")
    print("       • ct0")
    print("=" * 60 + "\n")

    auth_token = input("Enter 'auth_token' value: ").strip()
    if not auth_token:
        print("Error: auth_token cannot be empty.")
        sys.exit(1)

    ct0 = input("Enter 'ct0' value: ").strip()
    if not ct0:
        print("Error: ct0 cannot be empty.")
        sys.exit(1)

    cookies = {
        "auth_token": auth_token,
        "ct0": ct0,
    }

    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    cookies_path = output_dir / "cookies.json"

    with open(cookies_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)

    print(f"\n[OK] Successfully saved cookies to {cookies_path}!")
    print("You can now run 'python main.py' and twikit will authenticate seamlessly.")


if __name__ == "__main__":
    main()
