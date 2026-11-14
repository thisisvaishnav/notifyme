# NotifyMe

NotifyMe is an autonomous monitoring service for X. The software reads posts from a private X list. It delivers new posts to Telegram in real time. The software includes deduplication, keyword filters, and a local web dashboard.

---

## Features

* **Autonomous Polling:** The service polls the timeline at regular intervals.
* **Rate Limit Protection:** The service uses exponential backoff to prevent rate limit errors.
* **Follower Tracker:** The software tracks daily follower and unfollower metrics.
* **Local Web Dashboard:** A web user interface operates at `http://127.0.0.1:8080`.

---

## Prerequisites

* Python 3.11 or a later version.
* A Telegram bot token and your numerical chat ID.
* A secondary X account.
* A private X list containing the accounts you want to monitor.

---

## Configuration

### 1. Environment Variables

Copy the template file to create your local environment file:

```bash
cp .env.example .env
```

Set the required values in the `.env` file:

* `TELEGRAM_BOT_TOKEN`: The API token from BotFather.
* `TELEGRAM_CHAT_ID`: Your numerical Telegram chat ID.
* `X_USERNAME`: The username of your secondary X account.
* `X_PASSWORD`: The password of your secondary X account.
* `X_LIST_ID`: The numerical identifier of your private X list.

### 2. Application Settings

Adjust monitoring rules and polling intervals in the `config.yaml` file:

* Set `poll.interval_seconds` to change the polling frequency.
* Add keywords to `filters.keyword_blocklist` to ignore specific posts.
* Toggle `filters.include_replies` or `filters.include_retweets` as required.

---

## How to Run

### Method 1: Local Python Environment

1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```

2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the application:
   ```bash
   python main.py
   ```

5. Open your web browser and navigate to:
   ```
   http://127.0.0.1:8080
   ```

### Method 2: Docker

1. Build and start the container:
   ```bash
   docker compose up -d --build
   ```

2. View the container log output:
   ```bash
   docker compose logs -f
   ```

3. Stop the container:
   ```bash
   docker compose down
   ```

### Method 3: Linux System Service (systemd)

1. Copy the repository files to `/opt/notifyme`.
2. Edit `notifyme.service` and replace `YOUR_SYSTEM_USER` with your Linux username.
3. Copy the service unit file:
   ```bash
   sudo cp notifyme.service /etc/systemd/system/
   ```
4. Reload the systemd manager configuration:
   ```bash
   sudo systemctl daemon-reload
   ```
5. Enable and start the service:
   ```bash
   sudo systemctl enable --now notifyme
   ```

---

## Warnings

* Automated polling can violate the terms of service of X.
* Always use a dedicated secondary account for data collection.
* Do not use your primary personal account.
* Cloud data centers can receive network blocks from X.
* Run this service on a residential connection for highest reliability.
