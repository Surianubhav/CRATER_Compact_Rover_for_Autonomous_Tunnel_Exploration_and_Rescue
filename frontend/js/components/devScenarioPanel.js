window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.devScenarioPanel = (() => {
  function trigger(scenario) {
    window.MSW_API.triggerScenario(scenario).catch((e) => console.error(e));
  }

  function mount(el) {
    el.innerHTML = `
      <button class="dev-panel-toggle" id="dev-toggle">SIMULATION</button>
      <div class="dev-panel" id="dev-panel">
        <div class="dev-panel__title">Dev scenario (not production UI)</div>
        <button data-scenario="nominal">Nominal</button>
        <button data-scenario="person_detected">Person Detected</button>
        <button data-scenario="communication_lost">Communication Lost</button>
        <button id="dev-replay">Replay (jump -60s)</button>
      </div>
    `;
    const panel = el.querySelector('#dev-panel');
    el.querySelector('#dev-toggle').onclick = () => {
      window.MSW_ACTIONS.setUi((u) => ({ devPanelOpen: !u.devPanelOpen }));
      panel.classList.toggle('open');
    };
    el.querySelectorAll('[data-scenario]').forEach((b) => { b.onclick = () => trigger(b.dataset.scenario); });
    el.querySelector('#dev-replay').onclick = () => {
      const m = window.MSW_STORE.getState().mission;
      if (!m) return;
      const t = Math.max(0, m.mission_time_s - 60);
      window.MSW_ACTIONS.setUi({ replayMode: true, replayTimeS: t });
      window.MSW_API.getReplaySnapshot(t).then((snap) => {
        if (!snap.error) window.MSW_ACTIONS.setMission({ ...snap, replay_mode: true, replay_time_s: t });
      });
    };
  }

  return { mount };
})();
