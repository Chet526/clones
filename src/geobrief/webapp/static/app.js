"use strict";

// GeoBrief LE front-end. Talks to the local FastAPI server, shows a
// plain-English summary, plots mappable points on a Leaflet map (with accuracy
// circles and a movement path), and offers all outputs as downloads.

let map = null;
let layerGroup = null;
let focusGroup = null;
let tileLayer = null;
let labelLayer = null;
let basemapChoice = "streets";
let lastResult = null;
let assistantAvailable = true;
let billingEnabled = false;

const THEME_KEY = "geobrief-theme";
const PANEL_KEY = "geobrief-assistant-open";
const CARTO_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';
const ESRI_ATTR =
  "Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community";
const BASEMAPS = {
  streets: {
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    light:
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution: CARTO_ATTR,
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTR,
  },
  hybrid: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    labels:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attribution: ESRI_ATTR,
  },
};

function currentTheme() {
  return document.documentElement.dataset.theme === "light"
    ? "light"
    : "dark";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch (err) {
    /* storage may be unavailable */
  }
  const toggle = el("theme-toggle");
  if (toggle) toggle.textContent = theme === "light" ? "☾" : "☀";
  refreshBasemap();
}

function refreshBasemap() {
  if (!map) return;
  const base = BASEMAPS[basemapChoice] || BASEMAPS.streets;
  if (tileLayer) map.removeLayer(tileLayer);
  if (labelLayer) {
    map.removeLayer(labelLayer);
    labelLayer = null;
  }
  const url =
    basemapChoice === "streets" ? base[currentTheme()] : base.url;
  tileLayer = L.tileLayer(url, {
    maxZoom: 19,
    attribution: base.attribution,
  }).addTo(map);
  if (base.labels) {
    labelLayer = L.tileLayer(base.labels, { maxZoom: 19 }).addTo(map);
  }
}

function wireBasemapSwitch() {
  document.querySelectorAll(".bm-btn").forEach((button) => {
    button.addEventListener("click", () => {
      basemapChoice = button.getAttribute("data-basemap");
      document
        .querySelectorAll(".bm-btn")
        .forEach((b) => b.classList.toggle("active", b === button));
      ensureMap();
      refreshBasemap();
    });
  });
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (err) {
    /* storage may be unavailable */
  }
  applyTheme(saved === "light" ? "light" : "dark");
}

function el(id) {
  return document.getElementById(id);
}

function setStatus(message, isError) {
  const status = el("status");
  status.textContent = message || "";
  status.classList.toggle("error", Boolean(isError));
}

function ensureMap() {
  if (map) {
    return;
  }
  map = L.map("map", { zoomControl: true });
  refreshBasemap();
  layerGroup = L.layerGroup().addTo(map);
  focusGroup = L.layerGroup().addTo(map);
  map.setView([20, 0], 2);
}

function showFocusPoints(points) {
  if (!map || !focusGroup) return;
  focusGroup.clearLayers();
  if (!points || !points.length) return;
  const bounds = [];
  for (const point of points) {
    const icon = L.divIcon({
      className: "",
      html: '<div class="focus-marker"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
    const marker = L.marker([point.latitude, point.longitude], {
      icon: icon,
      zIndexOffset: 1000,
    });
    if (point.label) {
      marker.bindTooltip(point.label, { direction: "top", offset: [0, -10] });
    }
    focusGroup.addLayer(marker);
    bounds.push([point.latitude, point.longitude]);
  }
  map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
}

function renderStats(summary) {
  const counts = summary.record_counts;
  const stats = [
    { value: counts.total, label: "Total records" },
    { value: counts.mappable, label: "Mappable points" },
    { value: counts.valid, label: "Valid points" },
    { value: counts.skipped_or_flagged, label: "Skipped / flagged" },
  ];
  el("stat-grid").innerHTML = stats
    .map(
      (s) =>
        `<div class="stat"><div class="value">${s.value}</div>` +
        `<div class="label">${s.label}</div></div>`
    )
    .join("");
}

function renderWarnings(summary) {
  const box = el("warnings");
  const list = el("warning-list");
  const warnings = summary.warnings || [];
  if (!warnings.length) {
    box.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  list.innerHTML = warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function popupHtml(props) {
  const rows = [
    ["Time (display)", props.display_timestamp || "—"],
    ["Time (UTC)", props.normalized_timestamp_utc || "—"],
    ["Source row", props.source_row_number],
    ["Accuracy (m)", props.accuracy_radius == null ? "—" : props.accuracy_radius],
    ["Status", props.validation_status],
  ];
  let html = "<table class='popup'>";
  for (const [label, value] of rows) {
    html += `<tr><th style="text-align:left;padding-right:6px">${label}</th>` +
      `<td>${escapeHtml(value)}</td></tr>`;
  }
  html += "</table>";
  if (props.warnings && props.warnings.length) {
    html += `<p style="color:#b45309;margin:4px 0 0">` +
      escapeHtml(props.warnings.join(" ")) + "</p>";
  }
  return html;
}

function pointMarker(lat, lon, props) {
  const flagged =
    props.validation_status !== "valid" ||
    (props.warnings && props.warnings.length);
  const icon = L.divIcon({
    className: "",
    html: `<div class="geo-marker${flagged ? " flagged" : ""}"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -8],
  });
  return L.marker([lat, lon], { icon: icon }).bindPopup(popupHtml(props));
}

function renderMap(geojson) {
  ensureMap();
  layerGroup.clearLayers();
  const bounds = [];
  const timed = [];
  for (const feature of geojson.features) {
    const [lon, lat] = feature.geometry.coordinates;
    const props = feature.properties;
    layerGroup.addLayer(pointMarker(lat, lon, props));
    if (props.accuracy_radius && props.accuracy_radius > 0) {
      layerGroup.addLayer(
        L.circle([lat, lon], {
          radius: props.accuracy_radius,
          color: "#22d3ee",
          weight: 1,
          fillOpacity: 0.07,
        })
      );
    }
    if (props.normalized_timestamp_utc) {
      timed.push({ at: props.normalized_timestamp_utc, latlng: [lat, lon] });
    }
    bounds.push([lat, lon]);
  }
  if (timed.length > 1) {
    timed.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
    layerGroup.addLayer(
      L.polyline(
        timed.map((t) => t.latlng),
        {
          color: "#8b5cf6",
          weight: 2.5,
          opacity: 0.75,
          dashArray: "6 8",
        }
      )
    );
  }
  if (bounds.length) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }
}

function featureTime(feature) {
  const stamp = feature.properties.normalized_timestamp_utc;
  if (!stamp) return null;
  const time = new Date(stamp).getTime();
  return Number.isNaN(time) ? null : time;
}

function initTimeFilter(geojson) {
  const times = geojson.features
    .map(featureTime)
    .filter((t) => t !== null)
    .sort((a, b) => a - b);
  const hasTimes = times.length > 0;
  el("time-filter").style.display = hasTimes ? "" : "none";
  el("filter-note").textContent = hasTimes
    ? ""
    : "No usable date/time values were found, so time filtering is off.";
  if (!hasTimes) return;
  el("filter-from").value = toLocalInputValue(times[0]);
  el("filter-to").value = toLocalInputValue(times[times.length - 1]);
}

function toLocalInputValue(epochMs) {
  const date = new Date(epochMs);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    date.getFullYear() +
    "-" + pad(date.getMonth() + 1) +
    "-" + pad(date.getDate()) +
    "T" + pad(date.getHours()) +
    ":" + pad(date.getMinutes()) +
    ":" + pad(date.getSeconds())
  );
}

function applyTimeFilter() {
  if (!lastResult) return;
  const fromValue = el("filter-from").value;
  const toValue = el("filter-to").value;
  const from = fromValue ? new Date(fromValue).getTime() : null;
  const to = toValue ? new Date(toValue).getTime() : null;
  const all = lastResult.geojson.features;
  const kept = all.filter((feature) => {
    const time = featureTime(feature);
    if (time === null) return false;
    if (from !== null && time < from) return false;
    if (to !== null && time > to) return false;
    return true;
  });
  renderMap({ type: "FeatureCollection", features: kept });
  const skippedNoTime = all.filter((f) => featureTime(f) === null).length;
  let note =
    "Showing " + kept.length + " of " + all.length + " points in this time window.";
  if (skippedNoTime) {
    note += " " + skippedNoTime + " points have no time and are hidden while filtering.";
  }
  el("filter-note").textContent = note;
}

function clearTimeFilter() {
  if (!lastResult) return;
  initTimeFilter(lastResult.geojson);
  renderMap(lastResult.geojson);
  el("filter-note").textContent =
    "Showing all " + lastResult.geojson.features.length + " points.";
}

function wireTimeFilter() {
  el("filter-apply").addEventListener("click", applyTimeFilter);
  el("filter-clear").addEventListener("click", clearTimeFilter);
}

function download(filename, text, mime) {
  const blob = new Blob([text], { type: mime });
  triggerBlobDownload(filename, blob);
}

function downloadBase64(filename, base64Data, mime) {
  const bytes = Uint8Array.from(atob(base64Data), (c) => c.charCodeAt(0));
  triggerBlobDownload(filename, new Blob([bytes], { type: mime }));
}

function triggerBlobDownload(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function baseName() {
  const summary = lastResult && lastResult.summary;
  const name = summary ? summary.source_file.filename : "records";
  return name.replace(/\.[^.]+$/, "");
}

async function processFormData(formData) {
  setStatus("Processing… the software is doing the hard part.");
  el("process-btn").disabled = true;
  try {
    const response = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Processing failed.");
    }
    lastResult = data;
    el("results-card").classList.remove("hidden");
    el("training-banner").classList.toggle(
      "hidden",
      !data.summary.training_mode
    );
    el("plain-summary").textContent = data.summary.plain_english;
    renderStats(data.summary);
    renderWarnings(data.summary);
    initTimeFilter(data.geojson);
    renderMap(data.geojson);
    if (focusGroup) focusGroup.clearLayers();
    setStatus("Done. Review your map and download your outputs below.");
    el("results-card").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    el("process-btn").disabled = false;
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  const fileInput = el("file-input");
  if (!fileInput.files.length) {
    setStatus("Please choose a file first.", true);
    return;
  }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("display_timezone", el("tz-select").value);
  const caseId = el("case-select").value;
  if (caseId) {
    formData.append("case_id", caseId);
  }
  if (!el("mapping-fieldset").classList.contains("hidden")) {
    formData.append("latitude_column", el("map-latitude").value);
    formData.append("longitude_column", el("map-longitude").value);
    formData.append("timestamp_column", el("map-timestamp").value);
    formData.append("accuracy_column", el("map-accuracy").value);
  }
  await processFormData(formData);
}

async function startTraining() {
  try {
    const response = await fetch("/api/training/sample");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load the practice file.");
    }
    const formData = new FormData();
    formData.append(
      "file",
      new Blob([data.csv], { type: "text/csv" }),
      data.filename
    );
    formData.append("display_timezone", el("tz-select").value);
    formData.append("training", "true");
    await processFormData(formData);
  } catch (err) {
    setStatus(err.message, true);
  }
}

function wireDownloads() {
  el("dl-csv").addEventListener("click", () => {
    if (!lastResult) return;
    download(baseName() + "_cleaned.csv", lastResult.cleaned_csv, "text/csv");
  });
  el("dl-json").addEventListener("click", () => {
    if (!lastResult) return;
    download(
      baseName() + "_summary.json",
      lastResult.summary_json,
      "application/json"
    );
  });
  el("dl-geojson").addEventListener("click", () => {
    if (!lastResult) return;
    download(
      baseName() + "_points.geojson",
      JSON.stringify(lastResult.geojson, null, 2),
      "application/geo+json"
    );
  });
  el("dl-kml").addEventListener("click", () => {
    if (!lastResult) return;
    download(
      baseName() + ".kml",
      lastResult.kml,
      "application/vnd.google-earth.kml+xml"
    );
  });
  el("dl-pdf").addEventListener("click", () => {
    if (!lastResult) return;
    downloadBase64(
      baseName() + "_report.pdf",
      lastResult.report_pdf_base64,
      "application/pdf"
    );
  });
}

function appendChat(role, text, extra) {
  const log = el("chat-log");
  const item = document.createElement("div");
  item.className = "chat-msg " + role;
  const body = document.createElement("div");
  body.className = "bubble";
  body.textContent = text;
  item.appendChild(body);
  if (extra) {
    const note = document.createElement("div");
    note.className = "chat-note";
    note.textContent = extra;
    item.appendChild(note);
  }
  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
  return body;
}

async function askAssistant(question) {
  if (!question) return;
  if (!assistantAvailable) {
    appendChat(
      "assistant",
      "The AI assistant is a Pro feature. Upgrade your plan to ask questions."
    );
    return;
  }
  if (!lastResult) {
    appendChat("assistant", "Process a file first, then ask me about it.");
    return;
  }
  appendChat("user", question);
  const pending = appendChat("assistant", "Thinking…");
  el("assistant-send").disabled = true;
  try {
    const response = await fetch("/api/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        summary: lastResult.summary,
        geojson: lastResult.geojson,
      }),
    });
    const data = await response.json();
    if (response.status === 402) {
      applyAssistantLock(data);
      pending.textContent =
        data.detail || "The AI assistant is a Pro feature.";
      pending.parentElement.classList.add("error");
      return;
    }
    if (!response.ok) {
      throw new Error(data.detail || "The assistant could not answer.");
    }
    pending.textContent = data.answer;
    const parent = pending.parentElement;
    if (data.tools_used && data.tools_used.length) {
      const tools = document.createElement("div");
      tools.className = "chat-note";
      tools.textContent =
        "✦ Tools used: " + data.tools_used.join(", ").replace(/_/g, " ");
      parent.appendChild(tools);
    }
    const note = document.createElement("div");
    note.className = "chat-note";
    note.textContent = data.disclaimer;
    parent.appendChild(note);
    showFocusPoints(data.focus_points);
  } catch (err) {
    pending.textContent = err.message;
    pending.parentElement.classList.add("error");
  } finally {
    el("assistant-send").disabled = !assistantAvailable;
  }
}

function setAssistantPanel(open) {
  document.body.classList.toggle("assistant-open", open);
  try {
    localStorage.setItem(PANEL_KEY, open ? "1" : "0");
  } catch (err) {
    /* storage may be unavailable */
  }
  if (open) {
    el("assistant-input").focus();
  }
  // The map needs to re-measure after the layout shift.
  if (map) {
    setTimeout(() => map.invalidateSize(), 320);
  }
}

function wireAssistant() {
  el("assistant-toggle").addEventListener("click", () =>
    setAssistantPanel(!document.body.classList.contains("assistant-open"))
  );
  el("assistant-close").addEventListener("click", () =>
    setAssistantPanel(false)
  );
  try {
    if (localStorage.getItem(PANEL_KEY) === "1") {
      setAssistantPanel(true);
    }
  } catch (err) {
    /* storage may be unavailable */
  }
  el("assistant-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = el("assistant-input");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    askAssistant(question);
  });
  el("assistant-suggestions").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-q]");
    if (!button) return;
    askAssistant(button.getAttribute("data-q"));
  });
}

function applyAssistantLock(info) {
  assistantAvailable = false;
  const upsell = el("assistant-upsell");
  const text = el("assistant-upsell-text");
  const cta = el("assistant-upsell-cta");
  if (text) {
    text.textContent =
      (info && info.detail) ||
      "The AI assistant is a Pro feature. Upgrade to unlock it.";
  }
  if (cta && info && info.required_plan) {
    cta.textContent =
      "Upgrade to " +
      info.required_plan.name +
      " (" +
      info.required_plan.price_display +
      ")";
  }
  if (upsell) upsell.classList.remove("hidden");
  const mode = el("assistant-mode");
  if (mode) mode.classList.add("hidden");
  el("assistant-send").disabled = true;
  el("assistant-input").disabled = true;
  el("assistant-input").placeholder = "Upgrade to Pro to ask questions…";
}

function renderPlans(data) {
  const grid = el("plan-grid");
  if (!grid || !data || !data.plans) return;
  billingEnabled = Boolean(data.billing_enabled);
  grid.innerHTML = data.plans
    .map((plan) => {
      const badge = plan.current
        ? '<span class="plan-badge">Current plan</span>'
        : "";
      const items = (plan.highlights || [])
        .map((h) => `<li>${escapeHtml(h)}</li>`)
        .join("");
      let action = "";
      if (plan.current) {
        action = '<button class="secondary" disabled>Current plan</button>';
      } else if (billingEnabled) {
        action =
          `<button class="primary plan-cta" data-plan="${escapeHtml(plan.id)}">` +
          `Subscribe — ${escapeHtml(plan.price_display)}</button>`;
      } else {
        action =
          '<button class="secondary" disabled title="Billing is not ' +
          'configured on this server">Subscribe</button>';
      }
      return (
        `<div class="plan${plan.current ? " current" : ""}">` +
        `<div class="plan-head"><h3>${escapeHtml(plan.name)}</h3>${badge}</div>` +
        `<p class="plan-price">${escapeHtml(plan.price_display)}</p>` +
        `<p class="plan-tagline">${escapeHtml(plan.tagline)}</p>` +
        `<ul class="plan-features">${items}</ul>` +
        `<div class="plan-action">${action}</div>` +
        `</div>`
      );
    })
    .join("");
}

async function startCheckout(planId) {
  if (!planId) return;
  try {
    const response = await fetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: planId }),
    });
    const data = await response.json();
    if (!response.ok || !data.url) {
      throw new Error(data.detail || "Could not start checkout.");
    }
    window.location.assign(data.url);
  } catch (err) {
    setStatus(err.message, true);
  }
}

function wirePlans() {
  const grid = el("plan-grid");
  if (!grid) return;
  grid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-plan]");
    if (!button) return;
    startCheckout(button.getAttribute("data-plan"));
  });
}

async function loadPlans() {
  try {
    const response = await fetch("/api/plans");
    if (!response.ok) return;
    renderPlans(await response.json());
  } catch (err) {
    /* pricing is best-effort */
  }
}

async function refreshAssistantMode() {
  try {
    const response = await fetch("/api/assistant/status");
    const data = await response.json();
    if (response.status === 402) {
      applyAssistantLock(data);
      return;
    }
    if (!response.ok) return;
    assistantAvailable = true;
    const note = el("assistant-mode");
    if (data.enabled) {
      note.textContent =
        "AI model (" + data.model + ") is configured. An aggregate summary " +
        "of this data may be sent to OpenRouter to answer your questions.";
    } else {
      note.textContent =
        "Running locally — your data stays on this computer. Set " +
        "OPENROUTER_API_KEY to enable the AI model.";
    }
  } catch (err) {
    /* status is best-effort */
  }
}

const CONFIDENCE_LABELS = {
  high: "(looks right)",
  medium: "(probably right — please check)",
  low: "(not sure — please check)",
  unknown: "(not found — pick one if it exists)",
};

function fillMappingSelect(id, columns, selected) {
  const select = el(id);
  const options = ['<option value="">Not in this file</option>'].concat(
    columns.map(
      (c) =>
        `<option value="${escapeHtml(c)}"${
          c === selected ? " selected" : ""
        }>${escapeHtml(c)}</option>`
    )
  );
  select.innerHTML = options.join("");
}

async function detectColumns() {
  const fileInput = el("file-input");
  if (!fileInput.files.length) return;
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  setStatus("Looking at your file…");
  try {
    const response = await fetch("/api/detect", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not read the file.");
    }
    const mapping = data.detection.mapping;
    const confidence = data.detection.confidence;
    fillMappingSelect("map-latitude", data.columns, mapping.latitude);
    fillMappingSelect("map-longitude", data.columns, mapping.longitude);
    fillMappingSelect("map-timestamp", data.columns, mapping.timestamp);
    fillMappingSelect("map-accuracy", data.columns, mapping.accuracy);
    for (const field of ["latitude", "longitude", "timestamp", "accuracy"]) {
      el("conf-" + field).textContent =
        CONFIDENCE_LABELS[confidence[field]] || "";
    }
    el("mapping-fieldset").classList.remove("hidden");
    setStatus(
      "I found " +
        data.row_count +
        " rows. Check the detected columns below, then process the file."
    );
  } catch (err) {
    el("mapping-fieldset").classList.add("hidden");
    setStatus(err.message, true);
  }
}

async function loadCases(selectId) {
  try {
    const response = await fetch("/api/cases");
    if (!response.ok) return;
    const data = await response.json();
    const select = el("case-select");
    const current = selectId != null ? String(selectId) : select.value;
    select.innerHTML =
      '<option value="">No case — just process the file</option>' +
      data.cases
        .map(
          (c) =>
            `<option value="${c.case_id}">[${c.case_id}] ${escapeHtml(
              c.case_number
            )}${c.investigator ? " — " + escapeHtml(c.investigator) : ""}` +
            "</option>"
        )
        .join("");
    if (current) select.value = current;
  } catch (err) {
    /* case list is best-effort */
  }
}

async function createCase() {
  const input = el("new-case-number");
  const caseNumber = input.value.trim();
  if (!caseNumber) {
    setStatus("Enter a case number first.", true);
    return;
  }
  try {
    const response = await fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_number: caseNumber }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not create the case.");
    }
    input.value = "";
    await loadCases(data.case_id);
    setStatus("Created case " + data.case_number + ".");
  } catch (err) {
    setStatus(err.message, true);
  }
}

function updateDropzone() {
  const dz = el("dropzone");
  const fileInput = el("file-input");
  const label = el("dz-file");
  const hasFile = fileInput.files.length > 0;
  dz.classList.toggle("has-file", hasFile);
  label.textContent = hasFile ? "▸ " + fileInput.files[0].name : "";
}

function wireDropzone() {
  const dz = el("dropzone");
  const fileInput = el("file-input");
  ["dragenter", "dragover"].forEach((name) =>
    dz.addEventListener(name, (event) => {
      event.preventDefault();
      dz.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    dz.addEventListener(name, (event) => {
      event.preventDefault();
      dz.classList.remove("dragover");
    })
  );
  dz.addEventListener("drop", (event) => {
    if (!event.dataTransfer || !event.dataTransfer.files.length) return;
    fileInput.files = event.dataTransfer.files;
    updateDropzone();
    detectColumns();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  el("theme-toggle").addEventListener("click", () =>
    applyTheme(currentTheme() === "light" ? "dark" : "light")
  );
  el("upload-form").addEventListener("submit", handleSubmit);
  el("file-input").addEventListener("change", () => {
    updateDropzone();
    detectColumns();
  });
  wireDropzone();
  el("new-case-btn").addEventListener("click", createCase);
  el("training-btn").addEventListener("click", startTraining);
  wireDownloads();
  wireTimeFilter();
  wireBasemapSwitch();
  wireAssistant();
  wirePlans();
  loadCases();
  loadPlans();
  refreshAssistantMode();
});
