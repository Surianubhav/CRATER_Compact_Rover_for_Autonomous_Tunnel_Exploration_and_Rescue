window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.thermalPanel = (() => {
  const F = window.MSW_FORMAT;
  let root;
  let video;
  let captureCanvas;
  let lastResult = null;
  let cameraReady = false;
  let captureTimer = null;

  const PALETTES = {
    'white-hot': 'grayscale(1) contrast(1.15)',
    'black-hot': 'grayscale(1) invert(1) contrast(1.15)',
    amber: 'grayscale(1) sepia(1) saturate(3) contrast(1.1)',
  };

  async function startCamera() {
    window.MSW_ACTIONS.setUi({ thermalConnection: 'CONNECTING' });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 }, audio: false });
      video.srcObject = stream;
      await video.play();
      cameraReady = true;
      captureLoop();
    } catch (err) {
      cameraReady = false;
      window.MSW_ACTIONS.setUi({ thermalConnection: 'DISCONNECTED' });
      renderStatusMessage('DISCONNECTED', 'No camera source connected. Grant webcam access, or wire the rover\u2019s ' +
        'thermal feed into POST /api/thermal/frame, to see live model inference here.');
    }
  }

  function captureLoop() {
    if (captureTimer) clearInterval(captureTimer);
    captureTimer = setInterval(async () => {
      if (!cameraReady) return;
      const ui = window.MSW_STORE.getState().ui;
      if (ui.thermalFrozen) return;
      captureCanvas.width = video.videoWidth || 480;
      captureCanvas.height = video.videoHeight || 360;
      const ctx = captureCanvas.getContext('2d');
      ctx.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
      captureCanvas.toBlob(async (blob) => {
        if (!blob) return;
        try {
          const result = await window.MSW_API.postThermalFrame(blob);
          lastResult = result;
          window.MSW_ACTIONS.setUi({ thermalConnection: result.connection_state });
          if (result.detections && result.detections.length) {
            window.MSW_ACTIONS.setMeta((meta) => ({
              thermalDetectionsHistory: [
                ...result.detections.map((d) => ({ id: d.id, timestamp: d.timestamp, confidence: d.confidence, thumb: d.thumbnail_data_uri })),
                ...meta.thermalDetectionsHistory,
              ].slice(0, 6),
            }));
          }
          renderFrame(result);
        } catch (err) {
          window.MSW_ACTIONS.setUi({ thermalConnection: 'MODEL_ERROR' });
          renderStatusMessage('MODEL_ERROR', String(err.message || err));
        }
      }, 'image/jpeg', 0.85);
    }, 1500);
  }

  function renderStatusMessage(stateName, message) {
    const overlay = root.querySelector('.thermal-panel__status-overlay');
    overlay.className = `thermal-panel__status-overlay active ${stateName}`;
    overlay.innerHTML = `<div class="state">${stateName.replace('_', ' ')}</div><div>${F.escapeHtml(message)}</div>`;
    root.querySelector('.thermal-panel__bboxes').innerHTML = '';
  }

  function renderFrame(result) {
    const overlay = root.querySelector('.thermal-panel__status-overlay');
    const img = root.querySelector('.thermal-panel__img');
    const ui = window.MSW_STORE.getState().ui;
    img.style.filter = PALETTES[ui.thermalPalette] || PALETTES['white-hot'];

    if (result.connection_state !== 'LIVE') {
      renderStatusMessage(result.connection_state, result.error_message || 'Model not ready.');
      return;
    }
    overlay.className = 'thermal-panel__status-overlay';
    overlay.innerHTML = '';

    if (result.frame_data_uri) img.src = result.frame_data_uri;

    const bboxWrap = root.querySelector('.thermal-panel__bboxes');
    bboxWrap.innerHTML = (result.detections || []).map((d) => `
      <div class="thermal-panel__bbox" style="left:${d.bbox.x_pct}%;top:${d.bbox.y_pct}%;width:${d.bbox.width_pct}%;height:${d.bbox.height_pct}%;">
        <span class="label">PERSON ${d.confidence.toFixed(2)}</span>
      </div>
    `).join('');

    root.querySelector('.thermal-panel__overlay-readout').innerHTML = `
      scene avg ${F.num(result.scene_avg_c, 1)}\u00b0C<br/>model ${F.escapeHtml(result.model_name || '')}
    `;
    root.querySelector('.thermal-panel__overlay-readout .max').innerHTML = `max ${F.num(result.scene_max_c, 1)}\u00b0C`;

    root.querySelector('.thermal-panel__tags').innerHTML = (result.detections || [])
      .flatMap((d) => d.classification_tags)
      .filter((v, i, arr) => arr.indexOf(v) === i)
      .map((t) => `<span class="tag ${t === 'HUMAN SIGNATURE' ? 'HUMAN' : t === 'HOT SPOT' ? 'HOT' : 'FIRE'}">${t}</span>`)
      .join('');
  }

  function renderThumbs(state) {
    const el = root.querySelector('.thermal-panel__thumbs');
    const hist = state.meta.thermalDetectionsHistory || [];
    el.innerHTML = hist.map((h) => `
      <img src="${h.thumb || 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2236%22 height=%2236%22%3E%3Crect width=%2236%22 height=%2236%22 fill=%22%23222%22/%3E%3C/svg%3E'}"
           title="${h.id} \u00b7 ${Math.round(h.confidence * 100)}%" data-thumb-id="${h.id}" />
    `).join('') || '<span class="text-secondary" style="font-size:10px;">No detections yet</span>';
    el.querySelectorAll('[data-thumb-id]').forEach((im) => {
      im.onclick = () => {
        const m = window.MSW_STORE.getState().mission;
        const d = m && m.detections.find((x) => x.id === im.dataset.thumbId);
        if (d) window.MSW_ACTIONS.setUi({ selectedMarker: { type: 'detection', id: d.id, position: d.position, centerRequestId: Date.now() } });
      };
    });
  }

  function render(state) {
    renderThumbs(state);
    const ui = state.ui;
    root.querySelectorAll('.thermal-panel__controls [data-palette]').forEach((b) => b.classList.toggle('active', b.dataset.palette === ui.thermalPalette));
    root.querySelector('[data-action="freeze"]').classList.toggle('active', ui.thermalFrozen);
  }

  function snapshotFrame() {
    const img = root.querySelector('.thermal-panel__img');
    const a = document.createElement('a');
    a.href = img.src.startsWith('data:') ? img.src : captureCanvas.toDataURL('image/jpeg');
    a.download = `thermal-snapshot-${Date.now()}.jpg`;
    document.body.appendChild(a); a.click(); a.remove();
  }

  function mount(el) {
    root = el;
    root.innerHTML = `
      <div class="panel-header"><strong>Thermal Camera</strong><span class="text-secondary mono" style="font-size:9px;">4:3</span></div>
      <div class="thermal-panel__frame-wrap">
        <img class="thermal-panel__img" alt="thermal feed" />
        <div class="thermal-panel__bboxes"></div>
        <div class="thermal-panel__overlay-readout"><span class="max"></span></div>
        <div class="thermal-panel__status-overlay"></div>
      </div>
      <div class="thermal-panel__tags"></div>
      <div class="thermal-panel__thumbs"></div>
      <div class="thermal-panel__controls">
        <button data-palette="white-hot">White-hot</button>
        <button data-palette="black-hot">Black-hot</button>
        <button data-palette="amber">Amber</button>
        <button data-action="snapshot">Snapshot</button>
        <button data-action="freeze">Freeze</button>
      </div>
    `;
    video = document.createElement('video');
    video.muted = true; video.playsInline = true;
    captureCanvas = document.createElement('canvas');

    root.querySelectorAll('[data-palette]').forEach((b) => {
      b.onclick = () => window.MSW_ACTIONS.setUi({ thermalPalette: b.dataset.palette });
    });
    root.querySelector('[data-action="snapshot"]').onclick = snapshotFrame;
    root.querySelector('[data-action="freeze"]').onclick = () => window.MSW_ACTIONS.setUi((u) => ({ thermalFrozen: !u.thermalFrozen }));

    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
    renderStatusMessage('CONNECTING', 'Requesting camera source\u2026');
    startCamera();
  }

  return { mount };
})();
