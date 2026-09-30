window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.mapToolbar = (() => {
  let root;

  const LAYERS = [
    ['occupancy', 'Occupancy'], ['trail', 'Trail'], ['nodesCoverage', 'Nodes/coverage'],
    ['gas', 'Gas'], ['temperature', 'Temperature'], ['detections', 'Detections'],
    ['hazards', 'Hazards'], ['annotations', 'Annotations'], ['route', 'Route'],
  ];

  function render(state) {
    const ui = state.ui;
    root.innerHTML = `
      <div class="map-toolbar__group">
        ${LAYERS.map(([key, label]) => `
          <label class="${ui.mapLayers[key] ? 'active-layer' : ''}">
            <input type="checkbox" data-layer="${key}" ${ui.mapLayers[key] ? 'checked' : ''}/> ${label}
          </label>
        `).join('')}
      </div>
      <div class="map-toolbar__sep"></div>
      <div class="map-toolbar__group">
        <label>Gas
          <select id="gas-select">
            <option value="ch4_pct" ${ui.gasLayerKey === 'ch4_pct' ? 'selected' : ''}>CH4</option>
            <option value="co_ppm" ${ui.gasLayerKey === 'co_ppm' ? 'selected' : ''}>CO</option>
            <option value="o2_pct" ${ui.gasLayerKey === 'o2_pct' ? 'selected' : ''}>O2</option>
          </select>
        </label>
      </div>
      <div class="map-toolbar__tools">
        <button id="tool-zoom-in" title="Zoom +">Zoom +</button>
        <button id="tool-zoom-out" title="Zoom -">Zoom -</button>
        <button id="tool-follow" class="${ui.followRover ? 'active' : ''}">Follow Rover</button>
        <button id="tool-center">Center Entry</button>
        <button id="tool-measure" class="${ui.measureMode ? 'active' : ''}">Measure</button>
        <button id="tool-annotate" class="${ui.annotateMode ? 'active' : ''}">Add Annotation</button>
        <button id="tool-snapshot">Snapshot</button>
      </div>
    `;

    root.querySelectorAll('[data-layer]').forEach((cb) => {
      cb.onchange = () => window.MSW_ACTIONS.setUi((u) => ({ mapLayers: { ...u.mapLayers, [cb.dataset.layer]: cb.checked } }));
    });
    root.querySelector('#gas-select').onchange = (e) => window.MSW_ACTIONS.setUi({ gasLayerKey: e.target.value });
    root.querySelector('#tool-zoom-in').onclick = () => window.MSW_MAP_CONTROLLER.zoomIn();
    root.querySelector('#tool-zoom-out').onclick = () => window.MSW_MAP_CONTROLLER.zoomOut();
    root.querySelector('#tool-follow').onclick = () => window.MSW_ACTIONS.setUi((u) => ({ followRover: !u.followRover }));
    root.querySelector('#tool-center').onclick = () => window.MSW_MAP_CONTROLLER.centerEntry();
    root.querySelector('#tool-measure').onclick = () => window.MSW_ACTIONS.setUi((u) => ({ measureMode: !u.measureMode, annotateMode: false }));
    root.querySelector('#tool-annotate').onclick = () => window.MSW_ACTIONS.setUi((u) => ({ annotateMode: !u.annotateMode, measureMode: false }));
    root.querySelector('#tool-snapshot').onclick = () => window.MSW_MAP_CONTROLLER.snapshot();
  }

  function mount(el) {
    root = el;
    window.MSW_STORE.subscribe(render);
    render(window.MSW_STORE.getState());
  }

  return { mount };
})();
