window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.eventLog = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let search = '';
  let category = '';
  let events = [];

  const CATEGORIES = ['COMMS', 'DETECTION', 'GAS', 'THERMAL', 'NODE', 'COMMAND', 'ANNOTATION', 'SYSTEM'];

  async function refresh() {
    try {
      const res = await window.MSW_API.listEvents({ ...(search ? { search } : {}), ...(category ? { category } : {}) });
      events = res.events;
      renderTable();
    } catch (e) { console.error('event log fetch failed', e); }
  }

  function renderTable() {
    const tbody = root.querySelector('tbody');
    if (!tbody) return;
    tbody.innerHTML = events.map((e) => `
      <tr>
        <td class="mono">${F.missionTimer(e.mission_time_s)}</td>
        <td class="mono">${e.clock}</td>
        <td><span class="cat-chip">${e.category}</span></td>
        <td>${F.escapeHtml(e.message)}</td>
        <td class="mono text-secondary">${F.escapeHtml(e.source)}</td>
        <td class="text-secondary">${F.escapeHtml(e.operator_action || '')}</td>
      </tr>
    `).join('') || '<tr><td colspan="6" style="padding:10px;color:var(--text-secondary);">No matching events.</td></tr>';
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="event-log">
        <div class="event-log__controls">
          <input type="text" placeholder="Search events..." id="ev-search" />
          <select id="ev-category">
            <option value="">All categories</option>
            ${CATEGORIES.map((c) => `<option value="${c}">${c}</option>`).join('')}
          </select>
          <button id="ev-export">Export CSV</button>
        </div>
        <div class="event-log__table">
          <table>
            <thead><tr><th>Mission time</th><th>Clock</th><th>Category</th><th>Event</th><th>Source</th><th>Operator action</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    `;
    root.querySelector('#ev-search').oninput = (e) => { search = e.target.value; refresh(); };
    root.querySelector('#ev-category').onchange = (e) => { category = e.target.value; refresh(); };
    root.querySelector('#ev-export').onclick = () => {
      const a = document.createElement('a');
      a.href = window.MSW_API.exportEventsCsvUrl();
      a.download = 'minesweeper-event-log.csv';
      document.body.appendChild(a); a.click(); a.remove();
    };
    refresh();
    setInterval(refresh, 4000);
  }

  return { mount };
})();
