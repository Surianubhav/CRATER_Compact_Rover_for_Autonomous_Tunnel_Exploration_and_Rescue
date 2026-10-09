window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.alertPanel = (() => {
  const F = window.MSW_FORMAT;
  const CFG = window.MSW_CONFIG;
  let root;
  let bodyEl;
  let eventLogMounted = false;

  function ackAlert(id, ev) {
    ev.stopPropagation();
    window.MSW_API.ackAlert(id).catch((e) => console.error(e));
  }

  function selectAlert(alert) {
    window.MSW_ACTIONS.setUi({ selectedAlertId: alert.id });
    if (alert.position) {
      window.MSW_ACTIONS.setUi({
        selectedMarker: { type: alert.ref_type, id: alert.ref_id, position: alert.position, centerRequestId: Date.now() },
      });
    }
  }

  function renderAlertRow(alert, ui) {
    const tierLabel = CFG.ALERT_TIER_LABEL[alert.tier];
    const glyph = CFG.ALERT_TIER_GLYPH[alert.tier];
    const mt = F.missionTimer(alert.mission_time_s);
    const ageS = Math.max(0, (Date.now() / 1000) - (alert.created_at || 0));
    const selected = ui.selectedAlertId === alert.id ? 'selected' : '';
    const acked = alert.state === 'ACKED' ? 'acked' : '';
    const ackDisabled = alert.state === 'ACKED' ? 'disabled' : '';
    const ackLabel = alert.state === 'ACKED' ? 'ACKED' : 'ACK';
    return `
      <div class="alert-row tier-${alert.tier} ${selected} ${acked}" data-alert-id="${alert.id}">
        <div class="tier-num">${alert.tier}<br/><span class="tier-glyph">${glyph}</span></div>
        <div class="alert-row__body">
          <div class="title">${F.escapeHtml(alert.title)}</div>
          <div class="detail">${F.escapeHtml(alert.detail)}</div>
          <div class="meta">mission time ${mt} \u00b7 age ${Math.round(ageS)}s \u00b7 ${tierLabel}</div>
        </div>
        <button class="alert-row__ack ${alert.state === 'ACKED' ? 'done' : ''}" ${ackDisabled} data-ack-id="${alert.id}">${ackLabel}</button>
      </div>
    `;
  }

  function renderActiveTab(state) {
    const alerts = state.mission ? state.mission.alerts : [];
    if (!alerts.length) {
      bodyEl.innerHTML = '<div style="padding:14px;color:var(--text-secondary);font-size:12px;">No active alerts.</div>';
      return;
    }
    bodyEl.innerHTML = alerts.map((a) => renderAlertRow(a, state.ui)).join('');
    bodyEl.querySelectorAll('[data-ack-id]').forEach((btn) => {
      btn.addEventListener('click', (ev) => ackAlert(btn.dataset.ackId, ev));
    });
    bodyEl.querySelectorAll('.alert-row').forEach((rowEl) => {
      rowEl.addEventListener('click', () => {
        const alert = alerts.find((a) => a.id === rowEl.dataset.alertId);
        if (alert) selectAlert(alert);
      });
    });
  }

  function render(state) {
    if (!root) return;
    const ui = state.ui;
    const activeCount = state.mission ? state.mission.alerts.length : 0;

    root.querySelector('.alert-tabs').innerHTML = `
      <button data-tab="ACTIVE" class="${ui.alertTab === 'ACTIVE' ? 'active' : ''}">Active (${activeCount})</button>
      <button data-tab="EVENT_LOG" class="${ui.alertTab === 'EVENT_LOG' ? 'active' : ''}">Event Log</button>
    `;
    root.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.onclick = () => window.MSW_ACTIONS.setUi({ alertTab: btn.dataset.tab });
    });

    if (ui.alertTab === 'ACTIVE') {
      renderActiveTab(state);
      eventLogMounted = false;
    } else if (!eventLogMounted) {
      window.MSW_COMPONENTS.eventLog.mount(bodyEl);
      eventLogMounted = true;
    }
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Alerts</strong></div>
      <div class="alert-tabs"></div>
      <div class="panel-body" id="alerts-body"></div>
    `;
    bodyEl = root.querySelector('#alerts-body');
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
