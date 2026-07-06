'use strict';

const RAMP = ['#440154','#414487','#2A788E','#22A884','#7AD151','#BDDF26','#FDE725'];
const BREAKS = [0.20, 0.35, 0.50, 0.65, 0.80, 0.92];
const NO_DATA = '#1A2030';
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Scrubber stops = 8 cumulative thresholds (drive the map)
const THRESHOLDS = [
  { label: '3h',  cum: 0, long: '3 hours' },
  { label: '24h', cum: 1, long: '24 hours' },
  { label: '2d',  cum: 2, long: '2 days' },
  { label: '3d',  cum: 3, long: '3 days' },
  { label: '1w',  cum: 4, long: '1 week' },
  { label: '2w',  cum: 5, long: '2 weeks' },
  { label: '20d', cum: 6, long: '20 days' },
  { label: '31d', cum: 7, long: '31 days' },
];
// Ladder rows = 8 cumulative + 1 month-plus tail
const LADDER = [
  { label: '3 hours',  cum: 0 }, { label: '24 hours', cum: 1 },
  { label: '2 days',   cum: 2 }, { label: '3 days',   cum: 3 },
  { label: '1 week',   cum: 4 }, { label: '2 weeks',  cum: 5 },
  { label: '20 days',  cum: 6 }, { label: '31 days',  cum: 7 },
  { label: '1 month+', tail: true },
];
const NYC_BOUNDS = [[-74.30, 40.45], [-73.65, 40.95]];
const BORO_BOUNDS = {
  'Manhattan': [[-74.02, 40.70], [-73.91, 40.88]],
  'Bronx': [[-73.93, 40.79], [-73.77, 40.92]],
  'Brooklyn': [[-74.05, 40.57], [-73.83, 40.74]],
  'Queens': [[-73.96, 40.54], [-73.70, 40.80]],
  'Staten Island': [[-74.26, 40.49], [-74.05, 40.65]],
  'All NYC': NYC_BOUNDS,
};

const state = { meta: null, probs: null, geo: null, bboxes: {}, boroOf: {},
  type: 'ALL', thr: 1, selected: null, playing: false, playTimer: null,
  shading: 'absolute', boro: 'All NYC' };

function percentile(sorted, q) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function classColor(p) {
  if (p == null || isNaN(p)) return NO_DATA;
  for (let i = 0; i < BREAKS.length; i++) if (p < BREAKS[i]) return RAMP[i];
  return RAMP[RAMP.length - 1];
}
function lighten(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt;
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}
function cumsum(bp) { const c = []; let s = 0; for (const x of bp) { s += x; c.push(s); } return c; }
function pct(x) { return Math.round(x * 100) + '%'; }
function cell(geoid, type) { const t = state.probs[geoid]; return t ? t[type] : null; }

/* ---------------- Map ---------------- */
const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      carto: { type: 'raster', tiles: ['https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png'],
        tileSize: 256, attribution: '© OpenStreetMap © CARTO' },
      labels: { type: 'raster', tiles: ['https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png'],
        tileSize: 256 },
    },
    layers: [{ id: 'carto', type: 'raster', source: 'carto' }],
  },
  center: reduceMotion ? [-73.94, 40.70] : [-74.02, 40.63],
  zoom: reduceMotion ? 9.7 : 8.6,
  minZoom: 9, maxZoom: 15, maxBounds: [[-74.35, 40.42], [-73.60, 40.98]],
  attributionControl: { compact: true },
});

async function boot() {
  const [meta, probs, geo] = await Promise.all([
    fetch('data/meta.json').then(r => r.json()),
    fetch('data/probs.json').then(r => r.json()),
    fetch('data/tracts.geojson').then(r => r.json()),
  ]);
  state.meta = meta; state.probs = probs; state.geo = geo;
  for (const f of geo.features) {
    state.bboxes[f.properties.geoid] = bbox(f.geometry);
    state.boroOf[f.properties.geoid] = f.properties.boro;
  }

  // Wait for the style spec to be *parsed* (what addSource needs) — not for all
  // basemap tiles to finish, which isStyleLoaded()/load require and which can stay
  // pending indefinitely in throttled/backgrounded render loops.
  const styleReady = () => { try { return (map.style && map.style._loaded) || map.isStyleLoaded(); } catch (_) { return false; } };
  await new Promise(res => {
    if (styleReady()) return res();
    const iv = setInterval(() => { if (styleReady()) { clearInterval(iv); res(); } }, 50);
    map.on('style.load', () => { clearInterval(iv); res(); });
  });
  map.addSource('tracts', { type: 'geojson', data: geo, promoteId: 'geoid' });
  map.addLayer({
    id: 'tract-fill', type: 'fill', source: 'tracts',
    paint: {
      'fill-color': ['case', ['==', ['feature-state', 'p'], null], NO_DATA,
        ['step', ['coalesce', ['feature-state', 'p'], 0],
          RAMP[0], BREAKS[0], RAMP[1], BREAKS[1], RAMP[2], BREAKS[2],
          RAMP[3], BREAKS[3], RAMP[4], BREAKS[4], RAMP[5], BREAKS[5], RAMP[6]]],
      'fill-opacity': reduceMotion ? 0.78 : 0,
      'fill-color-transition': { duration: 450, delay: 0 },
      'fill-opacity-transition': { duration: 800, delay: 0 },
    },
  }, 'carto');
  map.moveLayer('tract-fill');
  map.addLayer({ id: 'tract-line', type: 'line', source: 'tracts',
    paint: { 'line-color': '#0B0E14', 'line-width': 0.5, 'line-opacity': 0.4 } });
  map.addLayer({ id: 'tract-glow', type: 'line', source: 'tracts',
    paint: { 'line-blur': 4, 'line-width': 2,
      'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#FFB84D', '#FFFFFF'],
      'line-opacity': ['case', ['any', ['boolean', ['feature-state', 'hover'], false],
        ['boolean', ['feature-state', 'selected'], false]], 0.9, 0] } });
  map.addLayer({ id: 'tract-hover-line', type: 'line', source: 'tracts',
    paint: { 'line-width': 1.5,
      'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#FFB84D', '#FFFFFF'],
      'line-opacity': ['case', ['any', ['boolean', ['feature-state', 'hover'], false],
        ['boolean', ['feature-state', 'selected'], false]], 0.85, 0] } });
  map.addLayer({ id: 'labels', type: 'raster', source: 'labels' });

  buildScrubber(); buildLegend(); buildChips();
  wireInteractions();
  document.getElementById('loading').classList.add('hidden');  // show UI immediately

  paintWhenReady();          // colors the map as soon as the render loop is live
  restoreFromURL();
  if (!reduceMotion) {
    map.flyTo({ center: [-73.94, 40.70], zoom: 9.7, duration: 1800, essential: true });
    map.setPaintProperty('tract-fill', 'fill-opacity', 0.78);
  }
}

/* ---------------- Choropleth ---------------- */
// setFeatureState throws until the style is fully live; retry until the first
// paint succeeds (handles paused/backgrounded render loops gracefully).
function paintWhenReady() {
  updateLegendCaption();
  try { applyFeatureStates(); }
  catch (_) { map.once('idle', paintWhenReady); setTimeout(paintWhenReady, 250); }
}
// Safe to call from any UI handler: never throws, so panel/legend updates that
// follow it always run even if the map paint has to be deferred.
function paintMap() {
  updateLegendCaption();
  try { applyFeatureStates(); }
  catch (_) { map.once('idle', () => { try { applyFeatureStates(); } catch (e) {} }); }
}
function applyFeatureStates() {
  const cIdx = THRESHOLDS[state.thr].cum;
  // raw cumulative "within X" per tract for the current type
  const raw = {};
  for (const geoid in state.probs) {
    const c = cell(geoid, state.type);
    raw[geoid] = c ? cumsum(c.bp)[cIdx] : null;
  }

  // In relative mode, stretch the ramp across the values in the current view
  // (the focused borough, or the whole city) so within-type variation is visible.
  let lo = 0, hi = 1;
  if (state.shading === 'relative') {
    const scope = [];
    for (const geoid in raw) {
      if (raw[geoid] == null) continue;
      if (state.boro !== 'All NYC' && state.boroOf[geoid] !== state.boro) continue;
      scope.push(raw[geoid]);
    }
    scope.sort((a, b) => a - b);
    lo = percentile(scope, 0.02);
    hi = percentile(scope, 0.98);
    if (hi - lo < 0.01) hi = lo + 0.01;  // avoid divide-by-zero on uniform types
  }
  state.viewRange = { lo, hi };
  updateLegendRange();

  const span = hi - lo;
  for (const geoid in raw) {
    const r = raw[geoid];
    const shown = r == null ? null
      : state.shading === 'relative' ? Math.max(0, Math.min(1, (r - lo) / span)) : r;
    map.setFeatureState({ source: 'tracts', id: geoid }, { p: shown });
  }
}

/* ---------------- Scrubber ---------------- */
function buildScrubber() {
  const wrap = document.getElementById('scrub-segments');
  wrap.innerHTML = '';
  THRESHOLDS.forEach((t, i) => {
    const b = document.createElement('button');
    b.className = 'seg' + (i === state.thr ? ' active' : '');
    b.textContent = t.label; b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', i === state.thr);
    b.onclick = () => setThreshold(i);
    wrap.appendChild(b);
  });
}
function setThreshold(i) {
  state.thr = i;
  document.querySelectorAll('.seg').forEach((s, j) => {
    s.classList.toggle('active', j === i); s.setAttribute('aria-checked', j === i);
  });
  paintMap();
  if (state.selected) {
    const c = cell(state.selected, state.type);
    const cum = cumsum(c.bp);
    const strength = c.n >= 150 ? 2 : c.n >= 25 ? 1 : c.n > 0 ? 0 : -1;
    const props = state.geo.features.find(f => f.properties.geoid === state.selected).properties;
    updateHeadline(c, cum, strength, false);
    renderCompare(state.selected, props, cum);
    syncLadderActive();
  }
  pushURL();
}

/* ---------------- Legend ---------------- */
function buildLegend() {
  const sw = document.getElementById('legend-swatches');
  sw.innerHTML = '';
  RAMP.forEach(c => { const d = document.createElement('div'); d.style.background = c; sw.appendChild(d); });
}
function typeCaption() {
  const t = state.type;
  if (t === 'ALL') return 'a 311 request';
  const name = t.toLowerCase().replace('heat/hot water', 'heat/hot-water');
  const article = /^[aeiou]/.test(name) ? 'an' : 'a';
  return `${article} ${name} request`;
}
function updateLegendCaption() {
  const suffix = state.shading === 'relative' ? ' — colors stretched to this view' : '';
  document.getElementById('legend-caption').textContent =
    `Chance ${typeCaption()} is resolved within ${THRESHOLDS[state.thr].long}${suffix}`;
}
function updateLegendRange() {
  const [lo, mid, hi] = ['legend-lo', 'legend-mid', 'legend-hi'].map(id => document.getElementById(id));
  if (state.shading === 'relative' && state.viewRange) {
    const { lo: a, hi: b } = state.viewRange;
    lo.textContent = pct(a); mid.textContent = pct((a + b) / 2); hi.textContent = pct(b);
  } else { lo.textContent = '0%'; mid.textContent = '50%'; hi.textContent = '100%'; }
}

/* ---------------- Chips ---------------- */
const COMMON = ['ALL', 'Noise - Residential', 'HEAT/HOT WATER', 'Illegal Parking',
  'UNSANITARY CONDITION', 'Street Condition', 'Blocked Driveway'];
function nice(t) {
  if (t === 'ALL') return 'All';
  return t.split(' ').map(w => w.length > 3 ? w[0] + w.slice(1).toLowerCase() : w)
    .join(' ').replace('Heat/hot', 'Heat/Hot');
}
function buildChips() {
  ['header-chips', 'chips'].forEach(id => buildChipRow(document.getElementById(id)));
  syncChips();
}
function buildChipRow(wrap) {
  wrap.innerHTML = '';
  const shown = COMMON.filter(t => state.meta.types.includes(t));
  const rest = state.meta.types.filter(t => !shown.includes(t));
  shown.forEach(t => wrap.appendChild(makeChip(t)));
  if (rest.length) {
    const more = document.createElement('select');
    more.className = 'chip more-select'; more.style.appearance = 'none';
    more.innerHTML = '<option value="">More ▾</option>' +
      rest.map(t => `<option value="${t}">${nice(t)}</option>`).join('');
    more.onchange = () => { if (more.value) setType(more.value); };
    wrap.appendChild(more);
  }
}
function makeChip(t) {
  const c = document.createElement('button');
  c.className = 'chip' + (t === state.type ? ' active' : '');
  c.textContent = nice(t); c.dataset.type = t;
  c.setAttribute('role', 'radio'); c.onclick = () => setType(t);
  return c;
}
function syncChips() {
  document.querySelectorAll('.chip[data-type]').forEach(c =>
    c.classList.toggle('active', c.dataset.type === state.type));
  const isRest = !COMMON.includes(state.type);
  document.querySelectorAll('.more-select').forEach(s => {
    s.value = isRest ? state.type : '';
    s.classList.toggle('active', isRest);
  });
}
function setType(t) {
  state.type = t;
  syncChips();
  paintMap();
  if (state.selected) renderPanel(state.selected);
  pushURL();
}

/* ---------------- Selection & panel ---------------- */
function setFS(id, obj) { try { map.setFeatureState({ source: 'tracts', id }, obj); } catch (_) {} }
function selectTract(geoid, fly = true) {
  if (state.selected) setFS(state.selected, { selected: false });
  state.selected = geoid;
  setFS(geoid, { selected: true });
  document.getElementById('panel').classList.add('open');
  document.getElementById('panel').setAttribute('aria-hidden', 'false');
  document.body.classList.add('panel-open');
  document.getElementById('hint').classList.add('hidden');
  renderPanel(geoid);
  if (fly && state.bboxes[geoid]) {
    const b = state.bboxes[geoid];
    map.fitBounds(b, { padding: { top: 60, bottom: 60, left: 60, right: 440 },
      maxZoom: 13.5, duration: reduceMotion ? 0 : 900 });
  }
  pushURL();
}
function deselect() {
  if (state.selected) setFS(state.selected, { selected: false });
  state.selected = null;
  document.getElementById('panel').classList.remove('open');
  document.getElementById('panel').setAttribute('aria-hidden', 'true');
  document.body.classList.remove('panel-open');
  document.getElementById('hint').classList.remove('hidden');
  pushURL();
}

function renderPanel(geoid) {
  const feat = state.geo.features.find(f => f.properties.geoid === geoid);
  const props = feat.properties;
  const c = cell(geoid, state.type);
  document.getElementById('tract-name').textContent = 'Census Tract ' + tractLabel(geoid);
  document.getElementById('tract-nta').textContent = props.nta || '';
  const cum = cumsum(c.bp);
  const allN = cell(geoid, 'ALL').n;
  document.getElementById('tract-meta').textContent =
    `${props.boro} · ${allN.toLocaleString()} requests since 2025`;

  // borrowing banner for sparse cells (honest shrinkage story)
  const banner = document.getElementById('zero-banner');
  const label = state.type === 'ALL' ? '311' : nice(state.type).toLowerCase();
  if (c.n === 0) {
    banner.hidden = false;
    banner.textContent = `No ${label} requests recorded in this tract — showing the model's estimate based on ${props.nta} and ${props.boro}.`;
  } else if (c.n < 25) {
    banner.hidden = false;
    banner.textContent = `Only ${c.n} ${label} request${c.n === 1 ? '' : 's'} in this tract — this estimate leans on ${props.nta} and ${props.boro} patterns.`;
  } else banner.hidden = true;

  // strength
  const strength = c.n >= 150 ? 2 : c.n >= 25 ? 1 : c.n > 0 ? 0 : -1;
  renderStrength(strength, c, props);

  updateHeadline(c, cum, strength, true);
  renderLadder(geoid, c, cum);
  renderCompare(geoid, props, cum);
}

// Headline stat + caption + compare strip all track the active scrubber threshold.
function updateHeadline(c, cum, strength, animate) {
  const cIdx = THRESHOLDS[state.thr].cum;
  const val = cum[cIdx];
  const numEl = document.getElementById('stat-number');
  numEl.style.color = classColor(val);
  const prefix = strength <= 0 && c.n < 25 ? '~' : '';
  if (animate) countUp(numEl, val, prefix); else numEl.textContent = prefix + pct(val);
  document.getElementById('stat-caption').textContent =
    `chance it's resolved within ${THRESHOLDS[state.thr].long}`;
}

function renderStrength(level, c, props) {
  const dots = document.getElementById('strength-dots');
  const label = document.getElementById('strength-label');
  const filled = level < 0 ? 0 : level + 1;
  const cls = level === 0 ? 'on-warn' : 'on-good';
  dots.innerHTML = [0, 1, 2].map(i =>
    `<span class="${i < filled ? cls : ''}"></span>`).join('');
  const labels = ['Limited local data', 'Good local data', 'Strong local data'];
  label.textContent = level < 0 ? 'No local data' : labels[level];
  dots.title = `With ${c.n.toLocaleString()} requests of this type here, our model blends this tract's history with its neighborhood and borough. Fewer local reports = more blending, and a wider plausible range.`;
}

function renderLadder(geoid, c, cum) {
  const wrap = document.getElementById('ladder');
  wrap.innerHTML = '';
  const cIdx = THRESHOLDS[state.thr].cum;
  LADDER.forEach((row, ri) => {
    const isTail = !!row.tail;
    const value = isTail ? c.bp[8] : cum[row.cum];
    const lo = isTail ? Math.max(0, 1 - c.hi[7]) : c.lo[row.cum];
    const hi = isTail ? Math.min(1, 1 - c.lo[7]) : c.hi[row.cum];
    const inc = isTail ? c.bp[8] : c.bp[row.cum];
    // Tail row means "still unresolved after a month" — the opposite reading of the
    // cumulative rows — so it gets a distinct red outside the viridis ramp instead
    // of a ramp color (which made it look identical to the low "3 hours" row).
    const col = isTail ? '#C95C5C' : classColor(value);
    const active = !isTail && row.cum === cIdx;

    const div = document.createElement('div');
    div.className = 'lrow' + (active ? ' active' : '');
    div.innerHTML = `<div class="rlabel">${row.label}</div>
      <div class="track">
        <div class="cifade" style="left:${lo * 100}%;width:${(hi - lo) * 100}%;
          background:linear-gradient(90deg, ${col}, transparent);"></div>
        <div class="fill" style="width:${value * 100}%;background:${col};"></div>
        <div class="cap" style="left:${Math.max(0, (value - inc)) * 100}%;
          width:${Math.min(inc, value) * 100}%;background:${lighten(col, 0.35)};opacity:.5;"></div>
        <div class="pmarker" style="left:${value * 100}%;"></div>
        <div class="plabel ${value < 0.16 ? 'out' : ''}" style="${value < 0.16 ? 'left:' + (value * 100) + '%;padding-left:6px;' : ''}">${pct(value)}</div>
      </div>`;
    wrap.appendChild(div);
    const fill = div.querySelector('.fill');
    if (reduceMotion) {
      fill.style.width = (value * 100) + '%';
    } else {
      fill.style.width = '0%';
      setTimeout(() => { fill.style.width = (value * 100) + '%'; }, 40 * ri + 20);
    }
  });
  syncLadderActive();
}
function syncLadderActive() {
  const cIdx = THRESHOLDS[state.thr].cum;
  document.querySelectorAll('.lrow').forEach((r, i) =>
    r.classList.toggle('active', i < 8 && LADDER[i].cum === cIdx));
  // reference ticks on active row
  document.querySelectorAll('.reftick').forEach(t => t.remove());
  if (!state.selected) return;
  const props = state.geo.features.find(f => f.properties.geoid === state.selected).properties;
  const boroRef = state.meta.refs.boro[props.boro]?.[state.type];
  const cityRef = state.meta.refs.city[state.type];
  const active = document.querySelectorAll('.lrow')[state.thr];
  if (!active || cIdx > 7) return;
  const track = active.querySelector('.track');
  if (boroRef) addTick(track, boroRef[cIdx], 'boro');
  if (cityRef) addTick(track, cityRef[cIdx], 'city');
}
function addTick(track, v, cls) {
  const t = document.createElement('div');
  t.className = 'reftick ' + cls; t.style.left = (v * 100) + '%';
  track.appendChild(t);
}

function renderCompare(geoid, props, cum) {
  const cIdx = THRESHOLDS[state.thr].cum;
  const me = cum[cIdx];
  const boro = state.meta.refs.boro[props.boro]?.[state.type]?.[cIdx];
  const city = state.meta.refs.city[state.type]?.[cIdx];
  const d = (a, b) => {
    const diff = Math.round((a - b) * 100);
    const cls = diff >= 0 ? 'delta-up' : 'delta-down';
    return ` <span class="${cls}">${diff >= 0 ? '▲' : '▼'}${Math.abs(diff)} pts</span>`;
  };
  document.getElementById('compare').innerHTML =
    `<span class="me">This tract ${pct(me)}</span>` +
    (boro != null ? ` · ${props.boro} ${pct(boro)}${d(me, boro)}` : '') +
    (city != null ? ` · NYC ${pct(city)}` : '');
}

function countUp(el, target, prefix) {
  if (reduceMotion) { el.textContent = prefix + pct(target); return; }
  const start = performance.now(), dur = 700;
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    const e = 1 - Math.pow(1 - t, 3);
    el.textContent = prefix + Math.round(e * target * 100) + '%';
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ---------------- Interactions ---------------- */
let hovered = null;
function wireInteractions() {
  map.on('mousemove', 'tract-fill', e => {
    if (!e.features.length) return;
    const id = e.features[0].id;
    if (hovered && hovered !== id) map.setFeatureState({ source: 'tracts', id: hovered }, { hover: false });
    hovered = id;
    map.setFeatureState({ source: 'tracts', id }, { hover: true });
    map.getCanvas().style.cursor = 'pointer';
    showTooltip(e, id);
  });
  map.on('mouseleave', 'tract-fill', () => {
    if (hovered) map.setFeatureState({ source: 'tracts', id: hovered }, { hover: false });
    hovered = null; map.getCanvas().style.cursor = ''; hideTooltip();
  });
  map.on('click', 'tract-fill', e => {
    if (!e.features.length) return;
    const id = e.features[0].id;
    if (id === state.selected) deselect();      // click selected tract again to clear
    else selectTract(id);
  });
  map.on('click', e => {
    const f = map.queryRenderedFeatures(e.point, { layers: ['tract-fill'] });
    if (!f.length) deselect();
  });
  document.getElementById('panel-close').onclick = deselect;
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') deselect();
    if (e.key === 'ArrowLeft') setThreshold(Math.max(0, state.thr - 1));
    if (e.key === 'ArrowRight') setThreshold(Math.min(THRESHOLDS.length - 1, state.thr + 1));
  });
  document.getElementById('header-collapse').onclick = () =>
    document.getElementById('header').classList.toggle('collapsed');
  document.querySelectorAll('.boro-btn').forEach(b => b.onclick = () => {
    document.querySelectorAll('.boro-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.boro = b.dataset.boro;
    map.fitBounds(BORO_BOUNDS[state.boro], { padding: 40, duration: 900 });
    if (state.shading === 'relative') paintMap();  // re-stretch to the focused borough
  });
  document.querySelectorAll('.legend-toggle button[data-shade]').forEach(b => b.onclick = () => {
    state.shading = b.dataset.shade;
    document.querySelectorAll('.legend-toggle button[data-shade]').forEach(x => {
      const on = x === b; x.classList.toggle('active', on); x.setAttribute('aria-checked', on);
    });
    paintMap();
  });
  const helpBtn = document.getElementById('legend-help');
  const hint = document.getElementById('legend-hint');
  helpBtn.onclick = () => {
    hint.hidden = !hint.hidden;
    helpBtn.setAttribute('aria-expanded', String(!hint.hidden));
  };
  document.getElementById('play').onclick = togglePlay;
  wireSearch();
}

let tip;
function showTooltip(e, id) {
  const feat = state.geo.features.find(f => f.properties.geoid === id);
  if (!feat) return;
  const c = cell(id, state.type); if (!c) return;
  const cum = cumsum(c.bp); const cIdx = THRESHOLDS[state.thr].cum;
  const v = cum[cIdx], lo = c.lo[cIdx], hi = c.hi[cIdx];
  if (!tip) { tip = document.createElement('div'); tip.id = 'tooltip'; document.body.appendChild(tip);
    Object.assign(tip.style, { position: 'fixed', maxWidth: '240px', background: 'rgba(26,32,48,0.92)',
      backdropFilter: 'blur(8px)', border: '1px solid #2A3244', borderRadius: '8px',
      padding: '10px 12px', pointerEvents: 'none', zIndex: 40, fontSize: '12px' }); }
  tip.innerHTML = `<div style="font-weight:600;color:#F2F4F8;margin-bottom:3px">Tract ${tractLabel(id)} · ${feat.properties.nta}</div>
    <div style="font-size:13px;font-weight:700;color:${classColor(v)}">${pct(v)} chance resolved within ${THRESHOLDS[state.thr].long}</div>
    <div style="font-size:11px;color:#5C6577;margin-top:3px">Plausible range ${pct(lo)}–${pct(hi)} · ${c.n.toLocaleString()} requests</div>`;
  let x = e.originalEvent.clientX + 14, y = e.originalEvent.clientY + 14;
  if (x > window.innerWidth - 250) x = e.originalEvent.clientX - 250;
  tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.style.display = 'block';
}
function hideTooltip() { if (tip) tip.style.display = 'none'; }

function togglePlay() {
  const btn = document.getElementById('play');
  if (state.playing) { clearInterval(state.playTimer); state.playing = false;
    btn.classList.remove('playing'); btn.textContent = '▶'; return; }
  state.playing = true; btn.classList.add('playing'); btn.textContent = '❚❚';
  let i = 0; setThreshold(0);
  state.playTimer = setInterval(() => {
    i++;
    if (i >= THRESHOLDS.length) { togglePlay(); return; }
    setThreshold(i);
  }, 1400);
}

/* ---------------- Search (Nominatim) ---------------- */
function wireSearch() {
  const input = document.getElementById('search');
  const results = document.getElementById('search-results');
  let timer;
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { results.classList.remove('show'); return; }
    timer = setTimeout(async () => {
      const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&bounded=1&limit=5&viewbox=-74.30,40.95,-73.65,40.45&q=${encodeURIComponent(q)}`;
      try {
        const data = await fetch(url, { headers: { 'Accept-Language': 'en' } }).then(r => r.json());
        results.innerHTML = '';
        if (!data.length) { results.innerHTML = "<div>Couldn't find that in New York City — try a street + borough.</div>"; results.classList.add('show'); return; }
        data.forEach(d => {
          const el = document.createElement('div');
          el.textContent = d.display_name.replace(', United States', '');
          el.onclick = () => { results.classList.remove('show'); input.value = d.display_name.split(',')[0];
            goToPoint(+d.lon, +d.lat); };
          results.appendChild(el);
        });
        results.classList.add('show');
      } catch (_) { /* offline: ignore */ }
    }, 400);
  };
  document.addEventListener('click', e => { if (!input.parentNode.contains(e.target)) results.classList.remove('show'); });
}
function goToPoint(lon, lat) {
  map.flyTo({ center: [lon, lat], zoom: 13, duration: 1100 });
  const geoid = findTract(lon, lat);
  if (geoid) setTimeout(() => selectTract(geoid, false), reduceMotion ? 0 : 700);
}

/* ---------------- Geometry helpers ---------------- */
function bbox(geom) {
  let minX = 180, minY = 90, maxX = -180, maxY = -90;
  const scan = ring => ring.forEach(([x, y]) => {
    if (x < minX) minX = x; if (y < minY) minY = y; if (x > maxX) maxX = x; if (y > maxY) maxY = y; });
  (geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates).forEach(poly => poly.forEach(scan));
  return [[minX, minY], [maxX, maxY]];
}
function findTract(lon, lat) {
  for (const f of state.geo.features) {
    const b = state.bboxes[f.properties.geoid];
    if (lon < b[0][0] || lon > b[1][0] || lat < b[0][1] || lat > b[1][1]) continue;
    if (pointInGeom(lon, lat, f.geometry)) return f.properties.geoid;
  }
  return null;
}
function pointInGeom(x, y, geom) {
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
  return polys.some(poly => {
    if (!inRing(x, y, poly[0])) return false;
    for (let i = 1; i < poly.length; i++) if (inRing(x, y, poly[i])) return false;
    return true;
  });
}
function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function tractLabel(geoid) {
  const n = parseInt(geoid.slice(-6), 10) / 100;  // census tract code, e.g. 002201 -> 22.01
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

/* ---------------- URL state ---------------- */
function pushURL() {
  const p = new URLSearchParams();
  if (state.selected) p.set('tract', state.selected);
  if (state.type !== 'ALL') p.set('type', state.type);
  if (state.thr !== 1) p.set('t', THRESHOLDS[state.thr].label);
  history.replaceState(null, '', p.toString() ? '?' + p.toString() : location.pathname);
}
function restoreFromURL() {
  const p = new URLSearchParams(location.search);
  const type = p.get('type'); if (type && state.meta.types.includes(type)) setType(type);
  const t = p.get('t'); if (t) { const i = THRESHOLDS.findIndex(x => x.label === t); if (i >= 0) setThreshold(i); }
  const tr = p.get('tract'); if (tr && state.probs[tr]) selectTract(tr);
}

window.map = map; window.appState = state;
boot().catch(e => { console.error('boot failed:', e);
  document.querySelector('#loading div:last-child').textContent = 'Error: ' + e.message; });
