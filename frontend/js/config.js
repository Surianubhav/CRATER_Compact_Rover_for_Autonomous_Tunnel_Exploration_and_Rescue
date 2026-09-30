// Central frontend configuration. Single place to change if the backend
// runs on a different host/port during development.
window.MSW_CONFIG = {
  API_BASE: window.location.origin.includes('file://') ? 'http://127.0.0.1:8000' : '',
  WS_BASE: (() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (window.location.origin.includes('file://')) return 'ws://127.0.0.1:8000';
    return `${proto}//${window.location.host}`;
  })(),
  ALERT_TIER_LABEL: {
    1: 'COMMUNICATIONS', 2: 'HUMAN DETECTION', 3: 'ATMOSPHERE',
    4: 'THERMAL', 5: 'ROVER SYSTEM', 6: 'INFORMATION',
  },
  ALERT_TIER_GLYPH: {
    1: '\u25B3', 2: '\u25C9', 3: '\u2248', 4: '\u25B2', 5: '\u2699', 6: '\u2139',
  },
  NODE_CHAIN: ['N1', 'N2', 'N3', 'N4', 'N5'],
  MAP_VIEWBOX: { minX: -30, minY: -20, w: 340, h: 200 },
};
