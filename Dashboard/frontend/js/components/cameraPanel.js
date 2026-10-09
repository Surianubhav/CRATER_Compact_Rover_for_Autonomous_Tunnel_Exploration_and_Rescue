window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.cameraPanel = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let canvas;
  let ctx;
  let frameAgeMs = 0;
  let recording = false;
  let recordStart = null;

  function drawFrame() {
    const w = canvas.width; const h = canvas.height;
    ctx.fillStyle = '#0A0C0D';
    ctx.fillRect(0, 0, w, h);

    // subtle procedural "tunnel wall" texture -- an honest placeholder,
    // not an attempt to look like a real camera feed
    ctx.strokeStyle = 'rgba(213,219,224,0.05)';
    for (let i = 0; i < 14; i += 1) {
      ctx.beginPath();
      ctx.moveTo(0, (h / 14) * i + (Math.sin(Date.now() / 4000 + i) * 3));
      ctx.lineTo(w, (h / 14) * i + (Math.cos(Date.now() / 4000 + i) * 3));
      ctx.stroke();
    }
    const grad = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, w / 1.3);
    grad.addColorStop(0, 'rgba(213,219,224,0.05)');
    grad.addColorStop(1, 'rgba(0,0,0,0.55)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = 'rgba(213,219,224,0.35)';
    ctx.font = '11px monospace';
    ctx.fillText('SIMULATED FEED \u2014 RGB CAMERA NOT YET CONNECTED', 10, h - 12);

    frameAgeMs = (frameAgeMs + 60) % 400;
    root.querySelector('.camera-panel__readout').innerHTML = `
      <span class="camera-panel__live-dot"></span>LIVE<br/>
      LATENCY ${(70 + Math.round(Math.random() * 20))} ms<br/>
      FPS ${(11 + Math.round(Math.random() * 2))}<br/>
      FRAME AGE ${(frameAgeMs / 1000).toFixed(2)}s
    `;
    if (recording) {
      const secs = Math.floor((Date.now() - recordStart) / 1000);
      ctx.fillStyle = '#C0413B';
      ctx.beginPath(); ctx.arc(w - 46, 16, 4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#D5DBE0';
      ctx.fillText(`REC ${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`, w - 38, 20);
    }
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Camera</strong><span class="text-secondary mono" style="font-size:9px;">CAM 1 \u00b7 RGB</span></div>
      <div class="camera-panel__frame-wrap">
        <canvas></canvas>
        <div class="camera-panel__readout"></div>
      </div>
      <div class="camera-panel__controls">
        <button data-action="mode">RGB / Thermal</button>
        <button data-action="snapshot">Snapshot</button>
        <button data-action="record">Record</button>
        <button data-action="fullscreen">Fullscreen</button>
      </div>
    `;
    canvas = root.querySelector('canvas');
    ctx = canvas.getContext('2d');
    const resize = () => {
      canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight;
    };
    window.addEventListener('resize', resize);
    resize();
    setInterval(drawFrame, 60);

    root.querySelector('[data-action="mode"]').onclick = () => window.MSW_ACTIONS.setUi((u) => ({ cameraMode: u.cameraMode === 'RGB' ? 'THERMAL' : 'RGB' }));
    root.querySelector('[data-action="snapshot"]').onclick = () => {
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `camera-snapshot-${Date.now()}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    };
    root.querySelector('[data-action="record"]').onclick = (e) => {
      recording = !recording;
      recordStart = recording ? Date.now() : null;
      e.target.classList.toggle('active', recording);
    };
    root.querySelector('[data-action="fullscreen"]').onclick = () => {
      const wrap = root.querySelector('.camera-panel__frame-wrap');
      if (wrap.requestFullscreen) wrap.requestFullscreen();
    };
  }

  return { mount };
})();
