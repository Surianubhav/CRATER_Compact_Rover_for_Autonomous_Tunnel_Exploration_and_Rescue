window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.reportPreview = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let overlayEl;

  function renderReportHtml(data) {
    const detRows = (data.confirmed_detections || []).map((d) => `
      <tr><td>${d.id}</td><td>${Math.round(d.confidence * 100)}%</td><td>${F.metersLabel(d.distance_m)}</td><td>${d.nearest_node || '--'}</td></tr>
    `).join('') || '<tr><td colspan="4">None</td></tr>';

    const gasRows = Object.values(data.gas_peaks || {}).map((g) => `<tr><td>${g.label}</td><td>${g.peak} ${g.unit}</td></tr>`).join('');

    const nodeRows = (data.node_deployment_log || []).map((n) => `<tr><td>${n.id}</td><td>${n.state}</td><td>${n.battery_pct}%</td></tr>`).join('');

    const outageRows = (data.communication_outages || []).map((o) => `<tr><td>${o.clock}</td><td>${F.escapeHtml(o.message)}</td></tr>`).join('') || '<tr><td colspan="2">None recorded</td></tr>';

    const cmdRows = (data.commands || []).map((c) => `<tr><td>${c.id}</td><td>${F.escapeHtml(c.label)}</td><td>${c.status}</td></tr>`).join('') || '<tr><td colspan="3">None issued</td></tr>';

    const annRows = (data.annotations || []).map((a) => `<tr><td>${F.escapeHtml(a.label)}</td><td>x${Math.round(a.x_m)} y${Math.round(a.y_m)}</td></tr>`).join('') || '<tr><td colspan="2">None</td></tr>';

    const evRows = (data.event_log_excerpt || []).slice(0, 20).map((e) => `<tr><td>${e.clock}</td><td>${e.category}</td><td>${F.escapeHtml(e.message)}</td></tr>`).join('');

    return `
      <h1>MINESWEEPER Mission Report \u2014 ${data.mission_id}</h1>
      <div>Date: ${data.date} &nbsp;&nbsp; Operator: ${F.escapeHtml(data.operator)}</div>
      <div>Duration: ${F.missionTimer(data.duration_s)} &nbsp;&nbsp; Distance explored: ${F.metersLabel(data.distance_explored_m)} &nbsp;&nbsp; Path travelled: ${F.metersLabel(data.path_travelled_m)}</div>
      <div style="color:#666;font-size:11px;">${F.escapeHtml(data.area_mapped_note || '')}</div>

      <h2>Confirmed detections</h2>
      <table><tr><th>ID</th><th>Confidence</th><th>Distance</th><th>Nearest node</th></tr>${detRows}</table>

      <h2>Gas peaks</h2>
      <table><tr><th>Gas</th><th>Peak</th></tr>${gasRows}</table>
      <div>Maximum temperature: <b>${F.num(data.temperature_max_c, 1)}\u00b0C</b></div>

      <h2>Node deployment log</h2>
      <table><tr><th>Node</th><th>State</th><th>Battery</th></tr>${nodeRows}</table>

      <h2>Communication outages</h2>
      <table><tr><th>Time</th><th>Event</th></tr>${outageRows}</table>

      <h2>Commands</h2>
      <table><tr><th>ID</th><th>Label</th><th>Status</th></tr>${cmdRows}</table>

      <h2>Annotations</h2>
      <table><tr><th>Label</th><th>Position</th></tr>${annRows}</table>

      <h2>Event log excerpt</h2>
      <table><tr><th>Clock</th><th>Category</th><th>Event</th></tr>${evRows}</table>
    `;
  }

  async function open() {
    overlayEl.classList.add('active');
    root.querySelector('.modal-box__body').innerHTML = '<div style="padding:20px;">Building report\u2026</div>';
    try {
      const data = await window.MSW_API.getReport();
      root.querySelector('.modal-box__body').innerHTML = renderReportHtml(data);
    } catch (e) {
      root.querySelector('.modal-box__body').innerHTML = `<div style="padding:20px;color:#900;">Failed to build report: ${F.escapeHtml(e.message)}</div>`;
    }
  }

  function render(state) {
    if (state.ui.reportModalOpen) open(); else overlayEl.classList.remove('active');
  }

  function mount(el) {
    overlayEl = el;
    overlayEl.innerHTML = `
      <div class="modal-box">
        <div class="modal-box__header">
          <span class="title">Mission Report Preview</span>
          <button id="report-close">\u2715</button>
        </div>
        <div class="modal-box__body"></div>
        <div class="modal-box__footer">
          <button class="primary" id="report-export-pdf">Export PDF</button>
          <button id="report-export-json">Export Raw Data</button>
          <button id="report-print">Print</button>
        </div>
      </div>
    `;
    root = overlayEl;
    root.querySelector('#report-close').onclick = () => window.MSW_ACTIONS.setUi({ reportModalOpen: false });
    overlayEl.addEventListener('click', (e) => { if (e.target === overlayEl) window.MSW_ACTIONS.setUi({ reportModalOpen: false }); });
    root.querySelector('#report-export-pdf').onclick = () => window.open(window.MSW_API.exportReportPdfUrl(), '_blank');
    root.querySelector('#report-export-json').onclick = () => window.open(window.MSW_API.exportReportJsonUrl(), '_blank');
    root.querySelector('#report-print').onclick = () => window.print();

    window.MSW_STORE.subscribe(render);
  }

  return { mount };
})();
