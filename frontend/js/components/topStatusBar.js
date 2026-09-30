window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.topStatusBar = (() => {
  const F = window.MSW_FORMAT;
  let root;

  function render(state) {
    const m = state.mission;
    if (!m) return;
    const ui = state.ui;
    const linkStatus = (ui.replayMode ? 'REPLAY' : m.link.status).toUpperCase();

    let linkText;
    let linkClass;
    if (ui.replayMode) {
      linkText = `REPLAY \u00b7 ${F.missionTimer(ui.replayTimeS || 0)}`;
      linkClass = 'state-degraded';
    } else if (m.link.status === 'NOMINAL') {
      linkText = `LINK NOMINAL \u00b7 ${m.link.hops} hops \u00b7 ${Math.round(m.link.latency_ms)} ms`;
      linkClass = 'state-nominal';
    } else if (m.link.status === 'DEGRADED') {
      linkText = `LINK DEGRADED \u00b7 ${m.link.hops} hops \u00b7 ${Math.round(m.link.latency_ms)} ms`;
      linkClass = 'state-degraded';
    } else {
      linkText = `LINK LOST \u00b7 0 hops \u00b7 -- ms`;
      linkClass = 'state-lost';
    }
    const glyph = m.link.status === 'NOMINAL' ? '\u25CF' : m.link.status === 'DEGRADED' ? '\u25D0' : '\u25CB';

    const source = ui.replayMode ? 'REPLAY' : m.source;

    root.innerHTML = `
      <div class="top-bar__brand">
        <span class="name">MINESWEEPER</span>
        <span class="mission">${m.mission_id} \u00b7 ${F.escapeHtml(window.MSW_CONFIG.MISSION_LOCATION || 'Level 2, East Gallery')}</span>
      </div>
      <div class="top-bar__link ${linkClass}" title="${F.escapeHtml(m.link.unreachable_beyond ? `Unreachable beyond ${m.link.unreachable_beyond}` : '')}">
        <span class="glyph">${glyph}</span><span>${linkText}</span>
      </div>
      <div></div>
      <div class="top-bar__field">
        <span class="label">Mission Timer</span>
        <span class="value">${F.missionTimer(m.mission_time_s)}</span>
      </div>
      <div class="top-bar__field">
        <span class="label">Control State: ${m.rover.control_state}</span>
        <span class="value small">
          <span class="mono">${m.rover.control_state}</span>
          &nbsp;batt ${F.num(m.rover.battery_pct, 0)}%
          &nbsp;${F.metersLabel(m.rover.distance_from_entry_m)} from entry
          &nbsp;${F.metersLabel(m.rover.path_travelled_m)} travelled
        </span>
      </div>
      <div class="top-bar__field">
        <span class="label">Source</span>
        <span class="badge-source ${source}">${source}</span>
      </div>
      <div class="top-bar__field">
        <span class="label">Wall-clock time</span>
        <span class="value">${F.wallClock()}</span>
      </div>
      <button class="btn-report" id="btn-generate-report">Generate Report</button>
    `;

    root.querySelector('#btn-generate-report').onclick = () => window.MSW_ACTIONS.setUi({ reportModalOpen: true });
  }

  function mount(el) {
    root = el;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
    setInterval(() => render(window.MSW_STORE.getState()), 1000); // keep wall clock ticking even between snapshots
  }

  return { mount };
})();
