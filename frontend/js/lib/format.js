window.MSW_FORMAT = {
  missionTimer(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return hh > 0 ? `${pad(hh)}:${pad(mm)}:${pad(ss)}` : `${pad(mm)}:${pad(ss)}`;
  },
  missionClock(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    const hh = Math.floor(s / 3600) % 24;
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
  },
  wallClock(date = new Date()) {
    return date.toLocaleTimeString([], { hour12: false });
  },
  num(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return Number(value).toFixed(digits);
  },
  metersLabel(m) {
    if (m === null || m === undefined) return '-- m';
    return `${Math.round(m)} m`;
  },
  trendArrow(trendPerMin) {
    if (trendPerMin > 0.01) return '\u2191';
    if (trendPerMin < -0.01) return '\u2193';
    return '\u2192';
  },
  pct(value) {
    if (value === null || value === undefined) return '--%';
    return `${Math.round(value * 100)}%`;
  },
  escapeHtml(str) {
    return String(str ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  },
};
