// Tiny Redux/Zustand-style store, written dependency-free because this
// project has no bundler/npm build step for the frontend (see README for
// why: the existing repo shipped a plain HTML/CSS/JS console, and adding
// a full React+Vite toolchain to reach for Zustand would have been a much
// bigger change than the brief's "make changes only where necessary").
// Same shape as those libraries: getState / setState / subscribe.
function createStore(initialState) {
  let state = initialState;
  const listeners = new Set();

  return {
    getState() { return state; },
    setState(patch) {
      state = typeof patch === 'function' ? patch(state) : { ...state, ...patch };
      listeners.forEach((fn) => fn(state));
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

window.MSW_STORE = createStore({
  // raw last mission snapshot from backend (live or replay)
  mission: null,
  // UI-only state
  ui: {
    alertTab: 'ACTIVE',
    selectedAlertId: null,
    selectedMarker: null, // { type: 'detection'|'node'|'hazard'|'annotation', id }
    mapLayers: {
      occupancy: true, trail: true, nodesCoverage: false, gas: true,
      temperature: true, detections: true, hazards: true, annotations: true, route: true,
    },
    gasLayerKey: 'ch4_pct',
    mapZoom: 1,
    followRover: false,
    measureMode: false,
    annotateMode: false,
    pendingCommand: null, // { type, target, label }
    thermalPalette: 'white-hot',
    thermalFrozen: false,
    cameraMode: 'RGB',
    voiceState: 'IDLE', // IDLE | CONNECTED
    voiceConnectedSince: null,
    replayMode: false,
    replayTimeS: null,
    replaySpeed: 1,
    replayPlaying: false,
    devPanelOpen: false,
    reportModalOpen: false,
    thermalConnection: 'CONNECTING',
  },
  meta: {
    missionStartWallClock: Date.now(),
    map: null, // static geometry from /api/mission/map
    lastTelemetryAt: 0,
    thermalDetectionsHistory: [], // last 6 thumbnails
  },
});

window.MSW_ACTIONS = {
  setMission(snapshot) {
    window.MSW_STORE.setState((s) => ({ ...s, mission: snapshot, meta: { ...s.meta, lastTelemetryAt: Date.now() } }));
  },
  setUi(patch) {
    window.MSW_STORE.setState((s) => ({ ...s, ui: { ...s.ui, ...(typeof patch === 'function' ? patch(s.ui) : patch) } }));
  },
  setMeta(patch) {
    window.MSW_STORE.setState((s) => ({ ...s, meta: { ...s.meta, ...(typeof patch === 'function' ? patch(s.meta) : patch) } }));
  },
};
