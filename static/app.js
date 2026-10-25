// NotifyMe Desktop Dashboard Client Script

let currentStatus = {
  is_paused: false,
  status: "running"
};

function formatSeconds(sec) {
  const h = Math.floor(sec / 3600).toString().padStart(2, '0');
  const m = Math.floor((sec % 3600) / 60).toString().padStart(2, '0');
  const s = Math.floor(sec % 60).toString().padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function showToast(message, isError = false) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) toast.style.borderColor = "var(--accent-rose)";
  toast.innerHTML = `<span>${isError ? '⚠️' : 'ℹ️'}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.error("Failed to fetch status:", err);
  }
}

function updateUI(data) {
  currentStatus.is_paused = data.is_paused;
  currentStatus.status = data.status;

  // 1. Status Pill & Uptime
  const statusPill = document.getElementById("status-pill");
  const statusText = document.getElementById("status-text");
  const pauseBtn = document.getElementById("btn-toggle-pause");
  const pauseBtnText = document.getElementById("btn-pause-text");

  statusPill.className = "status-pill";
  if (data.is_paused) {
    statusPill.classList.add("status-paused");
    statusText.textContent = "PAUSED";
    pauseBtnText.textContent = "Resume";
  } else if (data.status === "error" || data.consecutive_failures > 0) {
    statusPill.classList.add("status-error");
    statusText.textContent = `ERROR (${data.consecutive_failures})`;
    pauseBtnText.textContent = "Pause";
  } else {
    statusPill.classList.add("status-running");
    statusText.textContent = "ONLINE • POLLING";
    pauseBtnText.textContent = "Pause";
  }

  document.getElementById("uptime-text").textContent = formatSeconds(data.uptime_seconds);

  // 2. Metrics
  const stats = data.stats || {};
  document.getElementById("metric-notified").textContent = stats.total_notified_tweets || 0;
  document.getElementById("metric-polls").textContent = stats.total_polls || 0;
  document.getElementById("metric-polls-footer").textContent = `${stats.total_errors || 0} errors recorded`;

  const lastPoll = stats.last_poll;
  const lastPollEl = document.getElementById("metric-last-poll");
  if (lastPoll) {
    lastPollEl.textContent = lastPoll.status === "success" ? "Success" : "Failed";
    lastPollEl.style.color = lastPoll.status === "success" ? "var(--accent-emerald)" : "var(--accent-rose)";
  } else {
    lastPollEl.textContent = "Waiting...";
  }

  document.getElementById("metric-last-seen-id").textContent = `Last ID: ${stats.last_seen_id || '--'}`;
  document.getElementById("metric-list-id").textContent = data.list_id || "Not Configured";
  
  const intervalSec = data.poll_interval || 180;
  const intervalDisplay = intervalSec >= 60 && intervalSec % 60 === 0 
    ? `${intervalSec / 60}m (${intervalSec}s)` 
    : `${intervalSec}s`;
  document.getElementById("metric-interval-footer").textContent = `Every ${intervalDisplay} + Jitter`;

  // 3. Rules
  const f = data.filter_settings || {};
  document.getElementById("rule-retweets").className = f.include_retweets ? "rule-status enabled" : "rule-status disabled";
  document.getElementById("rule-retweets").textContent = f.include_retweets ? "Included" : "Filtered";

  document.getElementById("rule-replies").className = f.include_replies ? "rule-status enabled" : "rule-status disabled";
  document.getElementById("rule-replies").textContent = f.include_replies ? "Included" : "Filtered";

  document.getElementById("rule-quotes").className = f.include_quotes ? "rule-status enabled" : "rule-status disabled";
  document.getElementById("rule-quotes").textContent = f.include_quotes ? "Included" : "Filtered";

  // 4. Tweets Feed
  const feed = document.getElementById("tweets-feed");
  const tweets = data.recent_tweets || [];
  document.getElementById("tweet-count-badge").textContent = `${tweets.length} Posts`;

  if (tweets.length === 0) {
    feed.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📬</div>
        <h3>No Posts Notified Yet</h3>
        <p>When monitored accounts tweet, new alerts will appear here in real-time.</p>
      </div>`;
  } else {
    feed.innerHTML = tweets.map(t => {
      const mediaHint = (t.media_urls && t.media_urls.length > 0)
        ? `<div class="tweet-media-badge">📷 Attached Media (${t.media_urls.length})</div>`
        : "";
      return `
        <div class="tweet-card">
          <div class="tweet-top">
            <a href="https://x.com/${t.author_handle}" target="_blank" class="tweet-author">@${t.author_handle}</a>
            <span class="tweet-time mono">${t.created_at || t.notified_at}</span>
          </div>
          <div class="tweet-body">${escapeHtml(t.text)}</div>
          ${mediaHint}
          <div class="tweet-footer">
            <span class="mono" style="color: var(--text-dim); font-size: 11px;">ID: ${t.tweet_id}</span>
            <a href="https://x.com/${t.author_handle}/status/${t.tweet_id}" target="_blank" class="btn-link">View on X &rarr;</a>
          </div>
        </div>
      `;
    }).join("");
  }

  // 5. Polls Table
  const pollsTableBody = document.getElementById("polls-table-body");
  const polls = data.recent_polls || [];
  if (polls.length > 0) {
    pollsTableBody.innerHTML = polls.map(p => {
      const isOk = p.status === "success";
      const statusBadge = isOk 
        ? `<span class="badge-status-ok">SUCCESS</span>` 
        : `<span class="badge-status-err">ERROR</span>`;
      return `
        <tr>
          <td class="mono">${(p.timestamp || "").split(" ")[1] || p.timestamp}</td>
          <td>${statusBadge}</td>
          <td class="mono">${p.tweets_found}</td>
          <td class="mono">${p.tweets_notified}</td>
        </tr>
      `;
    }).join("");
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Button Listeners
document.getElementById("btn-toggle-pause").addEventListener("click", async () => {
  const endpoint = currentStatus.is_paused ? "/api/resume" : "/api/pause";
  try {
    const res = await fetch(endpoint, { method: "POST" });
    const data = await res.json();
    showToast(data.is_paused ? "Monitoring Paused" : "Monitoring Resumed");
    fetchStatus();
  } catch (err) {
    showToast("Action failed: " + err, true);
  }
});

document.getElementById("btn-poll-now").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/poll_now", { method: "POST" });
    const data = await res.json();
    showToast("Poll cycle triggered immediately!");
    setTimeout(fetchStatus, 800);
  } catch (err) {
    showToast("Trigger failed: " + err, true);
  }
});

// Periodic fetch loop (every 3s)
fetchStatus();
setInterval(fetchStatus, 3000);
