(async function bootstrap() {
  const C = window.MSW_COMPONENTS;

  // pull real thresholds from the backend so the frontend's staleness /
  // status logic matches the single config file, not a hardcoded guess
  try {
    const thresholds = await window.MSW_API.getThresholds();
    if (thresholds.data_age_seconds) {
      window.MSW_DATA_AGE.thresholds = thresholds.data_age_seconds;
    }
  } catch (e) { console.warn('could not load thresholds, using defaults', e); }

  try {
    const geo = await window.MSW_API.getMap();
    window.MSW_ACTIONS.setMeta({ map: geo });
  } catch (e) { console.warn('could not load map geometry', e); }

  // initial state so the console isn't blank before the first WS push
  try {
    const initial = await window.MSW_API.getMissionState();
    window.MSW_ACTIONS.setMission(initial);
  } catch (e) { console.warn('could not load initial mission state', e); }

  C.topStatusBar.mount(document.getElementById('top-status-bar'));
  C.alertPanel.mount(document.getElementById('alerts-panel'));
  C.roverCommandPanel.mount(document.getElementById('commands-panel'));
  C.mapToolbar.mount(document.getElementById('map-toolbar'));
  await C.mineMap.mount(document.getElementById('map-canvas'));
  C.markerInfoPanel.mount(document.getElementById('map-canvas'), document.getElementById('marker-info-panel'));
  C.timeline.mount(document.getElementById('timeline'));
  C.thermalPanel.mount(document.getElementById('thermal-panel'));
  C.cameraPanel.mount(document.getElementById('camera-panel'));
  C.voiceLink.mount(document.getElementById('voice-link-panel'));
  C.meshNetwork.mount(document.getElementById('mesh-network-panel'));
  C.environmentStrip.mount(document.getElementById('env-strip'));
  C.reportPreview.mount(document.getElementById('report-modal'));
  C.devScenarioPanel.mount(document.getElementById('dev-scenario-panel'));

  window.MSW_WS.startAll();

  // move the marker info panel to float over the map canvas wrapper
  const mapWrap = document.querySelector('#map-canvas .map-canvas-wrap');
  const mip = document.getElementById('marker-info-panel');
  if (mapWrap && mip) mapWrap.appendChild(mip);
})();
