window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.voiceLink = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let pttActive = false;
  let muted = false;
  let volume = 70;

  function render(state) {
    const ui = state.ui;
    const connected = ui.voiceState === 'CONNECTED';
    const elapsed = connected ? Math.floor((Date.now() - ui.voiceConnectedSince) / 1000) : 0;
    const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const ss = String(elapsed % 60).padStart(2, '0');

    root.querySelector('.voice-link__state').className = `voice-link__state ${ui.voiceState}`;
    root.querySelector('.voice-link__state').innerHTML = `
      <span><span class="dot"></span>VOICE LINK \u00b7 ${ui.voiceState}${connected ? ` \u00b7 ${mm}:${ss}` : ''}</span>
    `;
    root.querySelector('.voice-link__waveform').innerHTML = Array.from({ length: 24 }).map(() => {
      const h = connected && pttActive ? 4 + Math.random() * 14 : 2;
      return `<span style="height:${h}px;"></span>`;
    }).join('');
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Voice Link</strong></div>
      <div class="voice-link">
        <div class="voice-link__state"></div>
        <div class="voice-link__waveform"></div>
        <div class="voice-link__controls">
          <button class="voice-link__ptt" id="vl-ptt">Push to Talk</button>
          <button id="vl-mute">Mute</button>
        </div>
        <div class="voice-link__meta">
          <span>Volume <span id="vl-vol-val">70</span>%</span>
          <span>Latency <span class="mono">62 ms</span></span>
        </div>
        <input type="range" id="vl-volume" min="0" max="100" value="70" style="width:100%;" />
        <button id="vl-standard">Play Standard Message</button>
      </div>
    `;

    const pttBtn = root.querySelector('#vl-ptt');
    pttBtn.onmousedown = () => {
      pttActive = true; pttBtn.classList.add('active');
      window.MSW_ACTIONS.setUi({ voiceState: 'CONNECTED', voiceConnectedSince: window.MSW_STORE.getState().ui.voiceConnectedSince || Date.now() });
    };
    pttBtn.onmouseup = () => { pttActive = false; pttBtn.classList.remove('active'); };
    pttBtn.onmouseleave = () => { pttActive = false; pttBtn.classList.remove('active'); };

    root.querySelector('#vl-mute').onclick = (e) => { muted = !muted; e.target.classList.toggle('active', muted); };
    root.querySelector('#vl-volume').oninput = (e) => {
      volume = Number(e.target.value);
      root.querySelector('#vl-vol-val').textContent = volume;
    };
    root.querySelector('#vl-standard').onclick = () => {
      window.MSW_ACTIONS.setUi({ voiceState: 'CONNECTED', voiceConnectedSince: window.MSW_STORE.getState().ui.voiceConnectedSince || Date.now() });
    };

    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
    setInterval(() => render(window.MSW_STORE.getState()), 1000);
  }

  return { mount };
})();
