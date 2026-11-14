# GitHub Issue Monitor with ASD-STE100 Telegram Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, completely isolated GitHub Issue Monitor inside a dedicated folder (`github_issue_monitor/`) that polls specified open-source repositories (starting with `open-telemetry/opentelemetry-collector-contrib`) every 15 minutes, filters for relevant issues, generates concise ASD-STE100 first-response drafts, and delivers instant, 1-tap copyable Telegram notifications without touching any existing Twitter monitoring code.

**Architecture:** A standalone Python package (`github_issue_monitor/`) with its own entry point, SQLite storage for deduplication, async HTTP fetcher with ETag caching, deterministic relevance filter, ASD-STE100 technical English response generator, and Telegram notification delivery.

**Tech Stack:** Python 3.10+, `aiohttp`, `sqlite3`, `pytest`, `pytest-asyncio`, `pyyaml`.

## Global Constraints
- Do NOT touch or modify any existing Twitter monitoring files (`app.py`, `fetcher.py`, `filters.py`, `follower_tracker.py`, `main.py`, `notifier.py`, `storage.py`, `web.py`).
- All code for this feature must reside strictly within `github_issue_monitor/`.
- No paid AI API keys required: Relevance classification and ASD-STE100 generation are 100% deterministic rule-based.
- Zero duplicate notifications across service restarts via persistent SQLite state.
- Notifications must follow the agreed ultra-compact format with 1-tap copyable `<code>` tags for Telegram mobile.

## Review Focus
1. GitHub API returns Pull Requests mixed with Issues in `/issues` endpoint; must strictly filter them out via presence of `pull_request` key.
2. Bot accounts (Dependabot, Renovate, GitHub Actions) must be excluded from alerts.
3. Rate limits without a token must be preserved by sending `If-None-Match` HTTP ETags to receive `304 Not Modified`.
4. Telegram HTML messages must escape special XML characters (`<`, `>`, `&`) in issue titles and usernames except for intended HTML tags (`<b>`, `<code>`, `<a>`).
5. Running with `--once` flag must allow instant one-off testing and dry-run without waiting 15 minutes.

---

### Task 1: Data Models & ASD-STE100 Generator

**Files:**
- Create: `github_issue_monitor/models.py`
- Create: `github_issue_monitor/ste100.py`
- Test: `github_issue_monitor/tests/test_ste100.py`

**Interfaces:**
- Produces: `IssueData` dataclass, `RelevanceCategory` enum, `generate_ste100_reply(issue: IssueData, category: RelevanceCategory) -> str`

- [ ] **Step 1: Write the failing tests for models and ASD-STE100 generation**
- [ ] **Step 2: Run pytest to verify test failure**
- [ ] **Step 3: Implement `models.py` and `ste100.py` with rule-based archetypes**
- [ ] **Step 4: Run pytest to verify passing tests**
- [ ] **Step 5: Commit changes**

---

### Task 2: Relevance Filter Engine

**Files:**
- Create: `github_issue_monitor/filter.py`
- Test: `github_issue_monitor/tests/test_filter.py`

**Interfaces:**
- Consumes: `IssueData`, `RelevanceCategory` from Task 1
- Produces: `classify_issue(raw_issue_dict: dict) -> tuple[bool, RelevanceCategory | None, str]` (is_relevant, category, reason)

- [ ] **Step 1: Write tests for filtering out PRs, bots, assigned issues, and classifying bugs/enhancements/help-wanted**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement `filter.py` logic**
- [ ] **Step 4: Run pytest to verify passing tests**
- [ ] **Step 5: Commit changes**

---

### Task 3: SQLite Storage for Seen Issues

**Files:**
- Create: `github_issue_monitor/storage.py`
- Test: `github_issue_monitor/tests/test_storage.py`

**Interfaces:**
- Produces: `IssueStorage(db_path: str)` with methods `is_seen(repo: str, issue_number: int) -> bool`, `mark_seen(repo: str, issue_number: int, title: str)`, `save_etag(repo: str, etag: str)`, `get_etag(repo: str) -> str | None`

- [ ] **Step 1: Write tests for SQLite issue persistence and ETag tracking**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement `storage.py` using sqlite3**
- [ ] **Step 4: Run pytest to verify passing tests**
- [ ] **Step 5: Commit changes**

---

### Task 4: GitHub API Fetcher with ETag Caching

**Files:**
- Create: `github_issue_monitor/fetcher.py`
- Test: `github_issue_monitor/tests/test_fetcher.py`

**Interfaces:**
- Consumes: `storage.py` ETag methods, `models.py`
- Produces: `GitHubIssueFetcher(session: aiohttp.ClientSession, token: str | None)` with method `fetch_new_issues(repo: str, etag: str | None) -> tuple[list[dict], str | None]`

- [ ] **Step 1: Write unit tests with mocked aiohttp responses (handling 200 OK, 304 Not Modified, 403 Rate Limit)**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement `fetcher.py`**
- [ ] **Step 4: Run pytest to verify passing tests**
- [ ] **Step 5: Commit changes**

---

### Task 5: Compact Telegram Formatter & Notifier

**Files:**
- Create: `github_issue_monitor/notifier.py`
- Test: `github_issue_monitor/tests/test_notifier.py`

**Interfaces:**
- Consumes: `IssueData`, `ste100.py`
- Produces: `format_telegram_issue_message(issue: IssueData, ste100_reply: str) -> str`, `TelegramIssueNotifier` with `send_issue(issue, reply) -> bool`

- [ ] **Step 1: Write tests verifying Telegram HTML escaping and exact compact message layout with `<code>` tags**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement `notifier.py`**
- [ ] **Step 4: Run pytest to verify passing tests**
- [ ] **Step 5: Commit changes**

---

### Task 6: Configuration, CLI, and Monitor Loop Runner

**Files:**
- Create: `github_issue_monitor/config.py`
- Create: `github_issue_monitor/main.py`
- Create: `github_issue_monitor/config.yaml`
- Test: `github_issue_monitor/tests/test_integration.py`

**Interfaces:**
- Consumes: Tasks 1-5 modules
- Produces: Runnable CLI `python -m github_issue_monitor.main` with `--once` and daemon mode

- [ ] **Step 1: Write end-to-end integration test running a cycle against mocked GitHub & Telegram**
- [ ] **Step 2: Run pytest to verify failure**
- [ ] **Step 3: Implement `config.py` and `main.py`**
- [ ] **Step 4: Run full test suite across all modules**
- [ ] **Step 5: Commit changes**

---

### Task 7: Live Verification on DigitalOcean Droplet

**Files:**
- Target Server: `168.144.181.4` (`/opt/notifyme/github_issue_monitor`)
- Optional systemd unit: `github-issues.service` (or run as standalone process)

- [ ] **Step 1: Deploy `github_issue_monitor` to `/opt/notifyme/github_issue_monitor` on DigitalOcean server**
- [ ] **Step 2: Run live dry-run check with `python -m github_issue_monitor.main --once` for `open-telemetry/opentelemetry-collector-contrib`**
- [ ] **Step 3: Verify Telegram notification receipt and logs**
- [ ] **Step 4: Set up systemd service or background daemon so it runs autonomously every 15 minutes**
