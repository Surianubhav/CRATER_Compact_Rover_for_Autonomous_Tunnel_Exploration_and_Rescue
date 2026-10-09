window.MSW_COMPONENTS = window.MSW_COMPONENTS || {};

window.MSW_COMPONENTS.mineMap = (() => {
  const F = window.MSW_FORMAT;
  let svg;
  let wrapEl;
  let mapGeo = null;
  let viewBox = { x: -20, y: -20, w: 320, h: 180 };
  const baseViewBox = { x: -20, y: -20, w: 320, h: 180 };
  let measurePoints = [];
  let routeCache = { detectionId: null, data: null };

  function toSvgPoint(evt) {
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const ctm = svg.getScreenCTM().inverse();
    const p = pt.matrixTransform(ctm);
    return { x: p.x, y: p.y };
  }

  function corridorPath(points) {
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x_m} ${p.y_m}`).join(' ');
  }

  function partialPath(points, cumDist, maxDist) {
    const pts = [];
    for (let i = 0; i < points.length; i += 1) {
      if (cumDist[i] <= maxDist) {
        pts.push(points[i]);
      } else {
        const prev = points[i - 1];
        const t = (maxDist - cumDist[i - 1]) / (cumDist[i] - cumDist[i - 1] || 1);
        pts.push({ x_m: prev.x_m + (points[i].x_m - prev.x_m) * t, y_m: prev.y_m + (points[i].y_m - prev.y_m) * t });
        break;
      }
    }
    return pts;
  }

  function cumulative(points) {
    const out = [0];
    for (let i = 1; i < points.length; i += 1) {
      const dx = points[i].x_m - points[i - 1].x_m;
      const dy = points[i].y_m - points[i - 1].y_m;
      out.push(out[i - 1] + Math.hypot(dx, dy));
    }
    return out;
  }

  function gridLines() {
    const step = 10;
    const lines = [];
    const x0 = Math.floor(viewBox.x / step) * step;
    const x1 = viewBox.x + viewBox.w;
    for (let x = x0; x <= x1; x += step) lines.push(`<line x1="${x}" y1="${viewBox.y}" x2="${x}" y2="${viewBox.y + viewBox.h}" />`);
    const y0 = Math.floor(viewBox.y / step) * step;
    const y1 = viewBox.y + viewBox.h;
    for (let y = y0; y <= y1; y += step) lines.push(`<line x1="${viewBox.x}" y1="${y}" x2="${viewBox.x + viewBox.w}" y2="${y}" />`);
    return lines.join('');
  }

  function pillars(points) {
    // Decorative rectangular pillars along the corridor to sell the
    // "rectangular pillar" mining aesthetic -- procedurally placed, not
    // surveyed geometry.
    const out = [];
    for (let i = 0; i < points.length - 1; i += 1) {
      const a = points[i]; const b = points[i + 1];
      const segLen = Math.hypot(b.x_m - a.x_m, b.y_m - a.y_m);
      const steps = Math.floor(segLen / 14);
      for (let s = 1; s <= steps; s += 1) {
        const t = s / (steps + 1);
        const cx = a.x_m + (b.x_m - a.x_m) * t;
        const cy = a.y_m + (b.y_m - a.y_m) * t;
        const nx = -(b.y_m - a.y_m) / (segLen || 1);
        const ny = (b.x_m - a.x_m) / (segLen || 1);
        const off = 4.5;
        out.push(`<rect x="${cx + nx * off - 1.6}" y="${cy + ny * off - 1.6}" width="3.2" height="3.2" class="map-pillar" />`);
        out.push(`<rect x="${cx - nx * off - 1.6}" y="${cy - ny * off - 1.6}" width="3.2" height="3.2" class="map-pillar" />`);
      }
    }
    return out.join('');
  }

  function gasStatusFor(mission, key) {
    if (!mission) return 'normal';
    const g = mission.telemetry.gases.find((x) => x.key === key);
    return g ? g.status.toLowerCase() : 'normal';
  }

  function tempStatusFor(mission) {
    if (!mission) return 'normal';
    const t = mission.telemetry.environment.find((x) => x.key === 'temperature_c');
    return t ? t.status.toLowerCase() : 'normal';
  }

  async function ensureRoute(detectionId) {
    if (routeCache.detectionId === detectionId) return routeCache.data;
    try {
      const data = await window.MSW_API.getRoute({ detection_id: detectionId });
      routeCache = { detectionId, data };
      return data;
    } catch (e) { return null; }
  }

  function selectMarker(type, id, position) {
    window.MSW_ACTIONS.setUi({ selectedMarker: { type, id, position, centerRequestId: Date.now() } });
  }

  function render(state) {
    if (!svg || !mapGeo) return;
    const m = state.mission;
    if (!m) return;
    const ui = state.ui;
    const layers = ui.mapLayers;
    const mainPath = mapGeo.main_path;
    const cum = cumulative(mainPath);
    const explored = partialPath(mainPath, cum, m.rover.distance_from_entry_m);

    if (ui.followRover) {
      viewBox = {
        x: m.rover.position.x_m - viewBox.w / 2,
        y: m.rover.position.y_m - viewBox.h / 2,
        w: viewBox.w, h: viewBox.h,
      };
    }

    svg.setAttribute('viewBox', `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`);
    const galleryW = mapGeo.gallery_half_width_m * 2;
    const deadEndW = mapGeo.dead_end_half_width_m * 2;

    let html = '';
    // occupancy: unexplored hatch (whole corridor), then explored overlay
    if (layers.occupancy) {
      html += `<path d="${corridorPath(mainPath)}" class="map-corridor-unexplored" stroke-width="${galleryW}" fill="none" />`;
      html += `<path d="${corridorPath(mapGeo.dead_end_branch)}" class="map-corridor-unexplored" stroke-width="${deadEndW}" fill="none" />`;
      html += `<path d="${corridorPath(explored)}" class="map-corridor-explored" stroke-width="${galleryW}" fill="none" />`;
      html += pillars(mainPath);
    }
    if (layers.nodesCoverage) {
      html += m.nodes.map((n) => `<circle cx="${n.x_m}" cy="${n.y_m}" r="${n.range_m}" class="map-node-range" />`).join('');
    }

    // 10m grid (behind objects, above occupancy)
    html += `<g class="map-grid">${gridLines()}</g>`;

    // entry
    html += `<g class="map-entry"><polygon points="-3,-3 3,-3 0,4" /><text x="0" y="-6">ENTRY</text></g>`;

    // dead end / roof fall hazard label
    if (layers.hazards) {
      mapGeo.hazards.forEach((h) => {
        let sevClass = 'normal';
        if (h.type === 'gas') sevClass = gasStatusFor(m, 'ch4_pct');
        if (h.type === 'heat') sevClass = tempStatusFor(m);
        if (h.type === 'roof_fall') sevClass = 'danger';
        html += `
          <g class="map-hazard sev-${sevClass}" data-hazard="${h.id}" transform="translate(${h.x_m},${h.y_m})">
            <circle r="9" class="hit-area" />
            <polygon points="0,-5 5,4 -5,4" />
            <text x="0" y="12">${F.escapeHtml(h.label)}</text>
          </g>`;
      });
    }

    // gas layer selector marker (CH4 zone glow already covered by hazard); highlight selected gas key subtly
    if (layers.gas) {
      const g = m.telemetry.gases.find((x) => x.key === ui.gasLayerKey);
      if (g && g.status !== 'NORMAL') {
        html += `<circle cx="180" cy="36" r="26" class="map-gas-glow sev-${g.status.toLowerCase()}" />`;
      }
    }

    // route (only meaningful once a detection is confirmed)
    const confirmed = (m.detections || []).find((d) => d.status === 'CONFIRMED');
    if (layers.route && confirmed) {
      const cached = routeCache.detectionId === confirmed.id ? routeCache.data : null;
      if (cached) {
        html += cached.segments.map((seg) => `
          <line x1="${seg.from_xy[0]}" y1="${seg.from_xy[1]}" x2="${seg.to_xy[0]}" y2="${seg.to_xy[1]}"
                class="map-route sev-${seg.severity}" />
        `).join('');
      } else {
        ensureRoute(confirmed.id).then(() => render(window.MSW_STORE.getState()));
      }
    }

    // annotations
    if (layers.annotations) {
      html += (m.annotations || []).map((a) => `
        <g class="map-annotation" data-ann="${a.id}" transform="translate(${a.x_m},${a.y_m})">
          <path d="M0,-8 L0,4 M0,-8 L6,-5 L0,-2 Z" />
          <text x="8" y="-2">${F.escapeHtml(a.label)}</text>
        </g>
      `).join('');
    }

    // nodes
    html += m.nodes.map((n) => {
      const sel = ui.selectedMarker && ui.selectedMarker.type === 'node' && ui.selectedMarker.id === n.id ? 'selected' : '';
      return `
        <g class="map-node state-${n.state} ${sel}" data-node="${n.id}" transform="translate(${n.x_m},${n.y_m})">
          <circle r="9" class="hit-area" />
          <circle r="${n.range_m}" class="range-ring" />
          <rect x="-4" y="-4" width="8" height="8" />
          <text x="0" y="-8">${n.id}</text>
        </g>`;
    }).join('');

    // detections / person markers
    if (layers.detections) {
      html += (m.detections || []).map((d) => {
        if (!d.position || d.status === 'DISMISSED') return '';
        const sel = ui.selectedMarker && ui.selectedMarker.type === 'detection' && ui.selectedMarker.id === d.id ? 'selected' : '';
        const ringClass = d.status === 'CONFIRMED' ? 'ring-solid' : 'ring-dashed';
        return `
          <g class="map-person ${ringClass} ${sel}" data-detection="${d.id}" transform="translate(${d.position.x_m},${d.position.y_m})">
            <circle r="10" class="hit-area" />
            <circle r="6" class="halo" />
            <circle r="2.4" class="core" />
            <text x="8" y="4">${d.id}</text>
          </g>`;
      }).join('');
    }

    // rover
    const r = m.rover;
    const ghosted = r.ghosted ? 'ghosted' : '';
    const uncertaintyR = r.ghosted ? Math.min(60, 8 + (m.link.last_contact_age_s || 0) * 0.6) : 0;
    html += `<polyline points="${(r.trail || []).map((p) => `${p.x_m},${p.y_m}`).join(' ')}" class="map-trail" fill="none" />`;
    if (r.ghosted) {
      html += `<circle cx="${r.position.x_m}" cy="${r.position.y_m}" r="${uncertaintyR}" class="map-uncertainty" />`;
    }
    html += `
      <g class="map-rover ${ghosted}" transform="translate(${r.position.x_m},${r.position.y_m}) rotate(${r.position.heading_deg})">
        <path d="M0,-6 L4,5 L-4,5 Z" class="fov-fill" transform="scale(3.4) translate(0,0)" opacity="0.10"/>
        <path d="M0,-4 L3,3.2 L-3,3.2 Z" />
      </g>
      <text x="${r.position.x_m + 6}" y="${r.position.y_m - 6}" class="map-rover-coords">X ${F.num(r.position.x_m, 1)} Y ${F.num(r.position.y_m, 1)}</text>
    `;

    const contentGroup = svg.querySelector('.map-content') || svg;
    contentGroup.innerHTML = html;

    // wire click handlers
    svg.querySelectorAll('[data-node]').forEach((elx) => {
      elx.addEventListener('click', () => {
        const n = m.nodes.find((x) => x.id === elx.dataset.node);
        selectMarker('node', n.id, { x_m: n.x_m, y_m: n.y_m });
      });
    });
    svg.querySelectorAll('[data-detection]').forEach((elx) => {
      elx.addEventListener('click', () => {
        const d = m.detections.find((x) => x.id === elx.dataset.detection);
        selectMarker('detection', d.id, d.position);
      });
    });
    svg.querySelectorAll('[data-hazard]').forEach((elx) => {
      elx.addEventListener('click', () => {
        const h = mapGeo.hazards.find((x) => x.id === elx.dataset.hazard);
        selectMarker('hazard', h.id, { x_m: h.x_m, y_m: h.y_m });
      });
    });

    renderLegend(layers);
    renderScalebar();
  }

  function renderLegend(layers) {
    const el = wrapEl.querySelector('.map-legend');
    const rows = [
      ['occupancy', 'Occupancy'], ['trail', 'Trail'], ['nodesCoverage', 'Nodes / Coverage'],
      ['temperature', 'Temperature'], ['detections', 'Detections'], ['hazards', 'Hazards'],
      ['annotations', 'Annotations'], ['route', 'Route'],
    ];
    el.innerHTML = rows.filter(([k]) => layers[k]).map(([, label]) => `\u2611 ${label}`).join('<br/>');
  }

  function renderScalebar() {
    const el = wrapEl.querySelector('.map-scalebar');
    const pxPerUnit = wrapEl.clientWidth / viewBox.w;
    const targetPx = 80;
    const niceMeters = Math.max(5, Math.round((targetPx / pxPerUnit) / 5) * 5);
    const px = niceMeters * pxPerUnit;
    el.innerHTML = `<div class="map-scalebar__bar" style="width:${px}px"></div><div class="map-scalebar__label">${niceMeters}m</div>`;
  }

  function zoom(factor) {
    const cx = viewBox.x + viewBox.w / 2;
    const cy = viewBox.y + viewBox.h / 2;
    viewBox = { x: 0, y: 0, w: viewBox.w * factor, h: viewBox.h * factor };
    viewBox.x = cx - viewBox.w / 2;
    viewBox.y = cy - viewBox.h / 2;
    render(window.MSW_STORE.getState());
  }

  function centerOn(x, y, spanFactor) {
    const w = spanFactor ? baseViewBox.w * spanFactor : viewBox.w;
    const h = spanFactor ? baseViewBox.h * spanFactor : viewBox.h;
    viewBox = { x: x - w / 2, y: y - h / 2, w, h };
    render(window.MSW_STORE.getState());
  }

  function centerEntry() {
    viewBox = { ...baseViewBox };
    window.MSW_ACTIONS.setUi({ followRover: false });
    render(window.MSW_STORE.getState());
  }

  function snapshot() {
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svg);
    const canvas = document.createElement('canvas');
    const rect = svg.getBoundingClientRect();
    canvas.width = rect.width * 2; canvas.height = rect.height * 2;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#101417'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const img = new Image();
    const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `minesweeper-map-snapshot-${Date.now()}.png`;
        document.body.appendChild(a); a.click(); a.remove();
      });
    };
    img.src = url;
  }

  function handleClick(evt) {
    // Marker groups (person/node/hazard) attach their own click listeners
    // directly on themselves; a click that lands on one of them still
    // bubbles up to this SVG-level handler, which would otherwise
    // immediately deselect whatever the marker's own listener just
    // selected. Bail out here and let the marker's listener be the only
    // one that acts.
    if (evt.target.closest('[data-node],[data-detection],[data-hazard]')) return;

    const state = window.MSW_STORE.getState();
    const p = toSvgPoint(evt);
    if (state.ui.measureMode) {
      measurePoints.push(p);
      if (measurePoints.length === 2) {
        const d = Math.hypot(measurePoints[1].x - measurePoints[0].x, measurePoints[1].y - measurePoints[0].y);
        wrapEl.querySelector('.map-cursor-readout').textContent = `measured: ${d.toFixed(1)} m`;
        measurePoints = [];
      }
      return;
    }
    if (state.ui.annotateMode) {
      const label = window.prompt('Annotation label:', 'Note');
      if (label) {
        window.MSW_API.addAnnotation({ x_m: p.x, y_m: p.y, label }).catch((e) => console.error(e));
      }
      window.MSW_ACTIONS.setUi({ annotateMode: false });
      return;
    }
    // clicking empty map space deselects
    window.MSW_ACTIONS.setUi({ selectedMarker: null });
  }

  async function mount(el) {
    wrapEl = el;
    wrapEl.innerHTML = `
      <div class="map-canvas-wrap">
        <svg></svg>
        <div class="map-cursor-readout">cursor x -- y --</div>
        <div class="map-legend"></div>
        <div class="map-scalebar"></div>
        <div class="comms-lost-banner"></div>
      </div>
    `;
    svg = wrapEl.querySelector('svg');
    svg.innerHTML = `
      <defs>
        <pattern id="unexploredHatch" width="4" height="4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <rect width="4" height="4" fill="#14181B" />
          <line x1="0" y1="0" x2="0" y2="4" stroke="#232A30" stroke-width="1.4" />
        </pattern>
      </defs>
      <g class="map-content"></g>
    `;
    svg.addEventListener('click', handleClick);
    svg.addEventListener('mousemove', (evt) => {
      const p = toSvgPoint(evt);
      wrapEl.querySelector('.map-cursor-readout').textContent = `cursor x ${p.x.toFixed(1)} y ${p.y.toFixed(1)}`;
    });

    try {
      mapGeo = await window.MSW_API.getMap();
    } catch (e) {
      console.error('failed to load map geometry', e);
      mapGeo = { main_path: [], dead_end_branch: [], hazards: [], gallery_half_width_m: 9, dead_end_half_width_m: 7 };
    }

    window.MSW_STORE.subscribe((state) => {
      render(state);
      const banner = wrapEl.querySelector('.comms-lost-banner');
      const lost = state.mission && state.mission.link.status === 'LOST';
      banner.classList.toggle('active', !!lost);
      if (lost) {
        banner.textContent = `RESTORE COMMUNICATION: Rover unreachable \u00b7 last contact ${Math.round(state.mission.link.last_contact_age_s)}s ago \u00b7 beyond ${state.mission.link.unreachable_beyond}`;
      }

      // "go to selected marker" needs live access to current selection -> exposed via controller
      window.MSW_MAP_CONTROLLER.selectedMarkerPosition = state.ui.selectedMarker ? state.ui.selectedMarker.position : null;

      if (state.ui.selectedMarker && state.ui.selectedMarker.centerRequestId) {
        const p = state.ui.selectedMarker.position;
        if (p) centerOn(p.x_m, p.y_m, 0.35);
      }
    });
    render(window.MSW_STORE.getState());
  }

  window.MSW_MAP_CONTROLLER = {
    zoomIn: () => zoom(0.8),
    zoomOut: () => zoom(1.25),
    centerEntry,
    snapshot,
    selectedMarkerPosition: null,
  };

  return { mount };
})();
