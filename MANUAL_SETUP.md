# Post-Build Manual Setup Checklist

Below is the complete, exact checklist of the 4 things you must manually configure before running the application.

---

### Checklist Summary

| # | Item | What you need to do | Output Needed |
|---|---|---|---|
| **1** | **Telegram Bot** | Create bot with `@BotFather` & get your Chat ID | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| **2** | **X Data Account** | Create / prepare a dedicated throwaway X account | `X_USERNAME`, `X_EMAIL`, `X_PASSWORD` |
| **3** | **Private X List** | Create a private list on X with tracked accounts | `X_LIST_ID` (from list URL) |
| **4** | **Configuration Files** | Populate `.env` and review `config.yaml` | `.env` file created |

---

### Step 1: Telegram Bot & Chat ID Setup

1. **Create the Telegram Bot:**
   - Open Telegram and message `@BotFather`.
   - Send: `/newbot`
   - Enter a display name: `NotifyMe X Monitor`
   - Enter a bot username: (must end in `bot`, e.g. `my_custom_x_alert_bot`).
   - Copy the generated HTTP API Token:
     ```
     TELEGRAM_BOT_TOKEN=7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
     ```

2. **Obtain your personal Telegram Chat ID:**
   - Message `@userinfobot` on Telegram and send `/start`.
   - Copy the numerical **Id** shown (e.g. `123456789`).
   - **Crucial Step:** Open a direct message with your **new bot** and press **START** (or send `/start`). If you do not start the bot first, Telegram will block the bot from sending messages to you with a `403 Forbidden` error.

---

### Step 2: Dedicated X (Twitter) Data Account

1. Do **NOT** use your personal or main X account. Automated polling violates X terms of service and throwaways can be challenged or suspended.
2. Sign up or use a separate throwaway account.
3. Note down:
   - Account username (e.g. `data_tracker_99`)
   - Associated email (used if X asks for verification)
   - Password
   - If 2FA is active, have the TOTP secret key handy (optional).

---

### Step 3: Create Private X List & Find its ID

1. On [x.com](https://x.com), go to **Lists** (`https://x.com/i/lists`).
2. Click **New List** (the list icon with a plus).
3. Set a Name (e.g. `Tracked Accounts`).
4. **Important**: Check the checkbox **Make private** so external users don't see which accounts you are tracking.
5. Click **Save / Done**.
6. Click **Manage Members** and add all the X accounts you want to monitor.
7. Look at your browser URL bar. It will look like:
   ```
   https://x.com/i/lists/1849123456789012345
   ```
8. The long number at the end is your `X_LIST_ID`:
   ```
   X_LIST_ID=1849123456789012345
   ```

---

### Step 4: Populate `.env`

In your project directory (`/Users/bombermac/notifyme`), copy the example file:
```bash
cp .env.example .env
```
Open `.env` in any text editor and fill in your values:
```env
TELEGRAM_BOT_TOKEN=7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ALERT_CHAT_ID=123456789

X_USERNAME=your_data_account_handle
X_EMAIL=your_data_email@domain.com
X_PASSWORD=YourAccountPassword
X_TOTP_SECRET=

X_LIST_ID=1849123456789012345
X_COOKIES_PATH=data/cookies.json
```

---

### Step 5: Launch & Open Desktop Dashboard

Once `.env` is saved, launch the application:
```bash
source .venv/bin/activate
python main.py
```
Open your browser and navigate to:
```
http://127.0.0.1:8080
```
You will see the live desktop dashboard showing status, uptime, recent deliveries, and controls.
