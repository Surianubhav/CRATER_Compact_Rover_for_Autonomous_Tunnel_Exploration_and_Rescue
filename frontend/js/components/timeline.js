window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.timeline = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let bounds = { start_s: 0, end_s: 0 };
  let markers = [];
  let playTimer = null;
  let lastFetchAt = 0;

  async function refreshTimeline() {
    try {
      const data = await window.MSW_API.getReplayTimeline();
      bounds = { start_s: data.start_s, end_s: data.end_s };
      markers = data.markers;
      renderTrackMarkers();
    } catch (e) { /* backend may not have history yet */ }
  }

  function renderTrackMarkers() {
    const el = root.querySelector('.timeline__markers');
    if (!el) return;
    const span = Math.max(1, bounds.end_s - bounds.start_s);
    el.innerHTML = markers.map((m) => {
      const pct = ((m.mission_time_s - bounds.start_s) / span) * 100;
      return `<div class="timeline__marker ${m.category}" style="left:${pct}%" title="${F.escapeHtml(m.message)}"></div>`;
    }).join('');
  }

  async function scrubTo(t) {
    window.MSW_ACTIONS.setUi({ replayMode: true, replayTimeS: t });
    const now = Date.now();
    if (now - lastFetchAt < 150) return; // throttle
    lastFetchAt = now;
    try {
      const snap = await window.MSW_API.getReplaySnapshot(t);
      if (!snap.error) window.MSW_ACTIONS.setMission({ ...snap, replay_mode: true, replay_time_s: t });
    } catch (e) { /* ignore */ }
  }

  function goLive() {
    if (playTimer) { clearInterval(playTimer); playTimer = null; }
    window.MSW_ACTIONS.setUi({ replayMode: false, replayPlaying: false, replayTimeS: null });
  }

  function togglePlay() {
    const ui = window.MSW_STORE.getState().ui;
    if (ui.replayPlaying) {
      clearInterval(playTimer); playTimer = null;
      window.MSW_ACTIONS.setUi({ replayPlaying: false });
      return;
    }
    if (!ui.replayMode) window.MSW_ACTIONS.setUi({ replayMode: true, replayTimeS: bounds.start_s });
    window.MSW_ACTIONS.setUi({ replayPlaying: true });
    playTimer = setInterval(() => {
      const state = window.MSW_STORE.getState();
      const next = (state.ui.replayTimeS || 0) + state.ui.replaySpeed;
      if (next >= bounds.end_s) { goLive(); return; }
      scrubTo(next);
    }, 500);
  }

  function render(state) {
    const ui = state.ui;
    const mission = state.mission;
    const missionNow = mission ? mission.mission_time_s : 0;
    const t = ui.replayMode ? (ui.replayTimeS || 0) : missionNow;
    const span = Math.max(1, bounds.end_s - bounds.start_s || missionNow || 1);
    const pct = bounds.end_s > bounds.start_s ? ((t - bounds.start_s) / span) * 100 : 100;

    root.querySelector('.timeline__play').textContent = ui.replayPlaying ? '\u23F8' : '\u25B6';
    root.querySelector('.timeline__playhead').style.left = `${Math.max(0, Math.min(100, pct))}%`;
    root.querySelector('.timeline__progress').style.width = `${Math.max(0, Math.min(100, pct))}%`;
    root.querySelectorAll('.timeline__speed button').forEach((b) => b.classList.toggle('active', Number(b.dataset.speed) === ui.replaySpeed));
    root.querySelector('.timeline__live-btn').classList.toggle('in-replay', ui.replayMode);
    root.querySelector('.timeline__replay-badge').classList.toggle('active', ui.replayMode);
    root.querySelector('.timeline__replay-badge').textContent = `REPLAY ${F.missionTimer(t)}`;

    document.getElementById('app').classList.toggle('replay-mode', !!ui.replayMode);
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <button class="timeline__play">\u25B6</button>
      <div class="timeline__track">
        <div class="timeline__rail"></div>
        <div class="timeline__progress"></div>
        <div class="timeline__markers"></div>
        <div class="timeline__playhead"></div>
        <input type="range" class="timeline__scrub-input" min="0" max="100" value="0" step="0.1" />
      </div>
      <div class="timeline__speed">
        <button data-speed="1">1x</button>
        <button data-speed="4">4x</button>
        <button data-speed="16">16x</button>
      </div>
      <span class="timeline__replay-badge"></span>
      <button class="timeline__live-btn">LIVE</button>
    `;

    root.querySelector('.timeline__play').onclick = togglePlay;
    root.querySelector('.timeline__live-btn').onclick = goLive;
    root.querySelectorAll('.timeline__speed button').forEach((b) => {
      b.onclick = () => window.MSW_ACTIONS.setUi({ replaySpeed: Number(b.dataset.speed) });
    });
    root.querySelector('.timeline__scrub-input').oninput = (e) => {
      const span = Math.max(1, bounds.end_s - bounds.start_s);
      const t = bounds.start_s + (Number(e.target.value) / 100) * span;
      scrubTo(t);
    };

    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
    refreshTimeline();
    setInterval(refreshTimeline, 5000);
  }

  return { mount };
})();
