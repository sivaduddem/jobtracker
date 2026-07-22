async function refreshStats() {
  try {
    const res = await fetch("/api/stats");
    const s = await res.json();
    document.getElementById("stat-companies").textContent = s.companies_monitored ?? "—";
    document.getElementById("stat-active").textContent = s.jobs_active ?? "—";
    document.getElementById("stat-removed").textContent = s.jobs_removed ?? "—";
    document.getElementById("stat-errors").textContent = s.companies_with_errors ?? "—";
    document.getElementById("stat-last").textContent = s.last_successful_scrape || "—";
  } catch (_) { /* ignore */ }
}

async function refreshJobs() {
  const q = document.getElementById("search").value.trim();
  const sort = document.getElementById("sort").value;
  const active = document.getElementById("active-only").checked;
  const params = new URLSearchParams({ sort, active: String(active), limit: "80" });
  if (q) params.set("q", q);

  const res = await fetch(`/api/jobs?${params}`);
  const jobs = await res.json();
  const root = document.getElementById("jobs");
  if (!jobs.length) {
    root.innerHTML = `<p class="empty">No matching internships.</p>`;
    return;
  }
  root.innerHTML = jobs.map((job) => {
    const href = escapeAttr(safeHttpUrl(job.url));
    return `
    <article class="job">
      <div class="job-top">
        <h3><a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(job.title)}</a></h3>
        <span class="score">${Math.round(Number(job.score) || 0)}</span>
      </div>
      <div class="meta">
        <span>${escapeHtml(job.company)}</span>
        <span>${escapeHtml(job.term)}</span>
        <span>${escapeHtml(job.location || "—")}</span>
        <span class="provider">${escapeHtml(job.provider)}</span>
      </div>
      <div class="meta dim"><span>First seen ${escapeHtml(job.first_seen || "")}</span></div>
    </article>`;
  }).join("");
}

/** Escape text for HTML body content. */
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** Escape for double-quoted HTML attribute values. */
function escapeAttr(s) {
  return escapeHtml(s);
}

/**
 * Only allow http(s) URLs in href to block javascript:/data: injection.
 * Returns "#" when the value is missing or not a safe absolute http(s) URL.
 */
function safeHttpUrl(raw) {
  const value = String(raw ?? "").trim();
  if (!value) return "#";
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "#";
    }
    return parsed.href;
  } catch (_) {
    return "#";
  }
}

let debounce;
document.getElementById("search").addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(refreshJobs, 250);
});
document.getElementById("sort").addEventListener("change", refreshJobs);
document.getElementById("active-only").addEventListener("change", refreshJobs);

document.getElementById("poll-btn").addEventListener("click", async () => {
  const btn = document.getElementById("poll-btn");
  btn.disabled = true;
  btn.textContent = "Polling…";
  try {
    await fetch("/api/poll", { method: "POST" });
    await refreshStats();
    await refreshJobs();
  } finally {
    btn.disabled = false;
    btn.textContent = "Poll now";
  }
});

setInterval(refreshStats, 15000);
setInterval(refreshJobs, 30000);
