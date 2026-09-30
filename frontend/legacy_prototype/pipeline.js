/* =========================================================
   MINEGUARD — data pipeline

   This is the seam between "where the data comes from" and
   "how the dashboard renders it." Right now it loads the JSON
   files in /data. Later, swap the fetch() calls below for real
   API or WebSocket calls — script.js's render functions
   (updateSensorData, updateMeshNetwork, etc.) don't need to
   change at all.
   ========================================================= */

// Embedded fallback copies of the same data. These are only used
// if fetch() fails — which happens if index.html is opened
// directly as a file:// URL, since browsers block fetch() of
// local files for security reasons. Serving the folder with a
// tiny local server (see README) avoids this and loads the real
// JSON files instead.
const FALLBACK_DATA = {
  sensor: { mq4: 88, mq7: 228, temp: 25.70, hum: 57.60, pressure: 97627.0, alt: 312.88, bmp_ok: true },

  mesh: {
    route: ["ESP-01", "ESP-03", "ESP-05", "ROVER"],
    hops: 3,
    activeNodes: 5,
    nodes: {
      "ESP-01": { status: "online", role: "Sensor node", packetsForwarded: 342, lastPacketSec: 1, onRoute: true },
      "ESP-02": { status: "idle", role: "Standby relay", packetsForwarded: 54, lastPacketSec: 41, onRoute: false },
      "ESP-03": { status: "online", role: "Relay", packetsForwarded: 128, lastPacketSec: 2, onRoute: true },
      "ESP-04": { status: "idle", role: "Standby relay", packetsForwarded: 37, lastPacketSec: 58, onRoute: false },
      "ESP-05": { status: "online", role: "Relay", packetsForwarded: 96, lastPacketSec: 2, onRoute: true },
      "ROVER": { status: "online", role: "Base receiver", packetsForwarded: 470, lastPacketSec: 1, onRoute: true }
    }
  },

  thresholds: {
    mq4: { warning: 100, critical: 180 },
    mq7: { warning: 150, critical: 300 }
  },

  thermalSamples: [
    { detected: true, confidence: 0.91, bbox: [28, 22, 61, 68], person_id: 1 },
    { detected: true, confidence: 0.87, bbox: [35, 18, 70, 75], person_id: 1 },
    { detected: true, confidence: 0.95, bbox: [22, 30, 55, 80], person_id: 1 },
    { detected: false, confidence: 0.34, bbox: null, person_id: null }
  ],

  eventsSeed: [
    { message: "Rover connected", type: "info" },
    { message: "Thermal module ready", type: "info" },
    { message: "ESP-03 forwarded sensor packet", type: "info" },
    { message: "MQ-4 reading received", type: "info" }
  ]
};

/**
 * Fetches a JSON file, falling back to embedded demo data if the
 * fetch fails (e.g. running from file:// without a local server).
 */
async function loadJSON(path, fallbackKey) {
  try {
    const res = await fetch(path);
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json();
  } catch (err) {
    console.warn(
      "MINEGUARD pipeline: couldn't load " + path + " (" + err.message + ") " +
      "— using embedded fallback data instead. Serve this folder with a local " +
      "server (see README) to load the live JSON files."
    );
    return FALLBACK_DATA[fallbackKey];
  }
}

/**
 * Loads all dashboard data files in parallel.
 * TODO: this is the function to change when a real backend exists —
 * replace the loadJSON() calls with real API/WebSocket calls that
 * return data in the same shape.
 */
async function loadDashboardData() {
  const [sensor, mesh, thresholds, thermalSamples, eventsSeed] = await Promise.all([
    loadJSON("data/sensor-data.json", "sensor"),
    loadJSON("data/mesh-data.json", "mesh"),
    loadJSON("data/thresholds.json", "thresholds"),
    loadJSON("data/thermal-samples.json", "thermalSamples"),
    loadJSON("data/events-seed.json", "eventsSeed")
  ]);

  return { sensor, mesh, thresholds, thermalSamples, eventsSeed };
}
