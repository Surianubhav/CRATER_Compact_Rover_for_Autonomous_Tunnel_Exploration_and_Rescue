window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.markerInfoPanel = (() => {
  const F = window.MSW_FORMAT;
  let panelEl;
  let mapWrapEl;

  function positionNear(xM, yM) {
    const svg = mapWrapEl.querySelector('svg');
    if (!svg) return;
    const pt = svg.createSVGPoint();
    pt.x = xM; pt.y = yM;
    const screenPt = pt.matrixTransform(svg.getScreenCTM());
    const wrapRect = mapWrapEl.getBoundingClientRect();
    let left = screenPt.x - wrapRect.left + 14;
    let top = screenPt.y - wrapRect.top - 10;
    left = Math.min(left, wrapRect.width - 250);
    top = Math.max(6, Math.min(top, wrapRect.height - 260));
    panelEl.style.left = `${left}px`;
    panelEl.style.top = `${top}px`;
  }

  function renderPerson(d, mission) {
    const gases = mission.telemetry.gases.map((g) => `${g.label} ${F.num(g.value, 2)}${g.unit}`).join(' \u00b7 ');
    return `
      <div class="marker-info-panel__header">
        <strong>${d.id}</strong>
        <span class="marker-info-panel__status ${d.status}">${d.status}</span>
        <button class="close-btn" id="mip-close">\u2715</button>
      </div>
      <div class="marker-info-panel__body">
        <div class="marker-info-panel__row"><span class="k">Detected</span><span class="v">${F.wallClock(new Date(d.timestamp * 1000))}</span></div>
        <div class="marker-info-panel__row"><span class="k">Position</span><span class="v">x ${F.num(d.position.x_m, 0)}m y ${F.num(d.position.y_m, 0)}m</span></div>
        <div class="marker-info-panel__row"><span class="k">Distance</span><span class="v">${F.metersLabel(d.distance_m)}</span></div>
        <div class="marker-info-panel__row"><span class="k">Confidence</span><span class="v">${Math.round(d.confidence * 100)}%</span></div>
        ${d.thumbnail_data_uri ? `<img class="marker-info-panel__thumb" src="${d.thumbnail_data_uri}" />` : ''}
        <div class="marker-info-panel__row"><span class="k">Temperature delta</span><span class="v">+${F.num(d.temperature_delta_c, 1)}\u00b0C${d.estimated_thermal ? ' (est.)' : ''}</span></div>
        <div class="marker-info-panel__row"><span class="k">Nearest node</span><span class="v">${d.nearest_node || '--'}</span></div>
        <div class="marker-info-panel__row" style="flex-direction:column;gap:2px;"><span class="k">Gas at rover</span><span class="v" style="font-size:10px;">${gases}</span></div>
      </div>
      <div class="marker-info-panel__actions">
        <button class="confirm-btn" id="mip-confirm" ${d.status === 'CONFIRMED' ? 'disabled' : ''}>Confirm</button>
        <button class="dismiss-btn" id="mip-dismiss">Dismiss</button>
        <button id="mip-voice">Open Voice Link</button>
        <button id="mip-route" ${d.status !== 'CONFIRMED' ? 'disabled' : ''}>Export Route</button>
        <button class="wide" id="mip-note">Add Note</button>
      </div>
    `;
  }

  function renderNode(n) {
    return `
      <div class="marker-info-panel__header">
        <strong>${n.id}</strong>
        <span class="marker-info-panel__status ${n.state === 'ONLINE' ? 'CONFIRMED' : n.state === 'WEAK' ? 'PENDING' : 'DISMISSED'}">${n.state}</span>
        <button class="close-btn" id="mip-close">\u2715</button>
      </div>
      <div class="marker-info-panel__body">
        <div class="marker-info-panel__row"><span class="k">Battery</span><span class="v">${F.num(n.battery_pct, 0)}%</span></div>
        <div class="marker-info-panel__row"><span class="k">RSSI</span><span class="v">${F.num(n.rssi_dbm, 0)} dBm</span></div>
        <div class="marker-info-panel__row"><span class="k">Latency</span><span class="v">${F.num(n.latency_ms, 0)} ms</span></div>
        <div class="marker-info-panel__row"><span class="k">Last heartbeat</span><span class="v">${F.num(n.last_heartbeat_age_s, 1)}s ago</span></div>
      </div>
    `;
  }

  function renderHazard(h) {
    return `
      <div class="marker-info-panel__header"><strong>${F.escapeHtml(h.label)}</strong><button class="close-btn" id="mip-close">\u2715</button></div>
      <div class="marker-info-panel__body">
        <div class="marker-info-panel__row"><span class="k">Type</span><span class="v">${h.type}</span></div>
        <div class="marker-info-panel__row"><span class="k">Position</span><span class="v">x ${F.num(h.x_m, 0)}m y ${F.num(h.y_m, 0)}m</span></div>
      </div>
    `;
  }

  function wireActions(sel, mission) {
    const closeBtn = panelEl.querySelector('#mip-close');
    if (closeBtn) closeBtn.onclick = () => window.MSW_ACTIONS.setUi({ selectedMarker: null });

    if (sel.type !== 'detection') return;
    const confirmBtn = panelEl.querySelector('#mip-confirm');
    const dismissBtn = panelEl.querySelector('#mip-dismiss');
    const voiceBtn = panelEl.querySelector('#mip-voice');
    const routeBtn = panelEl.querySelector('#mip-route');
    const noteBtn = panelEl.querySelector('#mip-note');
    if (confirmBtn) confirmBtn.onclick = () => window.MSW_API.confirmDetection(sel.id).catch((e) => console.error(e));
    if (dismissBtn) dismissBtn.onclick = () => {
      window.MSW_API.dismissDetection(sel.id).catch((e) => console.error(e));
      window.MSW_ACTIONS.setUi({ selectedMarker: null });
    };
    if (voiceBtn) voiceBtn.onclick = () => window.MSW_ACTIONS.setUi({ voiceState: 'CONNECTED', voiceConnectedSince: Date.now() });
    if (routeBtn) routeBtn.onclick = async () => {
      try {
        const route = await window.MSW_API.getRoute({ detection_id: sel.id });
        const blob = new Blob([JSON.stringify(route, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `route-${sel.id}.json`;
        document.body.appendChild(a); a.click(); a.remove();
      } catch (e) { console.error(e); }
    };
    if (noteBtn) noteBtn.onclick = () => {
      const label = window.prompt('Note for this detection:', '');
      if (label) window.MSW_API.addAnnotation({ x_m: sel.position.x_m, y_m: sel.position.y_m, label: `${sel.id}: ${label}` }).catch((e) => console.error(e));
    };
  }

  function render(state) {
    const sel = state.ui.selectedMarker;
    const m = state.mission;
    if (!sel || !m) { panelEl.classList.remove('active'); return; }

    let html = '';
    if (sel.type === 'detection') {
      const d = m.detections.find((x) => x.id === sel.id);
      if (!d) { panelEl.classList.remove('active'); return; }
      html = renderPerson(d, m);
    } else if (sel.type === 'node') {
      const n = m.nodes.find((x) => x.id === sel.id);
      if (!n) { panelEl.classList.remove('active'); return; }
      html = renderNode(n);
    } else if (sel.type === 'hazard') {
      const geo = window.MSW_STORE.getState().meta.map;
      const h = geo && geo.hazards.find((x) => x.id === sel.id);
      if (!h) { panelEl.classList.remove('active'); return; }
      html = renderHazard(h);
    } else {
      panelEl.classList.remove('active');
      return;
    }

    panelEl.innerHTML = html;
    panelEl.classList.add('active');
    wireActions(sel, m);
    if (sel.position) positionNear(sel.position.x_m, sel.position.y_m);
  }

  function mount(mapWrap, panel) {
    mapWrapEl = mapWrap;
    panelEl = panel;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
