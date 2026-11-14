# Remove Hugging Face Configuration and ASD-STE100 Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all Hugging Face Spaces configuration artifacts from NotifyMe, rewrite README.md strictly in ASD-STE100 Simplified Technical English, verify tests pass, raise a pull request, and push to main.

**Architecture:** Revert Dockerfile, config.py, and static/index.html to their pre-Hugging Face state, remove app.py, compose an ASD-STE100 compliant README, verify with pytest, then publish via git branch, GitHub PR, and main push.

**Tech Stack:** Python 3.11, Docker, aiohttp, SQLite, git, GitHub CLI (`gh`).

**Spec:** User prompt requesting removal of Hugging Face configuration, push to main repo, ASD-STE100 README, and GitHub PR creation.

## Global Constraints

- Remove all files and lines introduced for Hugging Face Spaces (`app.py`, HF port 7860 mappings, HF user UID 1000 in Dockerfile, iframe-resizer in `static/index.html`, HF YAML frontmatter in README).
- All README text must strictly adhere to ASD-STE100: max 20 words for procedural steps, max 25 words for descriptions, approved vocabulary, active voice.
- All 43 test suite cases must pass before committing or pushing.
- Create a pull request targeting `main` and ensure `main` is updated on `origin`.

---

### Task 1: Remove Hugging Face Configuration

**Files:**
- Delete: `notifyme/app.py`
- Modify: `notifyme/Dockerfile`
- Modify: `notifyme/config.py`
- Modify: `notifyme/static/index.html`

- [ ] **Step 1: Delete `app.py`**
- [ ] **Step 2: Revert `Dockerfile` to use standard user and port 8080**
- [ ] **Step 3: Update `config.py` to use `WEB_HOST` and `WEB_PORT`**
- [ ] **Step 4: Remove `iframeResizer` script tag from `static/index.html`**

---

### Task 2: Write ASD-STE100 README

**Files:**
- Modify: `notifyme/README.md`

- [ ] **Step 1: Draft ASD-STE100 compliant documentation sections**
- [ ] **Step 2: Validate sentence lengths (<=20 words for instructions, <=25 words for descriptions)**
- [ ] **Step 3: Save to `notifyme/README.md`**

---

### Task 3: Test Verification and Security Review

**Files:**
- Test: `tests/`

- [ ] **Step 1: Run pytest test suite using uv**
- [ ] **Step 2: Verify zero test regressions**
- [ ] **Step 3: Parallel security review audit**

---

### Task 4: Git Branch, PR Creation, and Push to Main

- [ ] **Step 1: Create feature branch `cleanup/remove-huggingface-config`**
- [ ] **Step 2: Commit all modified and deleted files**
- [ ] **Step 3: Push branch to GitHub origin**
- [ ] **Step 4: Create PR using `gh pr create`**
- [ ] **Step 5: Merge branch into `main` and push `main` to origin**
