/* =========================================================
   MINEGUARD — dashboard logic (frontend-only prototype)

   This file is intentionally split into clearly named
   functions so a real backend/hardware layer can later
   call into this UI without any redesign:

     updateSensorData(data)
     runThermalDetection()
     updateThermalResult(result)
     updateMeshNetwork(data)
     updateRoverMap(data)      -- placeholder, no map yet
     triggerMotionlessAlert(data)
     addEvent(message, type)

   Everything else in this file is demo/mock wiring that
   feeds those functions with sample data.
   ========================================================= */

/* ---------------------------------------------------------
   1. DASHBOARD DATA
   Populated at startup by loadDashboardData() in pipeline.js,
   which reads the JSON files in /data (falling back to
   embedded demo data if they can't be fetched).
   TODO: once a backend exists, this is where live data lands —
   sensorData/meshData/GAS_THRESHOLDS/THERMAL_SAMPLES get
   reassigned from API/WebSocket responses instead of JSON files.
   --------------------------------------------------------- */
let sensorData = null;
let meshData = null;
let GAS_THRESHOLDS = null;
let THERMAL_SAMPLES = null;

let demoModeOn = false;
let demoInterval = null;
let uploadedImage = null; // { file, width, height }

/* ---------------------------------------------------------
   INIT
   --------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadDashboardData();

  sensorData = data.sensor;
  meshData = data.mesh;
  GAS_THRESHOLDS = data.thresholds;
  THERMAL_SAMPLES = data.thermalSamples;

  updateSensorData(sensorData);
  updateMeshNetwork(meshData);
  updateRoverMap(null);
  setupThermalUpload();
  setupMonitorDemo();
  setupDemoModeToggle();
  setupAlertDismiss();

  data.eventsSeed.forEach((e) => addEvent(e.message, e.type));
});

/* ===========================================================
   updateSensorData(data)
   Renders gas + environment readings from a plain data object.
   This is the single entry point the future backend should call.
   =========================================================== */
function updateSensorData(data) {
  sensorData = data;

  renderGasReading("mq4", data.mq4);
  renderGasReading("mq7", data.mq7);

  setText("env-temp", data.temp.toFixed(2));
  setText("env-hum", data.hum.toFixed(2));
  setText("env-pressure", Math.round(data.pressure));
  setText("env-alt", data.alt.toFixed(2));

  const bmpDot = document.getElementById("bmp-dot");
  const bmpText = document.getElementById("env-bmp");
  if (data.bmp_ok) {
    bmpDot.className = "status-dot status-ok";
    bmpText.textContent = "Sensor OK";
  } else {
    bmpDot.className = "status-dot status-critical";
    bmpText.textContent = "Sensor error";
  }
}

function renderGasReading(key, value) {
  const thresholds = GAS_THRESHOLDS[key];
  const status = getGasStatus(value, thresholds);

  setText(key + "-value", value);

  const badge = document.getElementById(key + "-status");
  badge.textContent = status.label;
  badge.className = "badge " + status.badgeClass;

  const bar = document.getElementById(key + "-bar");
  const pct = Math.min(100, Math.round((value / thresholds.critical) * 100));
  bar.style.width = pct + "%";
  bar.style.background = status.barColor;
}

function getGasStatus(value, thresholds) {
  if (value >= thresholds.critical) {
    return { label: "Critical", badgeClass: "badge-critical", barColor: "var(--red)" };
  }
  if (value >= thresholds.warning) {
    return { label: "Warning", badgeClass: "badge-warn", barColor: "var(--yellow)" };
  }
  return { label: "Normal", badgeClass: "badge-ok", barColor: "var(--olive)" };
}

/* ===========================================================
   updateRoverMap(data)
   Placeholder only. Later, a real mapping module should
   render into #rover-map instead of calling this function.
   =========================================================== */
function updateRoverMap(data) {
  // TODO: Replace the #rover-map placeholder contents with a
  // real canvas-based map (rover path, hotspots, warning zones)
  // once the navigation module is ready. Intentionally left
  // as a no-op for the frontend-only prototype.
  return;
}

/* ===========================================================
   Thermal upload + mock detection
   =========================================================== */
function setupThermalUpload() {
  const dropzone = document.getElementById("thermal-dropzone");
  const fileInput = document.getElementById("thermal-file-input");
  const runBtn = document.getElementById("run-detection-btn");
  const clearBtn = document.getElementById("clear-image-btn");

  dropzone.addEventListener("click", () => {
    if (!uploadedImage) fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) handleThermalFile(e.target.files[0]);
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleThermalFile(e.dataTransfer.files[0]);
    }
  });

  runBtn.addEventListener("click", runThermalDetection);
  clearBtn.addEventListener("click", clearThermalImage);
}

function handleThermalFile(file) {
  if (!file.type.startsWith("image/")) return;

  const url = URL.createObjectURL(file);
  const img = document.getElementById("thermal-image");
  img.src = url;

  img.onload = () => {
    uploadedImage = { file, width: img.naturalWidth, height: img.naturalHeight };
    setText("thermal-filename", file.name);
    setText("thermal-dimensions", img.naturalWidth + " × " + img.naturalHeight + " px");

    document.getElementById("upload-prompt").classList.add("is-hidden");
    document.getElementById("thermal-preview").classList.remove("is-hidden");
    document.getElementById("bbox-overlay").classList.add("is-hidden");
    document.getElementById("thermal-result").classList.add("is-hidden");

    document.getElementById("run-detection-btn").disabled = false;
    document.getElementById("clear-image-btn").disabled = false;

    setStatus("thermal", "Image loaded", "status-ok");
    addEvent("Thermal image uploaded: " + file.name, "info");
  };
}

function clearThermalImage() {
  uploadedImage = null;
  const img = document.getElementById("thermal-image");
  img.src = "";

  document.getElementById("thermal-preview").classList.add("is-hidden");
  document.getElementById("upload-prompt").classList.remove("is-hidden");
  document.getElementById("thermal-result").classList.add("is-hidden");
  document.getElementById("bbox-overlay").classList.add("is-hidden");

  document.getElementById("run-detection-btn").disabled = true;
  document.getElementById("clear-image-btn").disabled = true;

  document.getElementById("thermal-file-input").value = "";
  setStatus("thermal", "Awaiting feed", "status-warn");
}

/* ===========================================================
   runThermalDetection()
   MOCK detection only — picks one of the sample results loaded
   from data/thermal-samples.json, which is shaped exactly like
   what the real model is expected to return. Later this should
   be replaced with a real call, e.g.:
     const result = await fetch('/api/thermal-detection', { method: 'POST', body: imageData });
     updateThermalResult(await result.json());
   =========================================================== */
async function runThermalDetection() {
  if (!uploadedImage || !uploadedImage.file) return;

  const runBtn = document.getElementById("run-detection-btn");
  runBtn.disabled = true;
  runBtn.textContent = "Processing...";

  addEvent("Sending image to thermal detection model...", "info");

  const formData = new FormData();
  formData.append("file", uploadedImage.file);

  try {
    const response = await fetch("http://127.0.0.1:8000/api/detect-thermal", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const result = await response.json();
    updateThermalResult(result);
  } catch (err) {
    console.error("Detection failed:", err);
    addEvent("Detection request failed. Is the API server running?", "critical");
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run Detection";
  }
}

/* ===========================================================
   updateThermalResult(result)
   Renders a detection result object shaped like:
     { detected, confidence, bbox: [x1,y1,x2,y2] (% coords), person_id }
   This is the entry point the future real model output
   should be passed into.
   =========================================================== */
function updateThermalResult(result) {
  const box = document.getElementById("thermal-result");
  const imgElement = document.getElementById("thermal-image");
  const overlay = document.getElementById("bbox-overlay");
  
  // Hide standard CSS box overlay since YOLO draws bounding boxes directly on image
  overlay.classList.add("is-hidden");

  // Update preview image with annotated image output containing bounding boxes
  if (result.image_data) {
    imgElement.src = result.image_data;
  }

  const confidencePct = Math.round((result.confidence || 0) * 100);

  if (result.detected) {
    box.className = "thermal-result result-detected";
    box.innerHTML = `
      <p class="result-title">Human Detected (${result.count})</p>
      <div class="result-row"><span>Top Confidence</span><span>${confidencePct}%</span></div>
      <div class="result-row"><span>Status</span><span>Active target highlighted</span></div>
      <span class="result-flag">LIVE INFERENCE OUTPUT</span>
    `;

    setStatus("thermal", "Person detected", "status-warn");
    addEvent(`Thermal detection: ${result.count} human(s) detected (${confidencePct}% confidence)`, "warn");
  } else {
    box.className = "thermal-result result-none";
    box.innerHTML = `
      <p class="result-title">No human detected</p>
      <div class="result-row"><span>Confidence</span><span>${confidencePct}%</span></div>
      <span class="result-flag">LIVE INFERENCE OUTPUT</span>
    `;
    setStatus("thermal", "No detection", "status-ok");
    addEvent("Thermal detection: no human detected in image", "info");
  }

  box.classList.remove("is-hidden");
}

/* ===========================================================
   Motionless person monitoring (demo control)
   =========================================================== */
function setupMonitorDemo() {
  document.getElementById("simulate-alert-btn").addEventListener("click", () => {
    triggerMotionlessAlert({
      personId: "01",
      motionlessSeconds: 134,
      confidence: 0.91
    });
  });
}

/* ===========================================================
   triggerMotionlessAlert(data)
   data: { personId, motionlessSeconds, confidence }
   Later the real tracking backend should call this with live
   values instead of the demo button doing it.
   =========================================================== */
function triggerMotionlessAlert(data) {
  const minutes = Math.floor(data.motionlessSeconds / 60);
  const seconds = data.motionlessSeconds % 60;
  const durationText = pad(minutes) + ":" + pad(seconds);
  const confidencePct = Math.round(data.confidence * 100);

  setText("monitor-id", data.personId);
  setText("monitor-detection", "Possible motionless person — check required");
  setText("monitor-movement", "No movement detected");
  setText("monitor-duration", durationText);

  const badge = document.getElementById("monitor-status-badge");
  badge.textContent = "Check required";
  badge.className = "badge badge-critical";
  document.querySelector(".monitor-panel").classList.add("is-alert");

  showAlertBanner(
    "Possible motionless person",
    "Person ID " + data.personId + " · Motionless " + durationText +
    " · Confidence " + confidencePct + "% · Check required"
  );

  addEvent("⚠ Possible motionless person detected — ID " + data.personId, "critical");
}

function showAlertBanner(title, detail) {
  document.getElementById("alert-title").textContent = title;
  document.getElementById("alert-detail").textContent = detail;
  document.getElementById("alert-banner").classList.remove("is-hidden");
}

function setupAlertDismiss() {
  document.getElementById("alert-dismiss-btn").addEventListener("click", () => {
    document.getElementById("alert-banner").classList.add("is-hidden");
  });
}

/* ===========================================================
   updateMeshNetwork(data)
   data shape (future backend):
     { nodes: [{id, status}], route: [ids...], hops }
   For the demo this renders from the local meshData object.
   =========================================================== */
function updateMeshNetwork(data) {
  setText("mesh-active-nodes", data.activeNodes);
  setText("mesh-hops", data.hops);
  setText("mesh-route-text", data.route.join(" → ").replace("ROVER", "Rover"));

  const pathEl = document.getElementById("mesh-path");
  pathEl.innerHTML = "";

  data.route.forEach((nodeId, index) => {
    const node = data.nodes[nodeId];

    const btn = document.createElement("button");
    btn.className = "mesh-node " + (node.status === "online" ? "is-active" : "is-idle");
    btn.setAttribute("aria-label", nodeId + " details");
    btn.innerHTML = `
      <span class="mesh-node-box">${nodeId}</span>
      <span class="mesh-node-dot">${node.status === "online" ? "✓" : "…"}</span>
    `;
    btn.addEventListener("click", () => showMeshNodeDetail(nodeId, node));
    pathEl.appendChild(btn);

    if (index < data.route.length - 1) {
      const connector = document.createElement("div");
      connector.className = "mesh-connector " + (node.status === "online" ? "is-active" : "");
      pathEl.appendChild(connector);
    }
  });

  const networkBadge = document.getElementById("mesh-network-badge");
  const allOnline = data.route.every((id) => data.nodes[id].status === "online");
  networkBadge.textContent = allOnline ? "Connected" : "Degraded";
  networkBadge.className = "badge " + (allOnline ? "badge-ok" : "badge-warn");
  setStatus("mesh", allOnline ? "Connected" : "Degraded", allOnline ? "status-ok" : "status-warn");
}

function showMeshNodeDetail(nodeId, node) {
  const detail = document.getElementById("mesh-node-detail");
  detail.classList.remove("is-hidden");
  detail.innerHTML = `
    <div class="mesh-node-detail-title">${nodeId}</div>
    <div class="mesh-node-detail-row"><span>Status</span><span>${node.status === "online" ? "Online" : "Idle / standby"}</span></div>
    <div class="mesh-node-detail-row"><span>Role</span><span>${node.role}</span></div>
    <div class="mesh-node-detail-row"><span>Last packet</span><span>${node.lastPacketSec}s ago</span></div>
    <div class="mesh-node-detail-row"><span>Packets forwarded</span><span>${node.packetsForwarded}</span></div>
    ${!node.onRoute ? '<div class="mesh-node-detail-row"><span>Note</span><span>Not on active route</span></div>' : ""}
  `;
}

/* ===========================================================
   Event log
   =========================================================== */
function addEvent(message, type) {
  const log = document.getElementById("event-log");
  const row = document.createElement("div");
  row.className = "event-row" + (type === "warn" ? " event-warn" : type === "critical" ? " event-critical" : "");
  row.innerHTML = `<span class="event-time">${nowTimestamp()}</span><span>${message}</span>`;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function nowTimestamp() {
  const d = new Date();
  return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}

/* ===========================================================
   DEMO MODE — simulates incoming system activity so the
   dashboard is demonstrable before real hardware is connected.
   =========================================================== */
function setupDemoModeToggle() {
  const btn = document.getElementById("demo-mode-btn");
  btn.addEventListener("click", () => {
    demoModeOn = !demoModeOn;
    btn.classList.toggle("is-active", demoModeOn);
    btn.setAttribute("aria-pressed", String(demoModeOn));
    setText("demo-mode-state", demoModeOn ? "On" : "Off");

    if (demoModeOn) {
      addEvent("Demo mode enabled — simulating live data", "info");
      demoInterval = setInterval(runDemoTick, 4500);
    } else {
      addEvent("Demo mode disabled", "info");
      clearInterval(demoInterval);
    }
  });
}

function runDemoTick() {
  // 1. Small realistic drift in gas + environment readings.
  const next = {
    mq4: clamp(sensorData.mq4 + randomStep(6), 40, 220),
    mq7: clamp(sensorData.mq7 + randomStep(10), 100, 340),
    temp: clamp(sensorData.temp + randomStep(0.3), 22, 30),
    hum: clamp(sensorData.hum + randomStep(1.5), 40, 75),
    pressure: sensorData.pressure + randomStep(15),
    alt: sensorData.alt + randomStep(0.4),
    bmp_ok: true
  };
  updateSensorData(next);
  addEvent("MQ-4/MQ-7 reading updated", "info");

  // 2. Occasional mesh packet event.
  const routeSample = meshData.route[Math.floor(Math.random() * (meshData.route.length - 1))];
  addEvent(routeSample + " forwarded sensor packet", "info");

  // 3. Rare mock thermal pass (only logged, no image required).
  if (Math.random() < 0.25) {
    addEvent("Thermal module processed a frame — no human in view", "info");
  }

  // 4. Rare motionless alert simulation, only if not already alerted.
  const monitorPanel = document.querySelector(".monitor-panel");
  if (Math.random() < 0.12 && !monitorPanel.classList.contains("is-alert")) {
    triggerMotionlessAlert({
      personId: "0" + (1 + Math.floor(Math.random() * 3)),
      motionlessSeconds: 60 + Math.floor(Math.random() * 180),
      confidence: 0.85 + Math.random() * 0.12
    });
  }
}

/* ---------------------------------------------------------
   Small helpers
   --------------------------------------------------------- */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setStatus(key, text, dotClass) {
  setText("status-" + key, text);
  const dot = document.getElementById("dot-" + key);
  if (dot) dot.className = "status-dot " + dotClass;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function randomStep(magnitude) {
  return (Math.random() * 2 - 1) * magnitude;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}