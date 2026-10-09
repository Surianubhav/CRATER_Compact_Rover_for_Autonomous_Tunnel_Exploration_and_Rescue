// Reusable staleness logic (product brief section 22): every panel
// should compute "how old is this data" the SAME way. Thresholds pulled
// from the backend's thresholds.json at startup, with a sane fallback.
window.MSW_DATA_AGE = {
  thresholds: { caution: 5, danger: 30 },

  classify(ageSeconds) {
    if (ageSeconds === null || ageSeconds === undefined) return 'stale';
    if (ageSeconds > this.thresholds.danger) return 'stale';
    if (ageSeconds > this.thresholds.caution) return 'caution';
    return 'fresh';
  },

  label(ageSeconds) {
    if (ageSeconds === null || ageSeconds === undefined) return 'age --';
    return `age ${ageSeconds.toFixed(1)}s`;
  },

  // Renders a small <span class="data-age ..."> element as an HTML string.
  render(ageSeconds) {
    const cls = this.classify(ageSeconds);
    return `<span class="data-age ${cls}">${this.label(ageSeconds)}</span>`;
  },

  // Applies/removes the reusable `.stale` visual treatment (dim + hatch)
  // on an arbitrary panel element based on age.
  applyStaleClass(el, ageSeconds) {
    if (!el) return;
    const cls = this.classify(ageSeconds);
    el.classList.toggle('stale', cls === 'stale');
  },
};
