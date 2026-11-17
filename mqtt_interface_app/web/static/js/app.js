// EventSupplier web UI. Vanilla JS, no build step.
// Talks to the versioned REST API under /api/v1; new features should follow
// the same pattern: a fetch helper + a render function + polling if live.

const $ = (id) => document.getElementById(id);

const state = {
  activeTab: "dashboard",
  watchIntervalMs: 2000,
  pollTimer: null,
  lastEventId: 0,
  restartRequiredKeys: [],
  settings: {},
  volumeInitialized: false,
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (_) { /* non-JSON error body */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Generic UI helpers
// ---------------------------------------------------------------------------

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 3500);
}

function fmtTime(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleTimeString();
}

function fmtDuration(seconds) {
  if (seconds == null) return "-";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function fmtLength(seconds) {
  if (seconds == null) return "-";
  return fmtDuration(seconds);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Tabs + polling lifecycle
// ---------------------------------------------------------------------------

function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  restartPolling();
  if (name === "positions") loadPositions();
  if (name === "settings") loadSettingsForm();
}

function restartPolling() {
  clearInterval(state.pollTimer);
  if (state.activeTab === "dashboard") {
    refreshDashboard();
    state.pollTimer = setInterval(refreshDashboard, state.watchIntervalMs);
  } else if (state.activeTab === "positions") {
    state.pollTimer = setInterval(loadPositions, 10000);
  } else {
    state.pollTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function refreshDashboard() {
  try {
    const data = await api("/api/v1/status");
    setHealth(true);
    renderWatcher(data.watcher);
    renderMedia(data.vlc);
    await refreshEvents();
  } catch (err) {
    setHealth(false);
  }
}

function setHealth(ok) {
  $("health-dot").className = `dot ${ok ? "ok" : "error"}`;
  $("health-text").textContent = ok ? "connected" : "API unreachable";
}

function renderWatcher(w) {
  $("w-vlc-status").textContent = w.vlc_status;
  $("w-last-media").textContent = w.last_media || "-";
  $("w-last-error").textContent = w.last_error || "-";
  $("w-retrying").textContent = w.is_retrying ? "yes" : "no";
  $("w-retry-count").textContent = `${w.retry_count}`;
  $("w-loops").textContent = w.loop_count;
  $("w-uptime").textContent = fmtDuration(w.uptime_seconds);
}

function renderMedia(vlc) {
  const media = vlc.media || {};
  $("m-filename").textContent = media.filename || "No media";
  $("m-state").textContent = `state: ${vlc.state || "-"}`;

  const hasPosition = vlc.position != null;
  $("m-progress").style.width = hasPosition ? `${(vlc.position * 100).toFixed(1)}%` : "0";
  $("m-time").textContent = fmtDuration(vlc.time);
  $("m-length").textContent = fmtLength(vlc.length);

  if (vlc.volume != null) {
    $("volume-range").value = vlc.volume;
    $("volume-value").textContent = `${Math.round(vlc.volume)}%`;
    state.volumeInitialized = true;
  } else if (!state.volumeInitialized) {
    $("volume-value").textContent = "-";
  }
}

async function refreshEvents() {
  const data = await api(`/api/v1/events?limit=100&min_id=${state.lastEventId}`);
  if (data.events.length > 0) {
    state.lastEventId = data.last_id;
    const feed = $("event-feed");
    if (feed.querySelector(".muted")) feed.innerHTML = "";
    for (const e of data.events.reverse()) {
      feed.insertAdjacentHTML(
        "beforeend",
        `<div class="event ${e.level} topic-${escapeHtml(e.topic)}">
           <span class="time">${escapeHtml(fmtTime(e.time))}</span>
           <span class="topic">${escapeHtml(e.topic)}</span>
           <span class="message">${escapeHtml(e.message)}</span>
         </div>`
      );
      while (feed.children.length > 200) feed.removeChild(feed.firstChild);
    }
    feed.scrollTop = feed.scrollHeight;
  } else if (state.lastEventId === 0) {
    // keep placeholder
  }
}

async function vlcCommand(command, body) {
  try {
    const result = await api(`/api/v1/vlc/${command}`, { method: "POST", body: JSON.stringify(body || {}) });
    toast(result.message || result.status, result.status !== "ok");
    refreshDashboard();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Positions
// ---------------------------------------------------------------------------

async function loadPositions() {
  const q = $("positions-search").value.trim();
  try {
    const data = await api(`/api/v1/positions?q=${encodeURIComponent(q)}`);
    $("positions-count").textContent = `${data.count} entries`;
    const body = $("positions-body");
    if (data.items.length === 0) {
      body.innerHTML = '<tr><td colspan="8" class="muted">No entries</td></tr>';
      return;
    }
    body.innerHTML = data.items
      .map(
        (item) => `<tr>
          <td class="name" title="${escapeHtml(item.media_name)}">${escapeHtml(item.media_name)}</td>
          <td>
            <div class="progress-bar" style="width:120px">
              <div class="progress-fill" style="width:${item.position_percent}%"></div>
            </div>
          </td>
          <td>${item.position_percent.toFixed(1)}%</td>
          <td>${fmtLength(item.length)}</td>
          <td>${item.remaining_seconds == null ? "-" : fmtDuration(item.remaining_seconds)}</td>
          <td>${escapeHtml(item.datetime ? item.datetime.slice(0, 16).replace("T", " ") : "-")}</td>
          <td><span class="badge ${item.finished ? "finished" : item.position > 0.01 ? "watching" : "new"}">
            ${item.finished ? "finished" : item.position > 0.01 ? "watching" : "new"}</span></td>
          <td class="actions">
            <button data-act="edit" data-name="${escapeHtml(item.media_name)}">Edit</button>
            <button data-act="reset" data-name="${escapeHtml(item.media_name)}">Reset</button>
            <button data-act="finish" data-name="${escapeHtml(item.media_name)}">Mark finished</button>
            <button data-act="delete" data-name="${escapeHtml(item.media_name)}" class="danger">Delete</button>
          </td>
        </tr>`
      )
      .join("");
  } catch (err) {
    toast(`Failed to load positions: ${err.message}`, true);
  }
}

async function onPositionAction(act, name) {
  try {
    if (act === "edit") {
      const entry = await api(`/api/v1/positions/${encodeURIComponent(name)}`);
      const input = prompt(`Position for "${name}" (0-100 %):`, (entry.position * 100).toFixed(2));
      if (input === null) return;
      const percent = parseFloat(input);
      if (Number.isNaN(percent) || percent < 0 || percent > 100) {
        toast("Position must be between 0 and 100", true);
        return;
      }
      await api(`/api/v1/positions/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify({ position: percent / 100, length: entry.length }),
      });
      toast(`Updated ${name}`);
    } else if (act === "reset") {
      await api(`/api/v1/positions/${encodeURIComponent(name)}/reset`, { method: "POST" });
      toast(`Reset ${name}`);
    } else if (act === "finish") {
      await api(`/api/v1/positions/${encodeURIComponent(name)}/mark_finished`, { method: "POST" });
      toast(`Marked ${name} as finished`);
    } else if (act === "delete") {
      if (!confirm(`Delete position entry for "${name}"? This cannot be undone.`)) return;
      await api(`/api/v1/positions/${encodeURIComponent(name)}`, { method: "DELETE" });
      toast(`Deleted ${name}`);
    }
    loadPositions();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

const SETTING_LABELS = {
  vlc_host: "VLC host",
  vlc_port: "VLC port",
  vlc_key: "VLC password",
  mqtt_host: "MQTT host",
  mqtt_port: "MQTT port",
  subtitle_language: "Preferred subtitle language",
  watch_interval: "Poll interval (s)",
  web_host: "Web bind host",
  web_port: "Web port",
};

const HIDDEN_SETTINGS = new Set([]); // extend to hide fields from the UI

async function loadSettingsForm() {
  try {
    const data = await api("/api/v1/settings");
    state.restartRequiredKeys = data.restart_required_keys;
    state.settings = data.settings;
    const container = $("settings-fields");
    container.innerHTML = Object.entries(data.settings)
      .filter(([key]) => !HIDDEN_SETTINGS.has(key))
      .map(([key, value]) => {
        const needsRestart = data.restart_required_keys.includes(key);
        const type = typeof value === "number" ? "number" : "text";
        const step = typeof value === "number" && !Number.isInteger(value) ? "0.1" : "1";
        return `<div class="field">
          <label for="set-${key}">${SETTING_LABELS[key] || key}${needsRestart ? '<span class="star"> *</span>' : ""}</label>
          <input id="set-${key}" name="${key}" type="${type}" step="${step}" value="${escapeHtml(value)}">
          <span></span>
        </div>`;
      })
      .join("");
  } catch (err) {
    toast(`Failed to load settings: ${err.message}`, true);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const updates = {};
  document.querySelectorAll("#settings-fields input").forEach((input) => {
    const key = input.name;
    const current = state.settings[key];
    updates[key] = typeof current === "number" ? parseFloat(input.value) : input.value;
  });
  try {
    const result = await api("/api/v1/settings", { method: "PUT", body: JSON.stringify(updates) });
    const el = $("settings-result");
    el.className = "result ok";
    if (result.restart_required.length > 0) {
      el.textContent = "Saved. Restart the app for these to take effect: " + result.restart_required.join(", ");
      el.className = "result warn";
    } else {
      el.textContent = "Saved.";
    }
    if (result.updated.includes("watch_interval")) {
      state.watchIntervalMs = Math.max(500, result.settings.watch_interval * 1000);
      restartPolling();
    }
  } catch (err) {
    const el = $("settings-result");
    el.className = "result error";
    el.textContent = `Save failed: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function initPollInterval() {
  try {
    const data = await api("/api/v1/settings");
    const interval = data.settings.watch_interval;
    if (interval >= 0.5) state.watchIntervalMs = interval * 1000;
  } catch (_) {
    // settings unavailable: keep the 2s default
  }
  restartPolling();
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

  $("btn-play").addEventListener("click", () => vlcCommand("play"));
  $("btn-pause").addEventListener("click", () => vlcCommand("pause"));
  $("btn-stop").addEventListener("click", () => vlcCommand("stop"));

  let volumeTimer = null;
  $("volume-range").addEventListener("input", (e) => {
    $("volume-value").textContent = `${e.target.value}%`;
    clearTimeout(volumeTimer);
    volumeTimer = setTimeout(() => vlcCommand("volume", { volume: parseInt(e.target.value, 10) }), 300);
  });

  $("seek-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const value = parseFloat($("seek-input").value);
    if (!Number.isNaN(value)) vlcCommand("seek", { position: value });
  });

  $("positions-search").addEventListener("input", () => {
    clearTimeout($("positions-search")._timer);
    $("positions-search")._timer = setTimeout(loadPositions, 250);
  });

  $("hide-errors").addEventListener("change", (e) => {
    $("event-feed").classList.toggle("hide-errors", e.target.checked);
  });

  $("hide-positions").addEventListener("change", (e) => {
    $("event-feed").classList.toggle("hide-positions", e.target.checked);
  });

  // Event delegation: position table action buttons
  $("positions-table").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (btn) onPositionAction(btn.dataset.act, btn.dataset.name);
  });

  $("settings-form").addEventListener("submit", saveSettings);

  await initPollInterval();
});
