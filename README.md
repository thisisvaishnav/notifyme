---
title: NotifyMe X Monitor
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# NotifyMe • X Account Monitor with Telegram Alerts

> A robust, 24/7 autonomous monitoring service that polls a private X (Twitter) List and delivers new posts to Telegram in near real-time (~60 seconds), complete with deduplication, smart filtering, exponential backoff, and an embedded local HTML/CSS desktop dashboard.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Target Accounts on X      |
                      +--------------+--------------+
                                     |
                       (Private X List Timeline)
                                     v
                      +-----------------------------+
                      |        fetcher.py           |
                      |   (Twikit async client)     |
                      +--------------+--------------+
                                     |
                              [ TweetData ]
                                     v
                      +-----------------------------+
                      |       filters.py            |
                      | (Originals / Block / Allow) |
                      +--------------+--------------+
                                     | (allowed)
                                     v
+-------------------+ +-----------------------------+ +--------------------+
|    storage.py     | |         main.py             | |     notifier.py    |
| (SQLite baseline, |<-- (Orchestrator & scheduler) -->| (Safe HTML format, |
|  deduplication)   | |  with exponential backoff)  | |  cooldown alerts)  |
+-------------------+ +--------------+--------------+ +---------+----------+
                                     |                          |
                                     v                          v
                      +-----------------------------+ +--------------------+
                      |           web.py            | |  Telegram Bot API  |
                      |  (Local Desktop Dashboard)  | |   (User Chat ID)   |
                      |    http://127.0.0.1:8080    | +--------------------+
                      +-----------------------------+
```

---

## 1. Telegram Bot Setup & Finding Chat ID

### Step 1: Create the Telegram Bot
1. Open Telegram and search for `@BotFather`.
2. Send `/start`, then send `/newbot`.
3. Follow the prompts to provide:
   - A friendly name (e.g., `My X Feed Alerts`).
   - A unique username ending in `bot` (e.g., `my_x_feed_monitor_bot`).
4. `@BotFather` will reply with your **Bot Token** (e.g., `7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Copy this.

### Step 2: Retrieve Your Telegram Chat ID
1. Search for `@userinfobot` on Telegram and send `/start`.
2. It will reply with your numerical **Id** (e.g., `123456789`).
3. **Crucial:** Open a direct chat with your newly created bot and click **Start** (or send `/start`). Bots cannot initiate contact with you until you send the first message!

*(Alternative method: Send a message to your bot, then open `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in your browser. Look for `"chat":{"id":123456789}` in the JSON response).*

---

## 2. Creating the Private List on X & Finding its List ID

### Why a List?
Instead of making 20–50 separate requests per minute (one for each followed account), querying a single X List timeline fetches recent posts from all monitored accounts in **one single request per minute**, dramatically lowering rate limits and detection risks.

### Steps:
1. Log into your **dedicated data account** on [x.com](https://x.com).
2. Go to **Lists** in the left sidebar (or navigate to `https://x.com/i/lists`).
3. Click the **New List** icon (top right).
4. Enter a name (e.g., `Alpha Trackers`).
5. **Important:** Toggle **Make private** to ON.
6. Add the accounts you wish to monitor to this List.
7. Open the List in your browser. The URL in the address bar will look like:
   ```
   https://x.com/i/lists/1849123456789012345
   ```
8. The digits at the end (`1849123456789012345`) are your **`X_LIST_ID`**.

---

## 3. Configuring `.env` and `config.yaml`

Copy the template environment file:
```bash
cp .env.example .env
```

Edit `.env` with your actual values:
```env
TELEGRAM_BOT_TOKEN=7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ALERT_CHAT_ID=123456789

# Data account credentials (throwaway only!)
X_USERNAME=your_data_account_handle
X_EMAIL=your_data_email@domain.com
X_PASSWORD=YourAccountPassword
X_TOTP_SECRET=

# The List ID from Step 2
X_LIST_ID=1849123456789012345
X_COOKIES_PATH=data/cookies.json
```

Edit `config.yaml` to customize filtering and polling rules:
```yaml
poll:
  interval_seconds: 60
  jitter_max_seconds: 10

filters:
  include_replies: false
  include_retweets: false
  include_quotes: false
  keyword_allowlist: []
  keyword_blocklist:
    - "giveaway"
    - "airdrop"
  account_overrides: {}

alerts:
  max_consecutive_failures: 5
  inactivity_alert_minutes: 10
  alert_cooldown_minutes: 30

web:
  enabled: true
  host: "127.0.0.1"
  port: 8080

storage:
  db_path: "data/monitor.db"
```

---

## 4. How to Run

### Method A: Local Desktop (Recommended)

1. Create and activate a Python 3.11+ virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the monitor:
   ```bash
   python main.py
   ```
4. Open the native HTML/CSS desktop dashboard in your browser:
   ```
   http://127.0.0.1:8080
   ```
   From here, you can see live telemetry, inspect recent delivered posts, pause/resume monitoring, or trigger an instant poll cycle.

---

### Method B: Docker & Docker Compose

1. Build and run in background:
   ```bash
   docker compose up -d --build
   ```
2. Check container logs:
   ```bash
   docker compose logs -f
   ```
3. The dashboard is forwarded to `http://localhost:8080`.
4. Stop container:
   ```bash
   docker compose down
   ```

---

### Method C: Linux systemd Service (VPS / Raspberry Pi)

1. Clone or copy this repository to `/opt/notifyme`.
2. Create virtual environment and install requirements:
   ```bash
   cd /opt/notifyme
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Edit `notifyme.service` and replace `YOUR_SYSTEM_USER` with your Linux username.
4. Install and enable the unit file:
   ```bash
   sudo cp notifyme.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now notifyme
   ```
5. Check status and logs:
   ```bash
   systemctl status notifyme
   journalctl -u notifyme -f
   ```

---

## 5. Maintenance, Updates, and Handling Fetcher Breakages

Unofficial scrapers work by simulating web requests. When X changes internal endpoints or GraphQL schemas, twikit may require an update:

1. **Update twikit to the latest release:**
   ```bash
   source .venv/bin/activate
   pip install --upgrade twikit
   ```
2. **If cookies become invalid or corrupted:**
   Simply delete `data/cookies.json` and restart the service:
   ```bash
   rm data/cookies.json
   python main.py
   ```
   The service will authenticate with username/password and generate a fresh session automatically.
3. **If X challenges the account with a CAPTCHA:**
   - Log into the data account manually in a regular desktop browser.
   - Solve the CAPTCHA / verify email.
   - Once the account opens normally, restart `notifyme`.

---

## 6. Safety Warning & Terms of Service Notice

> ⚠️ **CRITICAL WARNING:**
> 1. Automated scraping with a logged-in account is against the **X (Twitter) Terms of Service**.
> 2. **NEVER use your primary, valuable, or personal X account.** Always create a separate, throwaway "data account".
> 3. If X detects automated polling, the data account could be flagged, locked, or permanently suspended.
> 4. **IP Reputation:** Datacenter IPs (AWS, DigitalOcean, Hetzner) are flagged far more aggressively by Cloudflare/X defenses. Running on a **residential connection** (such as your home Mac, PC, or a Raspberry Pi) has significantly higher reliability and rarely triggers CAPTCHA challenges.

---

## 7. Swapping to the Official X API v2

The project follows Clean Architecture with a swappable `BaseFetcher` interface in `fetcher.py`. To switch to the official X API:

1. Create a class `OfficialXAPIFetcher(BaseFetcher)` in `fetcher.py`:
   ```python
   class OfficialXAPIFetcher(BaseFetcher):
       def __init__(self, bearer_token: str):
           self.bearer_token = bearer_token
           self.session = None

       async def initialize(self) -> None:
           self.session = aiohttp.ClientSession(
               headers={"Authorization": f"Bearer {self.bearer_token}"}
           )

       async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
           url = f"https://api.twitter.com/2/lists/{list_id}/tweets"
           params = {"max_results": count, "tweet.fields": "created_at,entities"}
           async with self.session.get(url, params=params) as resp:
               data = await resp.json()
               # parse into list[TweetData]
               return parsed_tweets

       async def close(self) -> None:
           if self.session:
               await self.session.close()
   ```
2. In `main.py`, replace `fetcher = TwikitFetcher(...)` with `fetcher = OfficialXAPIFetcher(...)`.
3. **Zero changes** are needed in `storage.py`, `notifier.py`, `filters.py`, or `web.py`!

---

## 8. Known Limitations & Failure Modes

1. **New Account Restrictions on X:** Very newly created accounts (less than 24 hours old) may have lower request limits or require phone verification.
2. **List Delay:** Occasionally, X lists index posts with a 15–45 second delay compared to direct profile streams.
3. **Session Invalidation:** Changing your password or logging out from all sessions in a browser will invalidate `cookies.json`.
4. **Network Outages:** If your local machine goes to sleep or loses internet, polling stops until network returns. (System backoff handles transient drops smoothly).

---

## 9. End-to-End Test Plan

To verify that your installation is working properly end-to-end:

1. **Verify Unit & Integration Tests:**
   ```bash
   source .venv/bin/activate
   pytest -v
   ```
   *Expected: All 23 tests pass.*
2. **Baseline Check:**
   - Add a test account you control (or any active account) to your private X List.
   - Start `python main.py`.
   - In the console, look for:
     `Baseline established silently at tweet ID XXXXXXXXX. Found N existing tweets (notified none).`
   - *Expected: You should NOT receive Telegram notifications for existing tweets.*
3. **Live Alert Check:**
   - Post a new test tweet from the monitored test account (e.g., `Hello Telegram world 123`).
   - Watch the monitor console or the web dashboard at `http://localhost:8080`.
   - Within 60 seconds, the monitor will log:
     `Delivering new post XXXXXXXXX by @yourhandle to Telegram...`
   - Check Telegram: You should receive the message with handle, tweet text, and link within ~60s.
4. **Duplicate Prevention Check:**
   - Stop `main.py` (`Ctrl+C`) and restart it.
   - Wait for the next poll cycle.
   - *Expected: No repeat notification arrives in Telegram.*
