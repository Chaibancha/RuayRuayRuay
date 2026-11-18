/* Frontend logic for 1xBet 4-Method Odds Fetcher & Download Dashboard */

function formatUtcDate(dateObj) {
  return dateObj.toISOString().slice(0, 10);
}

function defaultDateRange() {
  const start = new Date();
  const end = new Date(start.getTime() + 3 * 86400000);
  return { from: formatUtcDate(start), to: formatUtcDate(end) };
}

const DEF_DATES = defaultDateRange();

const STATE = {
  methodsMeta: [],
  sportsCatalog: [],
  resultsByMethod: {},
  savedConfig: {
    mode: "prematch",
    sport_id: 1,
    count: 6,
    date_from: DEF_DATES.from,
    date_to: DEF_DATES.to,
    domain: "https://1xbet.com",
    proxy: "",
    oddspapi_key: "",
    live_browser: false,
  },
  settingsDirty: false,
  fetchingTarget: null,
  fetchStartedAt: 0,
  timerHandle: null,
};

document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
});

async function initDashboard() {
  setFetchingState(null);
  try {
    const [methodsResp, resultsResp] = await Promise.all([
      fetch("/api/methods"),
      fetch("/api/results"),
    ]);
    const methodsData = await methodsResp.json();
    const resultsData = await resultsResp.json();

    STATE.methodsMeta = methodsData.methods || [];
    STATE.sportsCatalog = methodsData.sports || [];
    STATE.resultsByMethod = resultsData.results || {};

    populateSportsDropdown();

    const localCfgRaw = localStorage.getItem("xbet_saved_settings_v3");
    const serverCfg = methodsData.settings || {};
    const mergedCfg = localCfgRaw
      ? { ...STATE.savedConfig, ...serverCfg, ...JSON.parse(localCfgRaw) }
      : { ...STATE.savedConfig, ...serverCfg };

    applyConfigToForm(mergedCfg);
    STATE.savedConfig = mergedCfg;
    STATE.settingsDirty = false;

    renderAll();
  } catch (err) {
    const titleEl = document.getElementById("liveStateTitle");
    if (titleEl) titleEl.textContent = `❌ โหลดข้อมูลเริ่มต้นไม่สำเร็จ: ${err.message}`;
  }
}

function populateSportsDropdown() {
  const selectEl = document.getElementById("cfgSport");
  if (!selectEl || STATE.sportsCatalog.length === 0) return;
  const currentVal = selectEl.value;
  selectEl.innerHTML = STATE.sportsCatalog
    .map((sp) => `<option value="${sp.id}">${escapeHtml(sp.label)}</option>`)
    .join("");
  if (currentVal !== "") selectEl.value = currentVal;
}

function parseSportIdSafe(rawVal) {
  if (rawVal === null || rawVal === undefined || rawVal === "") return 1;
  const n = Number(rawVal);
  return Number.isNaN(n) ? 1 : n;
}

function readFormConfig() {
  const def = defaultDateRange();
  let dateFrom = (document.getElementById("cfgDateFrom").value || def.from).trim();
  let dateTo = (document.getElementById("cfgDateTo").value || def.to).trim();
  if (dateTo < dateFrom) {
    const tmp = dateFrom;
    dateFrom = dateTo;
    dateTo = tmp;
  }
  const rawCount = parseInt(document.getElementById("cfgCount").value, 10);
  return {
    mode: document.getElementById("cfgMode").value === "live" ? "live" : "prematch",
    sport_id: parseSportIdSafe(document.getElementById("cfgSport").value),
    count: Math.max(1, Math.min(Number.isNaN(rawCount) ? 50 : rawCount, 1000)),
    date_from: dateFrom,
    date_to: dateTo,
    domain: document.getElementById("cfgDomain").value.trim() || "https://1xbet.com",
    proxy: document.getElementById("cfgProxy").value.trim(),
    oddspapi_key: document.getElementById("cfgOddsPapiKey").value.trim(),
    live_browser: document.getElementById("cfgLiveBrowser").checked,
  };
}

function applyConfigToForm(cfg) {
  const def = defaultDateRange();
  document.getElementById("cfgMode").value = cfg.mode === "live" ? "live" : "prematch";
  const sid = parseSportIdSafe(cfg.sport_id);
  document.getElementById("cfgSport").value = String(sid);
  document.getElementById("cfgCount").value = String(cfg.count || 6);
  document.getElementById("cfgDateFrom").value = cfg.date_from || def.from;
  document.getElementById("cfgDateTo").value = cfg.date_to || def.to;
  document.getElementById("cfgDomain").value = cfg.domain || "https://1xbet.com";
  document.getElementById("cfgProxy").value = cfg.proxy || "";
  document.getElementById("cfgOddsPapiKey").value = cfg.oddspapi_key || "";
  document.getElementById("cfgLiveBrowser").checked = Boolean(cfg.live_browser);
}

function applyDatePreset(daysAhead) {
  const start = new Date();
  const end = new Date(start.getTime() + Number(daysAhead) * 86400000);
  document.getElementById("cfgDateFrom").value = formatUtcDate(start);
  document.getElementById("cfgDateTo").value = formatUtcDate(end);
  markSettingsDirty();
}

function markSettingsDirty() {
  STATE.settingsDirty = true;
  renderSavedSettingsSummary();
}

async function saveSettings() {
  const cfg = readFormConfig();
  applyConfigToForm(cfg);
  STATE.savedConfig = cfg;
  localStorage.setItem("xbet_saved_settings_v3", JSON.stringify(cfg));

  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
  } catch (_) {
    // LocalStorage backup already saved
  }

  STATE.settingsDirty = false;
  renderSavedSettingsSummary();
  renderMethodCards();

  const actText = document.getElementById("activityText");
  if (actText && !STATE.fetchingTarget) {
    actText.textContent = `✅ บันทึกการตั้งค่าแล้ว (${getSportLabel(cfg.sport_id)} · ${cfg.date_from} ถึง ${cfg.date_to} · ${cfg.count} คู่/วิธี)`;
  }
}

function getSportLabel(sportId) {
  const sid = parseSportIdSafe(sportId);
  const found = STATE.sportsCatalog.find((s) => Number(s.id) === sid);
  if (found) return found.label;
  const opt = document.querySelector(`#cfgSport option[value="${sid}"]`);
  return opt ? opt.textContent : `Sport #${sid}`;
}

function renderSavedSettingsSummary() {
  const badge = document.getElementById("settingsDirtyBadge");
  const inline = document.getElementById("savedSummaryInline");
  const step2Banner = document.getElementById("activeSavedBanner");

  const cfg = STATE.savedConfig;
  const modeLabel = cfg.mode === "live" ? "กำลังแข่งสด (Live)" : "ก่อนแข่ง (Pre-match)";
  const sportLabel = getSportLabel(cfg.sport_id);

  if (badge) {
    if (STATE.settingsDirty) {
      badge.className = "badge badge-fallback";
      badge.textContent = "⚠️ มีการแก้ไข — กดบันทึกหรือกดดึงเพื่อบันทึกอัตโนมัติ";
    } else {
      badge.className = "badge badge-live";
      badge.textContent = "✅ บันทึกการตั้งค่าล่าสุดแล้ว";
    }
  }

  const summaryHtml = `ค่าที่บันทึกไว้: <strong>${escapeHtml(modeLabel)}</strong> · กีฬา: <strong>${escapeHtml(
    sportLabel
  )}</strong> · ช่วงเวลา: <strong>${escapeHtml(cfg.date_from)} ถึง ${escapeHtml(
    cfg.date_to
  )}</strong> · จำนวน: <strong>${cfg.count} คู่/วิธี</strong>`;

  if (inline) inline.innerHTML = summaryHtml;
  if (step2Banner) step2Banner.innerHTML = summaryHtml;
}

function setFetchingState(target) {
  STATE.fetchingTarget = target;
  const pill = document.getElementById("liveStatePill");
  const spinner = document.getElementById("liveStateSpinner");
  const dot = document.getElementById("liveStateDot");
  const title = document.getElementById("liveStateTitle");
  const detail = document.getElementById("liveStateDetail");
  const progressTrack = document.getElementById("topProgressTrack");

  const actBox = document.getElementById("fetchActivityBox");
  const actSpinner = document.getElementById("activitySpinner");
  const actText = document.getElementById("activityText");
  const actTimer = document.getElementById("activityTimer");
  const btnAll = document.getElementById("btnRunAll");

  if (STATE.timerHandle) {
    clearInterval(STATE.timerHandle);
    STATE.timerHandle = null;
  }

  if (target) {
    STATE.fetchStartedAt = performance.now();
    const label = target === "all" ? "ทั้ง 4 วิธีพร้อมกัน" : `วิธีที่ ${target}`;

    pill.className = "live-state-pill fetching";
    spinner.classList.remove("hidden");
    dot.classList.add("hidden");
    title.textContent = `⏳ กำลังดึงข้อมูล (${label})...`;
    detail.textContent = `${getSportLabel(STATE.savedConfig.sport_id)} · ${STATE.savedConfig.date_from} ถึง ${STATE.savedConfig.date_to}`;
    progressTrack.classList.remove("hidden");

    actBox.className = "activity-box fetching";
    actSpinner.classList.remove("hidden");
    actText.textContent = `⏳ กำลังติดต่อแหล่งข้อมูล (${label}) กรุณารอสักครู่...`;
    actTimer.textContent = "0.0s";
    if (btnAll) btnAll.disabled = true;

    STATE.timerHandle = setInterval(() => {
      const sec = ((performance.now() - STATE.fetchStartedAt) / 1000).toFixed(1);
      actTimer.textContent = `${sec}s`;
    }, 100);
  } else {
    pill.className = "live-state-pill idle";
    spinner.classList.add("hidden");
    dot.classList.remove("hidden");

    const allMatches = getAllMatches();
    const timestamps = Object.values(STATE.resultsByMethod)
      .map((r) => r && r.fetched_at_utc)
      .filter(Boolean)
      .sort();
    const latest =
      timestamps.length > 0
        ? timestamps[timestamps.length - 1].replace("T", " ").replace("Z", " UTC")
        : "-";

    title.textContent = "🟢 พร้อมใช้งาน (ไม่ได้กำลังดึงข้อมูล)";
    detail.textContent = `ข้อมูลในตาราง: ${allMatches.length} คู่ · อัปเดต: ${latest}`;
    progressTrack.classList.add("hidden");

    actBox.className = "activity-box idle";
    actSpinner.classList.add("hidden");
    actTimer.textContent = "";
    if (btnAll) btnAll.disabled = false;
  }
}

async function triggerFetch(methodTarget = "all") {
  if (STATE.fetchingTarget) return;

  if (STATE.settingsDirty) {
    await saveSettings();
  }

  const payload = { ...STATE.savedConfig, method: methodTarget };
  setFetchingState(methodTarget);
  renderMethodCards();

  try {
    const resp = await fetch("/api/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || "Request failed");
    }

    STATE.resultsByMethod = data.all_results || data.results || {};
    const methodsResp = await fetch("/api/methods");
    const methodsJson = await methodsResp.json();
    STATE.methodsMeta = methodsJson.methods || STATE.methodsMeta;

    // Auto-sync Step 3 Download Center selector & Step 4 Table filter to the method just fetched
    const dlSelect = document.getElementById("dlMethodSelect");
    if (dlSelect) {
      dlSelect.value = methodTarget;
    }
    const filterMethodEl = document.getElementById("filterMethod");
    if (filterMethodEl) {
      filterMethodEl.value = methodTarget;
    }

    const elapsedSec = ((performance.now() - STATE.fetchStartedAt) / 1000).toFixed(2);
    setFetchingState(null);
    const label = methodTarget === "all" ? "ทั้ง 4 วิธี" : `วิธีที่ ${methodTarget}`;
    document.getElementById(
      "activityText"
    ).textContent = `✅ ดึงข้อมูล (${label}) เสร็จสิ้นใน ${elapsedSec} วินาที — พร้อมตรวจสอบผลและดาวน์โหลด!`;
    renderAll();
  } catch (err) {
    setFetchingState(null);
    document.getElementById("activityText").textContent = `❌ ดึงข้อมูลไม่สำเร็จ: ${err.message}`;
    renderMethodCards();
  }
}

function renderAll() {
  renderSavedSettingsSummary();
  renderComparisonTable();
  renderMethodCards();
  updateDownloadSummary();
  renderOddsTable();
  renderRawJson();
  if (!STATE.fetchingTarget) {
    setFetchingState(null);
  }
}

function getAllMatches() {
  const list = [];
  ["1", "2", "3", "4"].forEach((id) => {
    const res = STATE.resultsByMethod[id];
    if (res && Array.isArray(res.matches)) {
      list.push(...res.matches);
    }
  });
  return list;
}

function renderComparisonTable() {
  const tbody = document.getElementById("comparisonTableBody");
  if (!tbody) return;

  tbody.innerHTML = STATE.methodsMeta
    .map(
      (m) => `
      <tr>
        <td><strong>${escapeHtml(m.name)}</strong></td>
        <td>${escapeHtml(m.cost)}</td>
        <td>${escapeHtml(m.latency)}</td>
        <td>${escapeHtml(m.difficulty)}</td>
        <td>${escapeHtml(m.best_for)}</td>
      </tr>
    `
    )
    .join("");
}

function renderMethodCards() {
  const grid = document.getElementById("methodCardsGrid");
  if (!grid) return;

  const isBusy = Boolean(STATE.fetchingTarget);
  const savedCount = STATE.savedConfig.count;

  grid.innerHTML = STATE.methodsMeta
    .map((m) => {
      const res = STATE.resultsByMethod[m.id];
      const thisFetching =
        STATE.fetchingTarget === "all" || STATE.fetchingTarget === m.id;
      const isLive = res && res.is_live_data;
      const count = res ? res.match_count : 0;
      const latency = res ? `${res.latency_ms} ms` : "-";

      let statusHtml = "";
      if (thisFetching) {
        statusHtml = `<span class="badge badge-fetching"><span class="spinner" style="width:11px;height:11px;border-width:2px;"></span> กำลังดึงข้อมูล...</span>`;
      } else if (res) {
        statusHtml = `<span class="badge ${isLive ? "badge-live" : "badge-fallback"}">${escapeHtml(
          res.source_mode
        )}</span>`;
      } else {
        statusHtml = `<span class="badge badge-fallback">พร้อมเรียกใช้งาน</span>`;
      }

      return `
        <article class="method-card ${thisFetching ? "is-fetching" : ""}">
          <div>
            <div class="method-card-top">
              <span class="method-num-badge">METHOD #${m.id}</span>
              ${statusHtml}
            </div>
            <h3>${escapeHtml(m.name)}</h3>
            <p class="method-desc">${escapeHtml(m.best_for)}</p>
          </div>

          <div>
            <div class="method-metrics-row">
              <span>ผลล่าสุด: <strong>${count} คู่</strong></span>
              <span>เวลาที่ใช้: <strong>${latency}</strong></span>
            </div>
            <button
              class="btn btn-primary btn-block"
              style="margin-top:10px;"
              onclick="triggerFetch('${m.id}')"
              ${isBusy ? "disabled" : ""}
            >
              ${
                thisFetching
                  ? "⏳ กำลังดึงข้อมูล..."
                  : `▶ เรียกดึงวิธีที่ ${m.id} (${savedCount} คู่)`
              }
            </button>
          </div>
        </article>
      `;
    })
    .join("");
}

function updateDownloadSummary() {
  const sel = document.getElementById("dlMethodSelect").value;
  const box = document.getElementById("dlSummaryBox");
  if (!box) return;

  if (sel === "all") {
    const total = getAllMatches().length;
    box.innerHTML = `📦 เลือกดาวน์โหลด <strong>ครบทั้ง 4 วิธีรวมกัน</strong> — มีข้อมูลพร้อมดาวน์โหลด <strong>${total} คู่</strong>`;
  } else {
    const res = STATE.resultsByMethod[sel];
    const meta = STATE.methodsMeta.find((m) => m.id === sel);
    const count = res ? res.match_count : 0;
    const title = meta ? meta.name : `วิธีที่ ${sel}`;
    box.innerHTML = `📌 เลือกดาวน์โหลดเฉพาะ <strong>${escapeHtml(
      title
    )}</strong> — มีข้อมูลพร้อมดาวน์โหลด <strong>${count} คู่</strong>`;
  }
}

function downloadFile(format, overrideMethod = null) {
  const method =
    overrideMethod || document.getElementById("dlMethodSelect").value || "all";
  const url = `/api/download?format=${encodeURIComponent(
    format
  )}&method=${encodeURIComponent(method)}`;
  window.location.href = url;
}

function renderOddsTable() {
  const tbody = document.getElementById("oddsTableBody");
  const badge = document.getElementById("tableCountBadge");
  if (!tbody) return;

  const methodFilter = document.getElementById("filterMethod").value;
  const activeFilter = document.getElementById("filterActive").value;
  const searchQuery = (document.getElementById("filterSearch").value || "")
    .trim()
    .toLowerCase();

  const filtered = getAllMatches().filter((m) => {
    if (methodFilter !== "all" && m.method_id !== methodFilter) return false;
    if (activeFilter === "active" && !m.market_active) return false;
    if (activeFilter === "suspended" && m.market_active) return false;
    if (searchQuery) {
      const hay = `${m.sport} ${m.league} ${m.home_team} ${m.away_team} ${m.method_name}`.toLowerCase();
      if (!hay.includes(searchQuery)) return false;
    }
    return true;
  });

  if (badge) badge.textContent = String(filtered.length);

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align:center;padding:28px;color:#94a3b8;">
          ไม่พบรายการแข่งขันที่ตรงกับตัวกรอง
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered
    .map((m) => {
      const probs = [m.implied_prob_home, m.implied_prob_draw, m.implied_prob_away];
      const probText =
        probs[0] && probs[1] && probs[2]
          ? `1: ${probs[0]}% | X: ${probs[1]}% | 2: ${probs[2]}%`
          : probs[0] && probs[2]
          ? `1: ${probs[0]}% | 2: ${probs[2]}%`
          : "-";

      const marginText =
        m.overround_pct !== null && m.overround_pct !== undefined
          ? `${m.overround_pct > 0 ? "+" : ""}${m.overround_pct}%`
          : "-";
      const hdpText =
        m.handicap_line !== null && m.handicap_line !== undefined
          ? `(${m.handicap_line}) ${m.handicap_home ?? "-"} / ${m.handicap_away ?? "-"}`
          : "-";
      const ouText =
        m.total_line !== null && m.total_line !== undefined
          ? `(${m.total_line}) สูง ${m.odds_over ?? "-"} / ต่ำ ${m.odds_under ?? "-"}`
          : "-";

      const marketBadge = m.market_active
        ? `<span class="badge badge-live">Active</span>`
        : `<span class="badge badge-suspended">Suspended</span>`;

      const timeDisplay =
        m.start_time_local ||
        (m.start_time_utc || "").replace("T", " ").replace("Z", " UTC");

      return `
        <tr>
          <td>
            <span class="badge badge-method">วิธีที่ ${escapeHtml(m.method_id)}</span>
          </td>
          <td>
            <div style="font-size:11.5px;color:#7dd3fc;">${escapeHtml(m.sport || "-")}</div>
            <div><strong>${escapeHtml(m.league)}</strong></div>
            <small style="color:#94a3b8;">${escapeHtml(timeDisplay)}</small>
          </td>
          <td>
            <div><strong>${escapeHtml(m.home_team)}</strong> vs <strong>${escapeHtml(
              m.away_team
            )}</strong></div>
            <small style="color:#38bdf8;">${escapeHtml(m.match_status)} ${
              m.score && m.score !== "-" ? `· สกอร์: ${escapeHtml(m.score)}` : ""
            }</small>
          </td>
          <td class="num-col"><span class="odds-pill">${fmtNum(m.odds_home)}</span></td>
          <td class="num-col"><span class="odds-pill">${fmtNum(m.odds_draw)}</span></td>
          <td class="num-col"><span class="odds-pill">${fmtNum(m.odds_away)}</span></td>
          <td><span class="prob-bar-text">${escapeHtml(probText)}</span></td>
          <td class="num-col">${escapeHtml(marginText)}</td>
          <td><span class="prob-bar-text">${escapeHtml(hdpText)}</span></td>
          <td><span class="prob-bar-text">${escapeHtml(ouText)}</span></td>
          <td>${marketBadge}</td>
        </tr>
      `;
    })
    .join("");
}

function switchExplorerTab(tab) {
  const tableTab = document.getElementById("explorerTabTable");
  const rawTab = document.getElementById("explorerTabRaw");
  const btnTable = document.getElementById("tabBtnTable");
  const btnRaw = document.getElementById("tabBtnRaw");
  const filterBar = document.getElementById("tableFilterBar");

  if (tab === "raw") {
    tableTab.classList.add("hidden");
    rawTab.classList.remove("hidden");
    btnTable.classList.remove("active");
    btnRaw.classList.add("active");
    filterBar.classList.add("hidden");
    renderRawJson();
  } else {
    rawTab.classList.add("hidden");
    tableTab.classList.remove("hidden");
    btnRaw.classList.remove("active");
    btnTable.classList.add("active");
    filterBar.classList.remove("hidden");
  }
}

function renderRawJson() {
  const sel = document.getElementById("rawMethodSelect").value;
  const viewer = document.getElementById("rawJsonViewer");
  if (!viewer) return;

  let targetData = {};
  if (sel === "all") {
    targetData = STATE.resultsByMethod;
  } else {
    const res = STATE.resultsByMethod[sel];
    targetData = res ? res.raw_payload : { message: "ยังไม่มีข้อมูลสำหรับวิธีนี้" };
  }
  viewer.textContent = JSON.stringify(targetData, null, 2);
}

async function copyRawJson() {
  const viewer = document.getElementById("rawJsonViewer");
  if (!viewer) return;
  try {
    await navigator.clipboard.writeText(viewer.textContent);
    document.getElementById("activityText").textContent = "📋 คัดลอก Raw JSON ลงคลิปบอร์ดแล้ว!";
  } catch (err) {
    document.getElementById("activityText").textContent = "กรุณาเลือกคลุมข้อความแล้วกด Ctrl+C";
  }
}

function downloadRawFromInspector() {
  const sel = document.getElementById("rawMethodSelect").value || "all";
  downloadFile("raw_json", sel);
}

function fmtNum(val) {
  if (val === null || val === undefined || val === "") return "-";
  const num = Number(val);
  return Number.isNaN(num) ? "-" : num.toFixed(2);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
