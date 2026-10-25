/**
 * NotifyMe • Modern Dashboard & Follower Studio Controller
 */

class DashboardApp {
  constructor() {
    this.pollIntervalMs = 4000;
    this.timerId = null;
    this.isPaused = false;

    // Follower Studio State
    this.allNfbAccounts = [];
    this.keptAccounts = new Set(JSON.parse(localStorage.getItem("notifyme_kept_accounts") || "[]"));
    this.searchQuery = "";
    this.activeFilter = "all"; // 'all' | 'pending' | 'kept'
    this.activeSort = "alpha-asc";
    this.currentPage = 1;
    this.pageSize = 50;

    this.initElements();
    this.bindEvents();
    this.startPolling();
    this.fetchFollowerData();
  }

  initElements() {
    // Navigation Tabs
    this.navTabs = document.querySelectorAll(".nav-tab");
    this.tabPanes = document.querySelectorAll(".tab-pane");

    // Header elements
    this.statusPill = document.getElementById("status-pill");
    this.statusText = document.getElementById("status-text");
    this.btnTogglePause = document.getElementById("btn-toggle-pause");
    this.btnPauseText = document.getElementById("btn-pause-text");
    this.btnPollNow = document.getElementById("btn-poll-now");

    // KPI elements
    this.kpiFollowers = document.getElementById("kpi-followers");
    this.kpiNetDelta = document.getElementById("kpi-net-delta");
    this.kpiMutualsText = document.getElementById("kpi-mutuals-text");
    this.kpiMutualsPct = document.getElementById("kpi-mutuals-pct");
    this.kpiFollowingText = document.getElementById("kpi-following-text");
    this.kpiReciprocityFill = document.getElementById("kpi-reciprocity-fill");
    this.kpiUnreciprocated = document.getElementById("kpi-unreciprocated");
    this.kpiTweetsNotified = document.getElementById("kpi-tweets-notified");
    this.kpiScheduleTime = document.getElementById("kpi-schedule-time");
    this.kpiPrepTime = document.getElementById("kpi-prep-time");
    this.btnQuickCheckFollowers = document.getElementById("btn-quick-check-followers");
    this.quickCheckText = document.getElementById("quick-check-text");
    this.btnGotoStudio = document.getElementById("btn-goto-studio");
    this.btnViewAllNfb = document.getElementById("btn-view-all-nfb");

    // Overview widgets
    this.tweetCountBadge = document.getElementById("tweet-count-badge");
    this.tweetsFeed = document.getElementById("tweets-feed");
    this.previewNfbCount = document.getElementById("preview-nfb-count");
    this.miniNfbList = document.getElementById("mini-nfb-list");
    this.snapshotHistoryList = document.getElementById("snapshot-history-list");
    this.tabNfbBadge = document.getElementById("tab-nfb-badge");

    // Follower Studio Elements
    this.btnStudioCheckNow = document.getElementById("btn-studio-check-now");
    this.btnStudioCheckText = document.getElementById("btn-studio-check-text");
    this.studioSearchInput = document.getElementById("studio-search-input");
    this.studioSearchClear = document.getElementById("studio-search-clear");
    this.filterChips = document.querySelectorAll(".filter-chips .chip");
    this.filterCountAll = document.getElementById("filter-count-all");
    this.filterCountPending = document.getElementById("filter-count-pending");
    this.filterCountKept = document.getElementById("filter-count-kept");
    this.studioSortSelect = document.getElementById("studio-sort-select");
    this.studioPerPageSelect = document.getElementById("studio-per-page-select");
    this.studioTableBody = document.getElementById("studio-table-body");
    this.paginationInfo = document.getElementById("pagination-info");
    this.btnPagePrev = document.getElementById("btn-page-prev");
    this.btnPageNext = document.getElementById("btn-page-next");
    this.pageCurrentIndicator = document.getElementById("page-current-indicator");

    // Diagnostics Elements
    this.diagUptime = document.getElementById("diag-uptime");
    this.diagListId = document.getElementById("diag-list-id");
    this.diagConsecFails = document.getElementById("diag-consec-fails");
    this.ruleDiagRt = document.getElementById("rule-diag-rt");
    this.ruleDiagReply = document.getElementById("rule-diag-reply");
    this.ruleDiagQuotes = document.getElementById("rule-diag-quotes");
    this.diagPollsTableBody = document.getElementById("diag-polls-table-body");

    // Toast
    this.toastContainer = document.getElementById("toast-container");
  }

  bindEvents() {
    // Tab switching
    this.navTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const targetTabId = tab.dataset.tab;
        this.switchTab(targetTabId);
      });
    });

    if (this.btnGotoStudio) {
      this.btnGotoStudio.addEventListener("click", () => this.switchTab("tab-followers"));
    }
    if (this.btnViewAllNfb) {
      this.btnViewAllNfb.addEventListener("click", () => this.switchTab("tab-followers"));
    }

    // Engine Controls
    this.btnTogglePause.addEventListener("click", () => this.togglePause());
    this.btnPollNow.addEventListener("click", () => this.triggerPollNow());

    // Audit Trigger Buttons
    if (this.btnQuickCheckFollowers) {
      this.btnQuickCheckFollowers.addEventListener("click", () => this.triggerFollowerAudit());
    }
    if (this.btnStudioCheckNow) {
      this.btnStudioCheckNow.addEventListener("click", () => this.triggerFollowerAudit());
    }

    // Follower Studio Controls
    if (this.studioSearchInput) {
      this.studioSearchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.trim().toLowerCase();
        this.studioSearchClear.classList.toggle("visible", this.searchQuery.length > 0);
        this.currentPage = 1;
        this.renderStudioTable();
      });
    }

    if (this.studioSearchClear) {
      this.studioSearchClear.addEventListener("click", () => {
        this.studioSearchInput.value = "";
        this.searchQuery = "";
        this.studioSearchClear.classList.remove("visible");
        this.currentPage = 1;
        this.renderStudioTable();
        this.studioSearchInput.focus();
      });
    }

    this.filterChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        this.filterChips.forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        this.activeFilter = chip.dataset.filter;
        this.currentPage = 1;
        this.renderStudioTable();
      });
    });

    if (this.studioSortSelect) {
      this.studioSortSelect.addEventListener("change", (e) => {
        this.activeSort = e.target.value;
        this.renderStudioTable();
      });
    }

    if (this.studioPerPageSelect) {
      this.studioPerPageSelect.addEventListener("change", (e) => {
        this.pageSize = parseInt(e.target.value, 10);
        this.currentPage = 1;
        this.renderStudioTable();
      });
    }

    if (this.btnPagePrev) {
      this.btnPagePrev.addEventListener("click", () => {
        if (this.currentPage > 1) {
          this.currentPage--;
          this.renderStudioTable();
        }
      });
    }

    if (this.btnPageNext) {
      this.btnPageNext.addEventListener("click", () => {
        this.currentPage++;
        this.renderStudioTable();
      });
    }
  }

  switchTab(tabId) {
    this.navTabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === tabId);
    });
    this.tabPanes.forEach((pane) => {
      pane.classList.toggle("active", pane.id === tabId);
    });
  }

  startPolling() {
    this.fetchStatus();
    this.timerId = setInterval(() => this.fetchStatus(), this.pollIntervalMs);
  }

  async fetchStatus() {
    try {
      const resp = await fetch("/api/status");
      if (!resp.ok) return;
      const data = await resp.json();
      this.updateEngineUI(data);
    } catch (err) {
      console.warn("Telemetry poll failed:", err);
    }
  }

  async fetchFollowerData() {
    try {
      const [statusResp, nfbResp] = await Promise.all([
        fetch("/api/followers/status"),
        fetch("/api/followers/not_following_back"),
      ]);

      if (statusResp.ok) {
        const statusData = await statusResp.json();
        this.updateFollowerMetrics(statusData);
      }

      if (nfbResp.ok) {
        const nfbData = await nfbResp.json();
        this.allNfbAccounts = nfbData.not_following_back || [];
        this.updateFollowerCounts();
        this.renderMiniNfb();
        this.renderStudioTable();
      }
    } catch (err) {
      console.warn("Follower data load failed:", err);
    }
  }

  updateEngineUI(data) {
    this.isPaused = data.is_paused;
    this.btnPauseText.textContent = this.isPaused ? "Resume" : "Pause";
    this.btnTogglePause.querySelector(".btn-icon").textContent = this.isPaused ? "▶" : "⏸";

    this.statusPill.className = `status-pill status-${data.status}`;
    this.statusText.textContent = data.status.toUpperCase();

    // Tweets count
    const notifiedCount = data.stats?.total_notified ?? 0;
    this.kpiTweetsNotified.textContent = notifiedCount;
    this.tweetCountBadge.textContent = `${notifiedCount} Posts`;

    // Uptime
    if (this.diagUptime) {
      this.diagUptime.textContent = `Uptime: ${this.formatUptime(data.uptime_seconds)}`;
    }
    if (this.diagListId) {
      this.diagListId.textContent = data.list_id;
    }
    if (this.diagConsecFails) {
      this.diagConsecFails.textContent = data.consecutive_failures;
    }

    // Rules
    if (data.filter_settings) {
      this.setRuleStatus(this.ruleDiagRt, data.filter_settings.include_retweets);
      this.setRuleStatus(this.ruleDiagReply, data.filter_settings.include_replies);
      this.setRuleStatus(this.ruleDiagQuotes, data.filter_settings.include_quotes);
    }

    // Render Tweets
    this.renderTweets(data.recent_tweets || []);

    // Render Telemetry cycles
    this.renderPollHistory(data.recent_polls || []);
  }

  setRuleStatus(elem, isIncluded) {
    if (!elem) return;
    elem.textContent = isIncluded ? "Included" : "Filtered Out";
    elem.className = `rule-badge ${isIncluded ? "enabled" : "disabled"}`;
  }

  updateFollowerMetrics(data) {
    const snap = data.latest_snapshot;
    if (snap) {
      const followers = snap.total_followers ?? 0;
      const following = snap.total_following ?? 0;
      const mutuals = data.mutual_count ?? 87;
      const nfbCount = data.not_following_back_count ?? (following - mutuals);

      this.kpiFollowers.textContent = followers;
      this.kpiFollowingText.textContent = following;
      this.kpiMutualsText.textContent = mutuals;

      const mutualPct = following > 0 ? ((mutuals / following) * 100).toFixed(1) : 0;
      this.kpiMutualsPct.textContent = `${mutualPct}%`;
      this.kpiReciprocityFill.style.width = `${Math.min(100, Math.max(5, mutualPct))}%`;

      this.kpiUnreciprocated.textContent = nfbCount;
      this.previewNfbCount.textContent = nfbCount;
      this.tabNfbBadge.textContent = nfbCount;
    }

    if (data.schedule_time) {
      this.kpiScheduleTime.textContent = `${data.schedule_time} AM`;
    }
    if (data.prep_lead_minutes) {
      this.kpiPrepTime.textContent = `Pre-collection at 08:20 AM (${data.prep_lead_minutes}m lead, 10–20s safe delays)`;
    }

    // Auditing badge state
    if (data.is_auditing) {
      this.quickCheckText.textContent = "Auditing...";
      this.btnQuickCheckFollowers.disabled = true;
      if (this.btnStudioCheckText) {
        this.btnStudioCheckText.textContent = "Safe Audit Running...";
        this.btnStudioCheckNow.disabled = true;
      }
    } else {
      this.quickCheckText.textContent = "Audit Now";
      this.btnQuickCheckFollowers.disabled = false;
      if (this.btnStudioCheckText) {
        this.btnStudioCheckText.textContent = "Run Safe Audit Now";
        this.btnStudioCheckNow.disabled = false;
      }
    }

    // Render snapshot history
    if (data.recent_snapshots && data.recent_snapshots.length > 0) {
      this.renderSnapshotHistory(data.recent_snapshots);
    }
  }

  updateFollowerCounts() {
    const total = this.allNfbAccounts.length;
    const keptCount = this.allNfbAccounts.filter((acc) => this.keptAccounts.has(acc.screen_name)).length;
    const pendingCount = total - keptCount;

    if (this.filterCountAll) this.filterCountAll.textContent = total;
    if (this.filterCountPending) this.filterCountPending.textContent = pendingCount;
    if (this.filterCountKept) this.filterCountKept.textContent = keptCount;
  }

  renderMiniNfb() {
    if (!this.miniNfbList) return;
    if (this.allNfbAccounts.length === 0) {
      this.miniNfbList.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 15px; font-size: 12px;">No unreciprocated accounts.</div>`;
      return;
    }

    const previewItems = this.allNfbAccounts.slice(0, 5);
    this.miniNfbList.innerHTML = previewItems
      .map((acc) => {
        const initial = (acc.name || acc.screen_name).charAt(0).toUpperCase();
        return `
          <div class="mini-nfb-item">
            <div class="mini-user-info">
              <div class="mini-avatar">${this.escape(initial)}</div>
              <div class="mini-names">
                <a href="https://x.com/${this.escape(acc.screen_name)}" target="_blank" class="mini-handle">@${this.escape(acc.screen_name)}</a>
                <span class="mini-display-name">${this.escape(acc.name || "")}</span>
              </div>
            </div>
            <a href="https://x.com/${this.escape(acc.screen_name)}" target="_blank" class="mini-unfollow-btn">Unfollow ↗</a>
          </div>
        `;
      })
      .join("");
  }

  renderStudioTable() {
    if (!this.studioTableBody) return;

    // Filter accounts
    let filtered = this.allNfbAccounts.filter((acc) => {
      const isKept = this.keptAccounts.has(acc.screen_name);
      if (this.activeFilter === "pending" && isKept) return false;
      if (this.activeFilter === "kept" && !isKept) return false;

      if (this.searchQuery) {
        const handle = (acc.screen_name || "").toLowerCase();
        const name = (acc.name || "").toLowerCase();
        return handle.includes(this.searchQuery) || name.includes(this.searchQuery);
      }
      return true;
    });

    // Sort accounts
    filtered.sort((a, b) => {
      const nameA = (a.screen_name || "").toLowerCase();
      const nameB = (b.screen_name || "").toLowerCase();
      return this.activeSort === "alpha-asc" ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
    });

    const totalCount = filtered.length;
    const totalPages = Math.ceil(totalCount / this.pageSize) || 1;
    if (this.currentPage > totalPages) this.currentPage = totalPages;

    const startIdx = (this.currentPage - 1) * this.pageSize;
    const endIdx = Math.min(startIdx + this.pageSize, totalCount);
    const pageItems = filtered.slice(startIdx, endIdx);

    // Update pagination controls
    if (this.paginationInfo) {
      if (totalCount === 0) {
        this.paginationInfo.innerHTML = "No matching accounts found";
      } else {
        this.paginationInfo.innerHTML = `Showing <b>${startIdx + 1}–${endIdx}</b> of <b>${totalCount}</b> accounts`;
      }
    }
    if (this.pageCurrentIndicator) {
      this.pageCurrentIndicator.textContent = `Page ${this.currentPage} of ${totalPages}`;
    }
    if (this.btnPagePrev) this.btnPagePrev.disabled = this.currentPage <= 1;
    if (this.btnPageNext) this.btnPageNext.disabled = this.currentPage >= totalPages;

    if (pageItems.length === 0) {
      this.studioTableBody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 40px; color: var(--text-dim);">
            No unreciprocated accounts match your filter.
          </td>
        </tr>
      `;
      return;
    }

    this.studioTableBody.innerHTML = pageItems
      .map((acc, index) => {
        const itemNumber = startIdx + index + 1;
        const initial = (acc.name || acc.screen_name).charAt(0).toUpperCase();
        const isKept = this.keptAccounts.has(acc.screen_name);

        return `
          <tr>
            <td style="color: var(--text-dim); font-size: 11px;" class="mono">${itemNumber}</td>
            <td>
              <div class="user-cell">
                <div class="user-avatar">${this.escape(initial)}</div>
                <div class="user-details">
                  <a href="https://x.com/${this.escape(acc.screen_name)}" target="_blank" class="user-handle-link">@${this.escape(acc.screen_name)}</a>
                  <span class="user-name-text">${this.escape(acc.name || "")}</span>
                </div>
              </div>
            </td>
            <td>
              <span class="badge badge-amber">Doesn't Follow Back</span>
            </td>
            <td>
              ${isKept ? '<span class="badge badge-emerald">Whitelisted</span>' : '<span class="badge badge-subtle">To Review</span>'}
            </td>
            <td>
              <div class="action-cell">
                <button class="btn-icon-action ${isKept ? "active" : ""}" 
                        onclick="dashboardApp.toggleWhitelist('${this.escape(acc.screen_name)}')"
                        title="${isKept ? "Remove from whitelist" : "Keep / Whitelist account"}">
                  ★
                </button>
                <button class="btn-icon-action" 
                        onclick="dashboardApp.copyHandle('${this.escape(acc.screen_name)}')"
                        title="Copy @${this.escape(acc.screen_name)}">
                  📋
                </button>
                <a href="https://x.com/${this.escape(acc.screen_name)}" 
                   target="_blank" 
                   class="btn-unfollow-x">
                  Unfollow on X ↗
                </a>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  toggleWhitelist(screenName) {
    if (this.keptAccounts.has(screenName)) {
      this.keptAccounts.delete(screenName);
      this.showToast(`Removed @${screenName} from whitelist`, "info");
    } else {
      this.keptAccounts.add(screenName);
      this.showToast(`Whitelisted @${screenName} (Keep Following)`, "success");
    }
    localStorage.setItem("notifyme_kept_accounts", JSON.stringify(Array.from(this.keptAccounts)));
    this.updateFollowerCounts();
    this.renderStudioTable();
  }

  copyHandle(screenName) {
    navigator.clipboard.writeText(`@${screenName}`);
    this.showToast(`Copied @${screenName} to clipboard`, "info");
  }

  renderSnapshotHistory(snapshots) {
    if (!this.snapshotHistoryList) return;
    this.snapshotHistoryList.innerHTML = snapshots
      .map((s, idx) => `
        <div class="snapshot-item">
          <div class="snap-meta">
            <span class="snap-time">${this.escape(s.recorded_at)}</span>
            <span class="snap-counts mono">${s.total_followers} Followers • ${s.total_following} Following</span>
          </div>
          <span class="badge ${idx === 0 ? "badge-emerald" : "badge-subtle"}">
            ${idx === 0 ? "Active" : "Archived"}
          </span>
        </div>
      `)
      .join("");
  }

  renderTweets(tweets) {
    if (!this.tweetsFeed) return;
    if (tweets.length === 0) {
      this.tweetsFeed.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📬</div>
          <h3>No Tweets Dispatched Yet</h3>
          <p>When the 18 alpha accounts post original tweets, they will appear here in real time.</p>
        </div>
      `;
      return;
    }

    this.tweetsFeed.innerHTML = tweets
      .map((t) => {
        const initial = (t.author_handle || "X").charAt(0).toUpperCase();
        return `
          <div class="tweet-card">
            <div class="tweet-top">
              <div class="tweet-author-badge">
                <div class="author-avatar">${this.escape(initial)}</div>
                <a href="https://x.com/${this.escape(t.author_handle)}" target="_blank" class="author-handle">@${this.escape(t.author_handle)}</a>
              </div>
              <span class="tweet-time mono">${this.escape(t.notified_at || t.created_at || "")}</span>
            </div>
            <div class="tweet-body">${this.escape(t.text)}</div>
            <div class="tweet-footer">
              <span class="badge badge-emerald">Dispatched to Telegram</span>
              <a href="https://x.com/${this.escape(t.author_handle)}/status/${this.escape(t.tweet_id)}" target="_blank" class="tweet-link">
                View on X ↗
              </a>
            </div>
          </div>
        `;
      })
      .join("");
  }

  renderPollHistory(polls) {
    if (!this.diagPollsTableBody) return;
    if (polls.length === 0) {
      this.diagPollsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 25px; color: var(--text-dim);">No poll telemetry recorded yet.</td></tr>`;
      return;
    }

    this.diagPollsTableBody.innerHTML = polls
      .map((p) => {
        const statusClass = p.status === "success" ? "badge-emerald" : "badge-amber";
        return `
          <tr>
            <td class="mono" style="font-size: 12px;">${this.escape(p.polled_at)}</td>
            <td><span class="badge ${statusClass}">${this.escape(p.status.toUpperCase())}</span></td>
            <td class="mono">${p.tweets_found}</td>
            <td class="mono">${p.tweets_notified}</td>
            <td style="font-size: 11px; color: var(--text-dim);">${this.escape(p.error_message || "OK - No errors")}</td>
          </tr>
        `;
      })
      .join("");
  }

  async togglePause() {
    const endpoint = this.isPaused ? "/api/resume" : "/api/pause";
    try {
      const resp = await fetch(endpoint, { method: "POST" });
      const data = await resp.json();
      if (data.success) {
        this.showToast(data.is_paused ? "Monitoring Paused" : "Monitoring Resumed", "info");
        this.fetchStatus();
      }
    } catch (err) {
      this.showToast("Failed to toggle pause", "error");
    }
  }

  async triggerPollNow() {
    this.btnPollNow.disabled = true;
    try {
      const resp = await fetch("/api/poll_now", { method: "POST" });
      const data = await resp.json();
      if (data.success) {
        this.showToast("Immediate list poll initiated", "success");
        setTimeout(() => this.fetchStatus(), 1200);
      }
    } catch (err) {
      this.showToast("Failed to trigger poll", "error");
    } finally {
      setTimeout(() => {
        this.btnPollNow.disabled = false;
      }, 3000);
    }
  }

  async triggerFollowerAudit() {
    if (this.btnQuickCheckFollowers) this.btnQuickCheckFollowers.disabled = true;
    if (this.btnStudioCheckNow) this.btnStudioCheckNow.disabled = true;

    try {
      const resp = await fetch("/api/followers/check_now", { method: "POST" });
      const data = await resp.json();
      if (data.success) {
        this.showToast("Safe follower audit started in background (10–20s delay pacing)", "info");
        setTimeout(() => this.fetchFollowerData(), 2000);
      } else {
        this.showToast(data.message || "Audit in progress", "info");
      }
    } catch (err) {
      this.showToast("Failed to trigger audit", "error");
    }
  }

  formatUptime(seconds) {
    if (!seconds || seconds < 0) return "00:00:00";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  escape(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  showToast(message, type = "info") {
    if (!this.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    this.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
}

// Global instance
let dashboardApp;
document.addEventListener("DOMContentLoaded", () => {
  dashboardApp = new DashboardApp();
});
