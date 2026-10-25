#!/usr/bin/env python3
"""Interactive utility to generate data/cookies.json or configure .env with X session cookies.

Because X permanently retired programmatic username/password logins for plain
HTTP clients (requiring in-browser WebAuthn/$castle_token challenges),
providing session cookies directly (auth_token and ct0) is the official,
reliable method to authenticate twikit / twifork scrapers.
"""

import json
import os
import sys
from pathlib import Path


def main():
    print("=" * 65)
    print("  NotifyMe - X Session Cookies Setup")
    print("=" * 65)
    print("\nHow to get your session cookies in 30 seconds:")
    print("  1. Log into your dedicated X account in any browser (Chrome/Firefox/Safari).")
    print("  2. Open Developer Tools (Press F12, or Right-Click -> Inspect).")
    print("  3. Go to the 'Application' (or 'Storage') tab -> Cookies -> 'https://x.com'.")
    print("  4. Copy the values for:")
    print("       • auth_token  (e.g., 40-character hex string)")
    print("       • ct0         (e.g., 160-character csrf token)")
    print("=" * 65 + "\n")

    auth_token = input("Enter 'auth_token': ").strip().strip('"').strip("'")
    if not auth_token:
        print("Error: auth_token cannot be empty.")
        sys.exit(1)

    ct0 = input("Enter 'ct0': ").strip().strip('"').strip("'")
    if not ct0:
        print("Error: ct0 cannot be empty.")
        sys.exit(1)

    # 1. Save to data/cookies.json
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    cookies_path = output_dir / "cookies.json"

    cookies_dict = {
        "auth_token": auth_token,
        "ct0": ct0,
    }

    with open(cookies_path, "w", encoding="utf-8") as f:
        json.dump(cookies_dict, f, indent=2)

    print(f"\n[OK] Saved cookies to: {cookies_path}")

    # 2. Update .env if it exists
    env_path = Path(".env")
    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            new_lines = []
            has_auth = False
            has_ct0 = False

            for line in lines:
                if line.startswith("X_AUTH_TOKEN="):
                    new_lines.append(f"X_AUTH_TOKEN={auth_token}")
                    has_auth = True
                elif line.startswith("X_CT0="):
                    new_lines.append(f"X_CT0={ct0}")
                    has_ct0 = True
                else:
                    new_lines.append(line)

            if not has_auth:
                new_lines.append(f"X_AUTH_TOKEN={auth_token}")
            if not has_ct0:
                new_lines.append(f"X_CT0={ct0}")

            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            print(f"[OK] Automatically updated .env with X_AUTH_TOKEN and X_CT0!")
        except Exception as e:
            print(f"[NOTE] Could not update .env directly ({e}), but data/cookies.json is ready.")

    print("\n Setup complete! You can now run: python main.py")


if __name__ == "__main__":
    main()
