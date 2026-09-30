window.MSW_WS = (() => {
  const base = window.MSW_CONFIG.WS_BASE;
  const sockets = {};

  function connect(name, path, onMessage) {
    let attempt = 0;
    let closedByUs = false;

    function open() {
      const ws = new WebSocket(base + path);
      sockets[name] = ws;

      ws.onopen = () => { attempt = 0; };
      ws.onmessage = (evt) => {
        try { onMessage(JSON.parse(evt.data)); } catch (err) { console.error(`[ws:${name}] parse error`, err); }
      };
      ws.onclose = () => {
        if (closedByUs) return;
        attempt += 1;
        const delay = Math.min(1000 * attempt, 8000);
        setTimeout(open, delay);
      };
      ws.onerror = () => ws.close();
    }
    open();
    return () => { closedByUs = true; sockets[name] && sockets[name].close(); };
  }

  return {
    startAll() {
      connect('telemetry', '/ws/telemetry', (payload) => {
        if (window.MSW_STORE.getState().ui.replayMode) return; // ignore live pushes while scrubbing replay
        window.MSW_ACTIONS.setMission(payload);
      });
      connect('thermal', '/ws/thermal', () => { /* mission snapshot already carries detections */ });
      connect('events', '/ws/events', (payload) => {
        window.MSW_ACTIONS.setMeta({ eventsStreamLast: payload });
      });
    },
  };
})();
