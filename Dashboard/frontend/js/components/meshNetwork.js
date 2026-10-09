window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.meshNetwork = (() => {
  const F = window.MSW_FORMAT;
  let root;

  function chainSvg(nodes, link) {
    const items = [{ id: 'BASE', state: 'ONLINE' }, ...nodes, { id: 'ROVER', state: link.status === 'LOST' ? 'UNREACHABLE' : 'ONLINE' }];
    const stepW = 58;
    const width = items.length * stepW;
    let svg = `<svg viewBox="0 0 ${width} 50" width="${width}" height="50">`;
    for (let i = 0; i < items.length - 1; i += 1) {
      const a = items[i]; const b = items[i + 1];
      const broken = a.state === 'LOST' || a.state === 'UNREACHABLE' || b.state === 'UNREACHABLE';
      const x1 = i * stepW + 20; const x2 = (i + 1) * stepW + 20;
      svg += `<line x1="${x1}" y1="20" x2="${x2}" y2="20" stroke="${broken ? '#5A646D' : '#6F9FB5'}"
                stroke-width="${broken ? 1 : 2}" stroke-dasharray="${broken ? '3 3' : 'none'}" />`;
    }
    items.forEach((it, i) => {
      const x = i * stepW + 20;
      const color = it.state === 'LOST' ? '#C0413B' : it.state === 'WEAK' ? '#C8952E' : it.state === 'UNREACHABLE' ? '#5A646D' : '#D5DBE0';
      svg += `<rect x="${x - 9}" y="10" width="18" height="18" fill="none" stroke="${color}" stroke-width="1.4" />`;
      svg += `<text x="${x}" y="42" fill="${color}" font-size="9" font-family="IBM Plex Mono, monospace" text-anchor="middle">${it.id}</text>`;
    });
    svg += '</svg>';
    return svg;
  }

  function render(state) {
    const m = state.mission;
    if (!m || !root) return;
    root.querySelector('.mesh-network__chain').innerHTML = chainSvg(m.nodes, m.link);

    root.querySelector('.mesh-network__table tbody').innerHTML = m.nodes.map((n) => `
      <tr>
        <td>${n.id}</td>
        <td><span class="node-state-chip ${n.state}">${n.state}</span></td>
        <td>${F.num(n.battery_pct, 0)}%</td>
        <td>${n.state === 'UNREACHABLE' ? '--' : F.num(n.rssi_dbm, 0)}</td>
        <td>${n.state === 'UNREACHABLE' ? '--' : F.num(n.latency_ms, 0)}</td>
        <td>${n.state === 'UNREACHABLE' ? '--' : `${F.num(n.last_heartbeat_age_s, 1)}s`}</td>
      </tr>
    `).join('');

    root.querySelector('.mesh-network__footer').innerHTML = `
      <span>Relays remaining: <b>${m.link.relays_total - m.link.relays_deployed}/${m.link.relays_total}</b></span>
      <span>Auto-deploy: <b>${m.link.auto_deploy_armed ? 'ARMED' : 'OFF'}</b></span>
      <span>Rover buffer: <b>${F.num(m.link.rover_buffer_s, 0)}s</b></span>
    `;
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Mesh Network</strong></div>
      <div class="mesh-network">
        <div class="mesh-network__chain"></div>
        <div class="mesh-network__table">
          <table>
            <thead><tr><th>Node</th><th>State</th><th>Batt</th><th>RSSI</th><th>Latency</th><th>Heartbeat</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="mesh-network__footer"></div>
      </div>
    `;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
