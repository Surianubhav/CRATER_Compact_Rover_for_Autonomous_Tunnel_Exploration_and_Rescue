window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.environmentStrip = (() => {
  const F = window.MSW_FORMAT;
  let root;

  function sparkline(history, status) {
    if (!history || history.length < 2) return '';
    const w = 100; const h = 20;
    const min = Math.min(...history); const max = Math.max(...history);
    const range = max - min || 1;
    const pts = history.map((v, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const color = status === 'DANGER' ? '#C0413B' : status === 'CAUTION' ? '#C8952E' : '#8B96A0';
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.4" /></svg>`;
  }

  function tile(reading, ageSeconds) {
    const cls = window.MSW_DATA_AGE.classify(ageSeconds);
    return `
      <div class="env-tile status-${reading.status.toLowerCase()} ${cls === 'stale' ? 'stale' : ''}">
        <div class="env-tile__top">
          <span class="env-tile__label">${reading.label}</span>
          ${reading.simulated_field ? '<span class="env-tile__sim-flag">SIM</span>' : ''}
        </div>
        <div class="env-tile__value-row">
          <span class="env-tile__value">${F.num(reading.value, reading.unit === 'Pa' ? 0 : 2)}</span>
          <span class="text-secondary" style="font-size:10px;">${reading.unit}</span>
        </div>
        <div class="env-tile__status">${reading.status}</div>
        <div class="env-tile__spark">${sparkline(reading.history, reading.status)}</div>
        <div class="env-tile__meta-row">
          <span>${F.trendArrow(reading.trend_per_min)} ${F.num(Math.abs(reading.trend_per_min), 2)}/min</span>
          <span>peak ${F.num(reading.peak_value, 1)}</span>
        </div>
        ${window.MSW_DATA_AGE.render(ageSeconds)}
      </div>
    `;
  }

  function render(state) {
    const m = state.mission;
    if (!m || !root) return;
    const age = m.telemetry.age_seconds || 0;
    const all = [...m.telemetry.gases, ...m.telemetry.environment];
    root.innerHTML = all.map((r) => tile(r, age)).join('');
  }

  function mount(el) {
    root = el;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
