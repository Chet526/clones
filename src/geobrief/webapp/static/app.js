"use strict";

// GeoBrief LE — Phase 1 front-end. Talks to the local FastAPI server, shows a
// plain-English summary, plots mappable points on a Leaflet map (with accuracy
// circles), and offers the cleaned CSV / JSON / GeoJSON as downloads.

let map = null;
let layerGroup = null;
let lastResult = null;

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
  map = L.map("map");
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  layerGroup = L.layerGroup().addTo(map);
  map.setView([20, 0], 2);
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

function renderMap(geojson) {
  ensureMap();
  layerGroup.clearLayers();
  const bounds = [];
  for (const feature of geojson.features) {
    const [lon, lat] = feature.geometry.coordinates;
    const props = feature.properties;
    const marker = L.marker([lat, lon]).bindPopup(popupHtml(props));
    layerGroup.addLayer(marker);
    if (props.accuracy_radius && props.accuracy_radius > 0) {
      layerGroup.addLayer(
        L.circle([lat, lon], {
          radius: props.accuracy_radius,
          color: "#2563eb",
          weight: 1,
          fillOpacity: 0.08,
        })
      );
    }
    bounds.push([lat, lon]);
  }
  if (bounds.length) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }
}

function download(filename, text, mime) {
  const blob = new Blob([text], { type: mime });
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
    el("plain-summary").textContent = data.summary.plain_english;
    renderStats(data.summary);
    renderWarnings(data.summary);
    renderMap(data.geojson);
    setStatus("Done. Review your map and download your outputs below.");
    el("results-card").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    el("process-btn").disabled = false;
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
}

document.addEventListener("DOMContentLoaded", () => {
  el("upload-form").addEventListener("submit", handleSubmit);
  wireDownloads();
});
