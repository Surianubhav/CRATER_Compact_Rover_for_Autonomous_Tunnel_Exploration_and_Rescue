window.MSW_API = (() => {
  const base = window.MSW_CONFIG.API_BASE;

  async function req(path, options = {}) {
    const res = await fetch(base + path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* noop */ }
      throw new Error(`${path} -> ${res.status} ${detail}`);
    }
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return res.json();
    return res.text();
  }

  return {
    getMissionState: () => req('/api/mission/state'),
    getMap: () => req('/api/mission/map'),
    getThresholds: () => req('/api/telemetry/thresholds'),
    ackAlert: (id) => req(`/api/alerts/${id}/ack`, { method: 'POST' }),
    listEvents: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return req(`/api/events${qs ? `?${qs}` : ''}`);
    },
    exportEventsCsvUrl: () => `${base}/api/events/export.csv`,
    issueCommand: (type, target) => req('/api/commands', { method: 'POST', body: JSON.stringify({ type, target }) }),
    listCommands: () => req('/api/commands'),
    confirmDetection: (id) => req(`/api/detections/${id}/confirm`, { method: 'POST' }),
    dismissDetection: (id) => req(`/api/detections/${id}/dismiss`, { method: 'POST' }),
    getRoute: (params) => {
      const qs = new URLSearchParams(params).toString();
      return req(`/api/route?${qs}`);
    },
    addAnnotation: (payload) => req('/api/annotations', { method: 'POST', body: JSON.stringify(payload) }),
    getReport: () => req('/api/report'),
    exportReportPdfUrl: () => `${base}/api/report/export.pdf`,
    exportReportJsonUrl: () => `${base}/api/report/export.json`,
    triggerScenario: (scenario) => req('/api/dev/scenario', { method: 'POST', body: JSON.stringify({ scenario }) }),
    getReplayTimeline: () => req('/api/replay/timeline'),
    getReplaySnapshot: (t) => req(`/api/replay/snapshot?t=${t}`),
    getThermalStatus: () => req('/api/thermal/status'),
    postThermalFrame: (blob) => {
      const form = new FormData();
      form.append('file', blob, 'frame.jpg');
      return fetch(base + '/api/thermal/frame', { method: 'POST', body: form }).then((r) => r.json());
    },
  };
})();
