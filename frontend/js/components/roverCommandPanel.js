window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.roverCommandPanel = (() => {
  const F = window.MSW_FORMAT;
  const CFG = window.MSW_CONFIG;
  let root;

  const COMMANDS = [
    { type: 'return_to_entry', label: 'Return to Entry' },
    { type: 'return_to_node', label: 'Return to Node', dropdown: true },
    { type: 'go_to_node', label: 'Go to Node', dropdown: true },
    { type: 'explore_unexplored', label: 'Explore Unexplored' },
    { type: 'go_to_marker', label: 'Go to Selected Marker' },
    { type: 'hold_position', label: 'Hold Position' },
  ];

  function issueControlToggle(mission) {
    const holding = mission.rover.control_state === 'HOLDING';
    window.MSW_API.issueCommand(holding ? 'resume' : 'hold_position').catch((e) => console.error(e));
  }

  function setPending(type, label, target) {
    window.MSW_ACTIONS.setUi({ pendingCommand: { type, label, target: target || null } });
  }

  function confirmPending() {
    const state = window.MSW_STORE.getState();
    const pending = state.ui.pendingCommand;
    if (!pending) return;
    window.MSW_API.issueCommand(pending.type, pending.target).catch((e) => console.error(e));
    window.MSW_ACTIONS.setUi({ pendingCommand: null });
  }

  function cancelPending() {
    window.MSW_ACTIONS.setUi({ pendingCommand: null });
  }

  function render(state) {
    const m = state.mission;
    if (!m || !root) return;
    const linkLost = m.link.status === 'LOST' && !state.ui.replayMode;
    const holding = m.rover.control_state === 'HOLDING';
    const pending = state.ui.pendingCommand;

    root.querySelector('.control-toggle').innerHTML = `
      <button class="${!holding ? 'active autonomous' : ''}" id="ctl-auto">Autonomous</button>
      <button class="${holding ? 'active holding' : ''}" id="ctl-hold">Hold/Resume</button>
    `;
    root.querySelector('#ctl-auto').onclick = () => { if (holding) issueControlToggle(m); };
    root.querySelector('#ctl-hold').onclick = () => issueControlToggle(m);

    const btnsEl = root.querySelector('.cmd-buttons');
    btnsEl.innerHTML = COMMANDS.map((c) => {
      if (c.dropdown) {
        return `
          <div>
            <button class="cmd-btn has-select" data-cmd="${c.type}">${c.label}</button>
            <select data-cmd-select="${c.type}">
              <option value="">Select node\u2026</option>
              ${CFG.NODE_CHAIN.map((n) => `<option value="${n}">${n}</option>`).join('')}
            </select>
          </div>
        `;
      }
      return `<button class="cmd-btn" data-cmd="${c.type}">${c.label}</button>`;
    }).join('');

    btnsEl.querySelectorAll('[data-cmd]').forEach((btn) => {
      const cmd = COMMANDS.find((c) => c.type === btn.dataset.cmd);
      if (cmd.dropdown) return; // handled by its select's onchange
      btn.onclick = () => setPending(cmd.type, cmd.label);
    });
    btnsEl.querySelectorAll('[data-cmd-select]').forEach((sel) => {
      sel.onchange = () => {
        if (!sel.value) return;
        const cmd = COMMANDS.find((c) => c.type === sel.dataset.cmdSelect);
        setPending(cmd.type, `${cmd.label} ${sel.value}`, sel.value);
      };
    });

    const strip = root.querySelector('.cmd-confirm-strip');
    if (pending) {
      strip.classList.add('active');
      strip.innerHTML = `
        <div>${F.escapeHtml(pending.label)}${linkLost ? ' \u2014 link down, will queue' : ''}?</div>
        <div class="row">
          <button class="confirm-btn" id="cmd-confirm">Confirm</button>
          <button class="cancel-btn" id="cmd-cancel">Cancel</button>
        </div>
      `;
      root.querySelector('#cmd-confirm').onclick = confirmPending;
      root.querySelector('#cmd-cancel').onclick = cancelPending;
    } else {
      strip.classList.remove('active');
      strip.innerHTML = '';
    }

    root.querySelector('.offline-banner').classList.toggle('active', linkLost);

    const queueEl = root.querySelector('.cmd-queue');
    queueEl.innerHTML = m.commands.map((c) => `
      <div class="cmd-queue-item">
        <span class="id">${c.id}</span> ${F.escapeHtml(c.label)}
        <span class="status ${c.status}">${c.status === 'QUEUED_OFFLINE' ? 'WILL SEND ON RECONNECT' : c.status}</span>
      </div>
    `).join('') || '<div style="padding:6px;color:var(--text-secondary);font-size:11px;">No commands issued yet.</div>';
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Rover Commands</strong></div>
      <div class="commands-panel">
        <div class="control-toggle"></div>
        <div class="cmd-buttons" style="display:flex;flex-direction:column;gap:4px;"></div>
        <div class="cmd-confirm-strip"></div>
        <div class="offline-banner">Lost link \u2014 will send on reconnect</div>
        <div class="cmd-queue"></div>
      </div>
    `;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
