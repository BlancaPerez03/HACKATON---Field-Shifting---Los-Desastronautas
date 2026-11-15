// Field Shift viewer: one Leaflet map, parcels, four environmental layers + risk zones, cursor
// inspector, and the scenario simulator (POST /api/parcel/simulate, contract sim-1).
"use strict";   // makes JavaScript throw errors for common mistakes (e.g. using an undeclared variable)

// Big picture of this file:
//   init() loads the demo parcels, the crop catalogue and layers.json, draws the map, then
//   analyzes every parcel. Every user action (click a parcel, move a slider, toggle a layer)
//   updates one of the four state objects below and calls the matching render function.
//   The server does all the science; this file only asks for data and draws it.

const MONTHS =["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CROP_COLORS = { Corn: "#e0b23a", Soybeans: "#5a9e4b", "Winter Wheat": "#b9894a", Alfalfa: "#7fb36a",
  "Fallow/Idle Cropland": "#b8b2a2", Pistachios: "#8a6d3b", Cotton: "#e8e3d8" };
const INDICATOR_TITLES = {
  ndvi: "Vegetation greenness (NDVI)", ndti: "Crop residue index (NDTI)",
  soil_moisture_smap: "Root-zone soil moisture (SMAP)", agroclimate_power: "Agroclimate (NASA POWER)",
  terrain: "Elevation and slope", soil_openlandmap: "Soil properties 0–30 cm",
  precipitation_imerg: "Satellite rainfall (GPM IMERG)", crop_type: "Crop history (CDL)",
};
const DELTA_LABELS = {
  mean_annual_deficit_mm: "Climatic water deficit", remaining_deficit_mm: "Deficit left after irrigation (hyp.)",
  deficit_months: "Months with deficit", et0_annual_mm: "Reference ET0",
  heat_days_per_year: "Heat days (Tmax ≥ 35 °C)", frost_days_le0_per_year: "Frost days (Tmin ≤ 0 °C)",
  frost_days_le2_per_year: "Cold nights (Tmin ≤ 2 °C)", last_spring_frost_p50_doy: "Last spring frost (median)",
  frost_free_days_median: "Frost-free season", rx1day_mm: "Wettest day (Rx1day)", r95p_mm: "Rain on very wet days (R95p)",
  erosion_index: "Erosion screening index",
};
const TYPE_CLASS = { Observed: "t-observed", Reanalysis: "t-reanalysis", Model: "t-model",
  Derived: "t-derived", "Derived + hypothetical": "t-hypothetical", Hypothetical: "t-hypothetical" };

// Small helpers used everywhere:
//   $("map")  -> the element with id="map"
//   esc(text) -> escapes < > & " ' so data is shown as text and never interpreted as HTML (prevents XSS)
//   fmt(v, d) -> number with d decimals, or "—" when the value is missing
//   css(name) -> reads a CSS variable, so charts use the same colours as the page (light and dark mode)
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 0, unit = "") => (v === null || v === undefined || Number.isNaN(v) ? "—" : `${Number(v).toFixed(d)}${unit}`);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------------------------------------------------------------------------------------------
// Data adapter: the only place that talks to the backend. mode = real | demo (mock not needed:
// real data and the precomputed demo cache both work).
const dataSource = {
  // fetch() wrapper: parses the JSON and turns HTTP errors into JS exceptions that carry the
  // backend's error code (e.g. err.code === "BASELINE_NOT_CACHED").
  async get(url, opts) {
    const r = await fetch(url, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(body?.detail?.message || `HTTP ${r.status}`); e.status = r.status; e.code = body?.detail?.code; throw e; }
    return body;
  },
  demoParcels() { return this.get("/api/demo/parcels"); },
  crops() { return this.get("/api/crops"); },
  layers() { return this.get("layers.json"); },
  analyze(geometry) {
    return this.get("/api/parcel/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ geometry }) });
  },
  terrainGrid(hash) { return this.get(`/api/parcel/terrain-grid?hash=${encodeURIComponent(hash)}`); },
  simulate(hash, sc, signal) {
    return this.get("/api/parcel/simulate", { method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geometry_hash: hash, delta_precip_pct: sc.dp, delta_temp_c: sc.dt,
        irrigation_enabled: sc.irrOn, irrigation_availability_pct: sc.irr, crop_id: sc.crop }) });
  },
  recommend(hash, sc, signal) {
    return this.get("/api/parcel/recommend", { method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geometry_hash: hash, delta_precip_pct: sc.dp, delta_temp_c: sc.dt,
        irrigation_enabled: sc.irrOn, irrigation_availability_pct: sc.irr }) });
  },
};

// ---------------------------------------------------------------------------------------------
// State, in four separate parts (+ fetched data). Baseline analyses are never overwritten by a scenario.
// MAP: the single Leaflet map and everything drawn on it (never recreated).
// SELECTION: which parcels are ticked and which one is "active" (shown in detail).
// LAYERS: on/off, opacity and month of each environmental layer.
// SCENARIO: slider values and chosen crop.  DATA: what the server returned.
const MAP = { map: null, parcelLayers: {}, overlays: {}, inspector: null };
const SELECTION = { ids: [], active: null };
const LAYERS = {};          // id -> { visible, opacity, month, meta, status }
const SCENARIO = { dp: 0, dt: 0, irrOn: false, irr: 0, crop: null, riskKind: "erosion", riskView: "scenario" };
// USDA CDL class name -> team catalogue id (to preselect the crop actually grown on the parcel)
const CDL_TO_CROP = { Corn: "corn_maize", Soybeans: "soybean", "Winter Wheat": "winter_wheat", Alfalfa: "alfalfa_hay_perennial",
  Sugarbeets: "sugar_beet", Sugarcane: "sugarcane_perennial", Potatoes: "potato", Sorghum: "sorghum", Cotton: "cotton",
  Rice: "rice", Barley: "barley", Peanuts: "peanut", Tomatoes: "processing_tomato", Grapes: "grape_perennial", Almonds: "almond_perennial" };
const STATUS_TXT = { ok: "✓ Fine", marginal: "! Watch out", limit: "✗ Problem", "n/a": "—" };
const DATA = { parcels: [], crops: null, analyses: {}, grids: {}, sims: {}, seq: 0, ctrl: null, t0: 0, timings: [] };

// ---------------------------------------------------------------------------------------------
async function init() {
  initMap();
  // Promise.all runs the three requests in parallel and waits for all of them.
  const [parcels, crops, layers] = await Promise.all([dataSource.demoParcels(), dataSource.crops(), dataSource.layers()]);
  DATA.parcels = parcels.concat(loadUserParcels()); DATA.crops = crops;
  initPicker();
  // All map layers start hidden: the first screen is just the satellite map and the parcels.
  layers.layers.forEach((m) => { LAYERS[m.id] = { visible: false, opacity: 0.7, month: null, meta: m, status: "" }; });
  drawParcels();
  renderParcelList();
  bindSimulator();
  bindSteps();
  // No parcel is preselected: the user starts by choosing one. Every parcel is analyzed in the
  // background, so the results are usually ready by the time the user gets to step 3.
  setView("pick");
  DATA.parcels.forEach((p) => loadAnalysis(p));
  checkStatus();
  let rt = null;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => MAP.map.invalidateSize(), 150); });
}

// ---------------------------------------------------------------------------------------------
// The three steps: 1 choose a parcel, 2 choose the topics, 3 results (parcel on the side).
const ASPECTS = [
  { id: "reco", name: "What to sow here", desc: "The crops that suit this parcel best, and when to sow them.", essential: true },
  { id: "rotation", name: "Crop rotation plan", desc: "Which crop to grow each year, alternating crops that add nitrogen to the soil with crops that use it.", essential: true },
  { id: "crop", name: "One crop in detail", desc: "Pick a crop and see, point by point, whether this parcel suits it.", essential: true },
  { id: "scenario", name: "A different climate", desc: "What if it rained less or it were warmer? Move two sliders and watch the results change." },
  { id: "money", name: "Money check", desc: "Costs, expected income and how much the harvest can drop before you lose money." },
  { id: "field", name: "Your field at a glance", desc: "Frost dates, rain, soil, slope and the crops grown here in past years." },
  { id: "climate", name: "Climate and water through the year", desc: "Month by month: rain, the water crops need and how green the field is." },
  { id: "catalogue", name: "All crops compared", desc: "A table with every crop in the catalogue and what could go wrong with each one." },
  { id: "layers", name: "Map layers", desc: "Satellite data on the map: vegetation, soil moisture, rain, slope and risk zones." },
  { id: "evidence", name: "Where the data comes from", desc: "Sources, how reliable each one is and the information we are missing." },
];
const ASPECT_KEY = "fieldshift.aspects.v1";
const CHOSEN = new Set(ASPECTS.filter((a) => a.essential).map((a) => a.id));
try { const saved = JSON.parse(localStorage.getItem(ASPECT_KEY) || "null"); if (Array.isArray(saved) && saved.length) { CHOSEN.clear(); saved.forEach((x) => CHOSEN.add(x)); } } catch { /* per-viewer convenience only */ }
const STEPS = ["pick", "aspects", "results"];
let VIEW = "pick";

function bindSteps() {
  document.querySelectorAll("[data-step]").forEach((b) => b.onclick = () => setView(b.dataset.step));
  document.querySelectorAll("[data-goto]").forEach((b) => b.onclick = () => setView(b.dataset.goto));
  $("go-results").onclick = () => setView("results");
  $("aspects-all").onclick = () => { ASPECTS.forEach((a) => CHOSEN.add(a.id)); renderAspects(); };
  $("aspects-essential").onclick = () => { CHOSEN.clear(); ASPECTS.filter((a) => a.essential).forEach((a) => CHOSEN.add(a.id)); renderAspects(); };
  // Charts drawn inside a closed section have no size: redraw them when the section opens.
  document.querySelectorAll("details").forEach((d) => d.addEventListener("toggle", () => {
    if (d.open) { Object.values(charts).forEach((c) => c.resize()); if (VIEW === "results") MAP.map.invalidateSize(); }
  }));
  renderAspects();
}

function renderAspects() {
  $("aspect-list").innerHTML = ASPECTS.map((a) => `<label class="aspect ${CHOSEN.has(a.id) ? "on" : ""}">
      <input type="checkbox" data-aspect-id="${a.id}" ${CHOSEN.has(a.id) ? "checked" : ""}>
      <span><b>${esc(a.name)}</b><span class="small muted">${esc(a.desc)}</span></span></label>`).join("");
  $("aspect-list").querySelectorAll("[data-aspect-id]").forEach((el) => el.onchange = () => {
    if (el.checked) CHOSEN.add(el.dataset.aspectId); else CHOSEN.delete(el.dataset.aspectId);
    el.closest(".aspect").classList.toggle("on", el.checked);
    $("go-results").disabled = !CHOSEN.size;
  });
  $("go-results").disabled = !CHOSEN.size;
  try { localStorage.setItem(ASPECT_KEY, JSON.stringify([...CHOSEN])); } catch { /* ignore */ }
}

function setView(v) {
  if (v !== "pick" && !SELECTION.active) v = "pick";            // steps 2 and 3 need a parcel
  if (v === "results" && !CHOSEN.size) v = "aspects";
  VIEW = v;
  $("app").className = `app view-${v}${CHOSEN.has("layers") ? " layers-on" : ""}`;
  const reached = SELECTION.active ? 2 : 0;
  document.querySelectorAll(".steps .step").forEach((b) => {
    const i = STEPS.indexOf(b.dataset.step);
    b.classList.toggle("current", b.dataset.step === v);
    b.classList.toggle("done", i < STEPS.indexOf(v));
    b.disabled = i > reached;
  });
  if (v === "aspects") renderAspects();
  if (v === "results") applyAspects();
  // The same Leaflet map moves between the big slot (steps 1-2) and the side panel (step 3).
  ($(v === "results" ? "side-map-slot" : "map-slot")).appendChild($("map-wrap"));
  setTimeout(() => { MAP.map.invalidateSize(); if (v === "pick" && !SELECTION.active) fitAll(); else fitSelection(); }, 60);
  window.scrollTo(0, 0);
}

// Show only the chosen topics; the first one opens, the others stay closed until clicked.
function applyAspects() {
  try { localStorage.setItem(ASPECT_KEY, JSON.stringify([...CHOSEN])); } catch { /* ignore */ }
  document.querySelectorAll("[data-aspect]").forEach((el) => { el.hidden = !CHOSEN.has(el.dataset.aspect); });
  let first = true;
  document.querySelectorAll(".rsec").forEach((d) => { if (!d.hidden) { d.open = first; first = false; } });
  if (!CHOSEN.has("scenario") && (SCENARIO.dp || SCENARIO.dt || SCENARIO.irrOn)) $("reset").click();   // no scenario: today's climate
  if (!CHOSEN.has("layers")) { Object.values(LAYERS).forEach((l) => { l.visible = false; }); renderLayerPanel(); buildOverlays(); }
  else renderLayerPanel();
}

function fitAll() {
  const b = L.latLngBounds([]);
  Object.values(MAP.parcelLayers).forEach((l) => b.extend(l.getBounds()));
  if (b.isValid()) MAP.map.fitBounds(b, { padding: [60, 60], maxZoom: 15 });
}

// Card under the parcel list: the parcel just chosen and the button to go on.
function renderChosen() {
  const box = $("chosen"), id = SELECTION.active;
  if (!id) { box.hidden = true; return; }
  const p = DATA.parcels.find((x) => x.id === id), a = DATA.analyses[id];
  const status = !a ? "Getting its data… (a new field takes up to a minute)" : a.error ? `Could not analyze it: ${a.error}` : "Data ready.";
  box.hidden = false;
  box.innerHTML = `<div class="small muted">Chosen parcel</div><b>${esc(p?.name || "")}</b>
    <div class="small muted">${a?.request ? `${fmt(a.request.area_ha, 1)} ha · ` : ""}${esc(status)}</div>
    <button type="button" class="primary" id="go-aspects">Continue: choose what to look at →</button>`;
  $("go-aspects").onclick = () => setView("aspects");
}

function initMap() {
  MAP.map = L.map("map", { zoomControl: true });
  // Basemap: satellite photo tiles from Esri. {z}/{y}/{x} are zoom level and tile row/column.
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Basemap imagery © Esri, Maxar, Earthstar Geographics (display only, not analysis data)",
  }).addTo(MAP.map);
  // Panes are stacking layers: zone polygons (350) sit under the pixel grids (390), which sit
  // under the parcel outlines (Leaflet's default overlay pane is 400). So parcels stay clickable.
  MAP.map.createPane("zones").style.zIndex = 350;
  MAP.map.createPane("grids").style.zIndex = 390;
  L.control.scale({ metric: true, imperial: false }).addTo(MAP.map);
  // Custom Leaflet controls: extend L.Control and return the HTML element from onAdd().
  const Fit = L.Control.extend({ options: { position: "topleft" }, onAdd() {
    const d = L.DomUtil.create("div", "leaflet-bar");
    d.innerHTML = '<a href="#" class="fit" role="button" title="Zoom to selection">Fit selection</a>';
    L.DomEvent.on(d, "click", (e) => { L.DomEvent.preventDefault(e); fitSelection(); });
    return d;
  } });
  MAP.map.addControl(new Fit());
  const Insp = L.Control.extend({ options: { position: "bottomleft" }, onAdd() {
    const d = L.DomUtil.create("div", "inspector");
    d.innerHTML = '<h4>Under the cursor</h4><div class="muted">Move over the map</div>';
    L.DomEvent.disableClickPropagation(d);
    return d;
  } });
  MAP.inspector = new Insp();
  MAP.map.addControl(MAP.inspector);
  MAP.map.setView([42, -93], 6);
  MAP.map.on("zoomend", updateMarkers);
  MAP.map.on("mousemove", (e) => inspect(e.latlng));
  MAP.map.on("click", (e) => inspect(e.latlng));   // touch devices
}

async function loadAnalysis(p) {
  try {
    DATA.analyses[p.id] = await dataSource.analyze(p.geometry);
  } catch (e) {
    DATA.analyses[p.id] = { error: e.message };
  }
  renderParcelList();
  updateMode();
  if (SELECTION.ids.includes(p.id)) onSelectionChanged();   // its data just arrived: draw it and run the scenario
}

// Tell the user when Earth Engine is not configured and how to fix it (one command, see README).
async function checkStatus() {
  try {
    const s = await dataSource.get("/api/status");
    const el = $("setup-note");
    if (!el || s.earth_engine.ready) return;
    el.hidden = false;
    el.innerHTML = `<strong>Earth Engine not configured</strong> · NDVI, SMAP and slope are off; climate (NASA POWER),
      soil (USDA SSURGO) and crop history (USDA CropScape) still work without any login.
      To turn the rest on, stop the server and run <code>python run.py --setup</code> once.`;
  } catch { /* older backend without /api/status */ }
}

// ---------------------------------------------------------------------------------------------
// Parcels and selection
function drawParcels() { DATA.parcels.forEach(drawParcel); }

function drawParcel(p) {
  const lyr = L.geoJSON(p.geometry, { style: () => parcelStyle(p.id) });
  lyr.on("click", (e) => { L.DomEvent.stopPropagation(e); select(p.id, e.originalEvent.shiftKey); });
  lyr.bindTooltip(p.name, { sticky: true });
  lyr.addTo(MAP.map);
  MAP.parcelLayers[p.id] = lyr;
  // A round marker on each parcel so it can be found and clicked when the map is zoomed out
  // (a 60 ha field is invisible at state scale). Hidden when zoomed in close.
  const mk = L.circleMarker(lyr.getBounds().getCenter(), { radius: 9, color: "#ffffff", weight: 2, fillColor: "#ffd84d", fillOpacity: 0.9 })
    .bindTooltip(p.name, { direction: "top" });
  mk.on("click", (e) => { L.DomEvent.stopPropagation(e); select(p.id); });
  (MAP.markers ||= {})[p.id] = mk;
  updateMarkers();
}

function updateMarkers() {
  const show = MAP.map.getZoom() < 13;
  Object.entries(MAP.markers || {}).forEach(([id, mk]) => {
    mk.setStyle({ fillColor: id === SELECTION.active ? "#ffd84d" : "#ffffff", radius: id === SELECTION.active ? 11 : 8 });
    if (show && !MAP.map.hasLayer(mk)) mk.addTo(MAP.map);
    if (!show && MAP.map.hasLayer(mk)) MAP.map.removeLayer(mk);
  });
}

// ---------------------------------------------------------------------------------------------
// Add a real field from the map (team module field-picker.js, attached to this same map)
const USER_KEY = "fieldshift.userParcels.v1";
// localStorage keeps the fields a user added, in their own browser only. It can be blocked
// (private mode), so every access is wrapped in try/catch and the page still works without it.
function loadUserParcels() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || "[]"); } catch { return []; }
}
function saveUserParcels() {
  try { localStorage.setItem(USER_KEY, JSON.stringify(DATA.parcels.filter((p) => p.user))); } catch { /* per-viewer convenience only */ }
}

let PICKER = null, PICKED = null;
function initPicker() {
  if (!window.FieldPicker) { $("add-field").hidden = true; return; }
  // The team's field picker attaches to OUR map (option `map`) and stays inactive until the user
  // presses "Add a field", so its clicks do not interfere with selecting parcels.
  PICKER = FieldPicker.create($("map"), {
    map: MAP.map, active: false, showSearch: true, showPanel: false, maxAreaHa: 1000,
    onSelect(info) { PICKED = info; renderPicked(); },
    onPlace(info) { if (info === PICKED) renderPicked(); },
    onClear() { PICKED = null; renderPicked(); },
  });
  $("add-field").onclick = () => setPicking(!PICKER.isActive());
  $("analyze-field").onclick = analyzePicked;
}

function setPicking(on) {
  PICKER.setActive(on);
  $("add-field").setAttribute("aria-pressed", String(on));
  $("add-field").textContent = on ? "Cancel adding a field" : "+ Add a field from the map";
  $("pick-box").hidden = !on;
  if (on) { PICKED = null; renderPicked(); if (MAP.map.getZoom() < 14) MAP.map.setZoom(14); }
}

function renderPicked() {
  const box = $("pick-info"), btn = $("analyze-field");
  if (!PICKED) { box.textContent = "No field selected yet."; btn.disabled = true; return; }
  const place = PICKED.place ? [PICKED.place.county, PICKED.place.state].filter(Boolean).join(", ") : "locating…";
  const tooBig = PICKED.area.ha > 1000;
  box.innerHTML = `<strong>${fmt(PICKED.area.ha, 2)} ha</strong> (${fmt(PICKED.area.acres, 1)} ac) · ${esc(place)}<br>
    Centre ${PICKED.centroid.lat.toFixed(5)}, ${PICKED.centroid.lon.toFixed(5)} · source: ${esc(PICKED.source)}
    ${PICKED.warnings.map((w) => `<br>⚠ ${esc(w)}`).join("")}`;
  btn.disabled = tooBig;
}

async function analyzePicked() {
  if (!PICKED) return;
  const info = PICKED;
  const place = info.place ? [info.place.county, info.place.state].filter(Boolean).join(", ") : `${info.centroid.lat.toFixed(3)}, ${info.centroid.lon.toFixed(3)}`;
  const label = info.source === "usda_csb" ? "USDA field" : info.source === "drawn" ? "Drawn field" : "Field";
  const p = { id: `user_${Date.now().toString(36)}`, name: `${label} · ${place} (${fmt(info.area.ha, 1)} ha)`,
    geometry: info.geometry, user: true, source: info.source, source_id: info.source_id };
  $("analyze-field").disabled = true;
  const t0 = performance.now();
  // The analysis can take up to a minute: show a live seconds counter so the user knows it is working.
  const tick = setInterval(() => { $("pick-progress").textContent =
    `Analyzing with NASA POWER, Landsat, SMAP, NASADEM, OpenLandMap and CDL… ${Math.round((performance.now() - t0) / 1000)} s (usually 30-60 s the first time)`; }, 500);
  try {
    const a = await dataSource.analyze(p.geometry);
    DATA.analyses[p.id] = a;
    DATA.parcels.push(p);
    saveUserParcels();
    drawParcel(p);
    setPicking(false);
    $("pick-progress").textContent = "";
    select(p.id, false);
    fitSelection();
  } catch (e) {
    $("pick-progress").textContent = `Could not analyze this field: ${e.message}`;
    $("analyze-field").disabled = false;
  } finally {
    clearInterval(tick);
  }
}

function removeUserParcel(id) {
  DATA.parcels = DATA.parcels.filter((p) => p.id !== id);
  if (MAP.parcelLayers[id]) { MAP.map.removeLayer(MAP.parcelLayers[id]); delete MAP.parcelLayers[id]; }
  if (MAP.markers?.[id]) { MAP.map.removeLayer(MAP.markers[id]); delete MAP.markers[id]; }
  delete DATA.analyses[id]; delete DATA.grids[id]; delete DATA.sims[id];
  saveUserParcels();
  SELECTION.ids = SELECTION.ids.filter((x) => x !== id);
  if (!SELECTION.ids.includes(SELECTION.active)) SELECTION.active = SELECTION.ids[0] || null;
  onSelectionChanged();
  if (!SELECTION.active) setView("pick");
}

function parcelStyle(id) {
  // Selected parcels get a thick outline (yellow for the active one); when the NDVI layer is on,
  // the parcel is filled with the colour of its NDVI value for the chosen month.
  const sel = SELECTION.ids.includes(id);
  const L_ = LAYERS.ndvi;
  let fill = "#ffffff", fillOpacity = 0.05;
  if (sel && L_.visible) {
    const v = ndviValue(id, L_.month);
    if (v != null) { fill = ramp(L_.meta.legend, v); fillOpacity = L_.opacity; }
  }
  return { color: sel ? (id === SELECTION.active ? "#ffd84d" : "#ffffff") : "#ffffffaa",
    weight: sel ? 3 : 1.5, dashArray: sel ? null : "4 4", fillColor: fill, fillOpacity };
}

function select(id) {
  // One parcel at a time: the results always describe the parcel shown on the side.
  const changed = SELECTION.active !== id;
  SELECTION.ids = [id]; SELECTION.active = id;
  if (DATA.ctrl) DATA.ctrl.abort();          // changing parcels cancels the pending scenario
  if (changed && !SCENARIO.cropTouched) SCENARIO.crop = null;
  onSelectionChanged();
  if (VIEW === "pick") fitSelection();
  setView(VIEW);                             // refresh the step buttons (steps 2-3 become available)
}

function onSelectionChanged() {
  Object.keys(MAP.parcelLayers).forEach((id) => MAP.parcelLayers[id].setStyle(parcelStyle(id)));
  updateMarkers();
  renderParcelList();
  renderChosen();
  renderLayerPanel();
  renderAnalysis();
  SELECTION.ids.forEach(ensureGrid);
  buildOverlays();
  runScenario(true);
 
}

function fitSelection() {
  const ids = SELECTION.ids.length ? SELECTION.ids : Object.keys(MAP.parcelLayers);
  const b = L.latLngBounds([]);
  ids.forEach((id) => b.extend(MAP.parcelLayers[id].getBounds()));
  if (b.isValid()) MAP.map.fitBounds(b, { padding: [50, 50], maxZoom: 16 });
}

function renderParcelList() {
  $("parcel-list").innerHTML = DATA.parcels.map((p) => {
    const a = DATA.analyses[p.id];
    const st = !a ? "loading…" : a.error ? `error: ${a.error}` :
      ({ demo_cache: "demo cache", cache: "cache", live: "live" }[a.served_from] || a.served_from);
    const area = a && a.request ? `${fmt(a.request.area_ha, 1)} ha` : "";
    return `<li class="${p.id === SELECTION.active ? "active" : ""}" data-id="${esc(p.id)}" tabindex="0" role="button"
        aria-pressed="${p.id === SELECTION.active}">
      <span class="pname">${esc(p.name)}</span>
      <span class="pmeta">${p.user ? `<span class="tag user">your field · ${esc(p.source === "usda_csb" ? "USDA boundary" : p.source || "")}</span>`
        : '<span class="tag">approximate example</span>'} ${esc(area)} · data: ${esc(st)}
        ${p.user ? `<button type="button" class="linkbtn" data-remove="${esc(p.id)}" aria-label="Remove ${esc(p.name)}">remove</button>` : ""}</span>
    </li>`;
  }).join("");
  $("parcel-list").querySelectorAll("[data-remove]").forEach((b) => b.onclick = (e) => { e.stopPropagation(); removeUserParcel(b.dataset.remove); });
  $("parcel-list").querySelectorAll("li").forEach((li) => {
    li.onclick = () => select(li.dataset.id);
    li.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(li.dataset.id); } };
  });
}

// ---------------------------------------------------------------------------------------------
// Layers
function monthsFor(layerId, id) {
  // List every month of the period with a flag `ok` telling if that layer has data for it.
  // Months without data are shown disabled in the date selector, with the reason.
  const a = DATA.analyses[id];
  if (!a || !a.indicators) return [];
  const ind = a.indicators;
  if (layerId === "ndvi" && ind.ndvi) return ind.ndvi.monthly.map((m) => ({ m: m.month, ok: m.valid_observations > 0 && m.median != null, why: "no valid cloud-free Landsat scene" }));
  if (layerId === "smap" && ind.soil_moisture_smap) return ind.soil_moisture_smap.monthly.map((m) => ({ m: m.month, ok: m.value != null, why: "no SMAP value" }));
  if (layerId === "precip" && ind.agroclimate_power) return ind.agroclimate_power.monthly_series.map((m) => ({ m: m.month, ok: m.precip_mm != null, why: "incomplete month" }));
  return [];
}

function ndviValue(id, month) {
  const n = DATA.analyses[id]?.indicators?.ndvi;
  return n?.monthly.find((m) => m.month === month)?.median ?? null;
}

function legendHtml(meta) {
  const lg = meta.legend;
  if (lg.classes) {
    return `<div class="legend"><div class="cls">${lg.classes.map(([, n, c]) => `<span><i class="sw" style="background:${c}"></i>${esc(n)}</span>`).join("")}
      <span><i class="sw" style="background:${lg.cold}"></i>Possible cold-air pooling</span></div></div>`;
  }
  return `<div class="legend"><div class="bar" style="background:linear-gradient(90deg,${lg.palette.join(",")})"></div>
    <div class="ends"><span>${lg.min}</span><span>${esc(meta.unit)}</span><span>${lg.max}</span></div></div>`;
}

function renderLayerPanel() {
  const id = SELECTION.active;
  $("layer-list").innerHTML = Object.values(LAYERS).map((L_) => {
    const m = L_.meta;
    const months = m.temporal ? monthsFor(m.id, id) : [];
    if (m.temporal && months.length && (!L_.month || !months.some((x) => x.m === L_.month && x.ok))) {
      // default: the latest July/August with data (peak season reads best), else the latest month
      const okm = months.filter((x) => x.ok), summer = okm.filter((x) => /-0[78]$/.test(x.m));
      L_.month = summer.length ? summer[summer.length - 1].m : okm.length ? okm[okm.length - 1].m : null;
    }
    const sel = !m.temporal ? '<div class="status">Static layer (no date)</div>'
      : months.length ? `<label class="row">Observation date <select data-layer="${m.id}" aria-label="${esc(m.name)} month">
          ${months.map((x) => `<option value="${x.m}" ${x.ok ? "" : "disabled"} ${x.m === L_.month ? "selected" : ""}>${x.m}${x.ok ? "" : " — " + esc(x.why)}</option>`).join("")}
        </select></label>` : '<div class="status err">No data for this parcel</div>';
    const riskCtl = m.id === "risk" ? `<div class="row">
        <select data-risk="kind" aria-label="Risk type"><option value="erosion" ${SCENARIO.riskKind === "erosion" ? "selected" : ""}>Erosion screening</option>
          <option value="cold_air" ${SCENARIO.riskKind === "cold_air" ? "selected" : ""}>Possible cold-air pooling</option></select>
        <select data-risk="view" aria-label="Base or scenario"><option value="scenario" ${SCENARIO.riskView === "scenario" ? "selected" : ""}>Scenario</option>
          <option value="base" ${SCENARIO.riskView === "base" ? "selected" : ""}>Base</option></select></div>` : "";
    return `<div class="layer">
      <div class="layer-head"><label><input type="checkbox" data-toggle="${m.id}" ${L_.visible ? "checked" : ""}> ${esc(m.name)}</label>
        <span class="typelabel ${TYPE_CLASS[m.type_label] || ""}">${esc(m.type_label)}</span></div>
      <div class="row">Opacity <input type="range" min="0" max="100" step="5" value="${Math.round(L_.opacity * 100)}" data-opacity="${m.id}" aria-label="${esc(m.name)} opacity" aria-valuetext="${Math.round(L_.opacity * 100)} percent"></div>
      ${sel}${riskCtl}
      <div class="status ${L_.status.startsWith("!") ? "err" : ""}">${esc(L_.status.replace(/^!/, ""))}</div>
      <details><summary class="small">Legend & source</summary>${legendHtml(m)}
        <p class="small">${esc(m.description)}</p>
        <p class="small"><strong>${esc(m.source.name)}</strong> ${m.source.nasa ? "· NASA" : "· non-NASA"}<br><code>${m.source.ids.map(esc).join(", ")}</code></p>
        <p class="small">Type: ${esc(m.data_type)} · Resolution: ${esc(m.resolution)} · Scale: ${esc(m.scale_note)}</p>
        <p class="small muted">${esc(m.honesty)}</p>
        ${m.warnings.length ? `<p class="small">Warnings: ${m.warnings.map((w) => `<code>${esc(w)}</code>`).join(" ")}</p>` : ""}
      </details>
    </div>`;
  }).join("");
  const box = $("layer-list");
  box.querySelectorAll("[data-toggle]").forEach((el) => el.onchange = () => { LAYERS[el.dataset.toggle].visible = el.checked; buildOverlays(); });
  box.querySelectorAll("[data-opacity]").forEach((el) => el.oninput = () => {
    LAYERS[el.dataset.opacity].opacity = el.value / 100; el.setAttribute("aria-valuetext", `${el.value} percent`); applyOpacity(); });
  box.querySelectorAll("select[data-layer]").forEach((el) => el.onchange = () => { LAYERS[el.dataset.layer].month = el.value; buildOverlays(); });
  box.querySelectorAll("select[data-risk]").forEach((el) => el.onchange = () => {
    SCENARIO[el.dataset.risk === "kind" ? "riskKind" : "riskView"] = el.value; buildRiskOverlay(); });
}

function setStatus(id, text) {
  LAYERS[id].status = text;
  const el = [...document.querySelectorAll("#layer-list .layer")].find((d) => d.querySelector(`[data-toggle="${id}"]`));
  if (el) { const s = el.querySelectorAll(".status"); const st = s[s.length - 1]; st.textContent = text.replace(/^!/, ""); st.classList.toggle("err", text.startsWith("!")); }
}

function ramp(lg, v) {
  // Colour scale: t is the value scaled to 0..1 inside the legend range, then we find the two
  // palette colours around t and blend them linearly (f = how far we are between them).
  const p = lg.palette, t = Math.max(0, Math.min(1, (v - lg.min) / (lg.max - lg.min)));
  const x = t * (p.length - 1), i = Math.min(p.length - 2, Math.floor(x)), f = x - i;
  const a = hex(p[i]), b = hex(p[i + 1]);
  return `rgb(${a.map((c, k) => Math.round(c + (b[k] - c) * f)).join(",")})`;
}
function hex(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }

function clearOverlay(id) { (MAP.overlays[id] || []).forEach((l) => MAP.map.removeLayer(l)); MAP.overlays[id] = []; }

function buildOverlays() {
  Object.keys(MAP.parcelLayers).forEach((id) => MAP.parcelLayers[id].setStyle(parcelStyle(id)));
  setStatus("ndvi", LAYERS.ndvi.visible ? (LAYERS.ndvi.month ? `Showing ${LAYERS.ndvi.month} (parcel mean)` : "!No valid month") : "");
  ["smap", "precip"].forEach(buildZoneOverlay);
  buildSlopeOverlay();
  buildRiskOverlay();
}

function buildZoneOverlay(lid) {
  clearOverlay(lid);
  const L_ = LAYERS[lid];
  if (!L_.visible) { setStatus(lid, ""); return; }
  let n = 0;
  SELECTION.ids.forEach((id) => {
    const ind = DATA.analyses[id]?.indicators;
    if (!ind) return;
    let geom = null, value = null;
    if (lid === "smap" && ind.soil_moisture_smap) {
      geom = ind.soil_moisture_smap.pixel_footprint;
      value = ind.soil_moisture_smap.monthly.find((m) => m.month === L_.month)?.value ?? null;
    }
    if (lid === "precip" && ind.agroclimate_power) {
      const [w, s, e, nn] = ind.agroclimate_power.merra2_cell_bounds || [];
      if (w != null) geom = { type: "Polygon", coordinates: [[[w, s], [e, s], [e, nn], [w, nn], [w, s]]] };
      value = ind.agroclimate_power.monthly_series.find((m) => m.month === L_.month)?.precip_mm ?? null;
    }
    if (!geom || value == null) return;
    const lyr = L.geoJSON(geom, { pane: "zones", interactive: false,
      style: { color: css("--ink"), weight: 1.5, dashArray: "6 4", fillColor: ramp(L_.meta.legend, value), fillOpacity: L_.opacity } });
    lyr.addTo(MAP.map); MAP.overlays[lid].push(lyr); n++;
  });
  setStatus(lid, n ? `Showing ${L_.month} · whole ${lid === "smap" ? "SMAP cell" : "MERRA-2 cell"} (zoom out to see it)` : (lid === "smap" ? "!No SMAP cell footprint or value for this date" : "!No value for this date"));
}

function gridImage(grid, colorOf) {
  // Paint the 30 m grid into an off-screen canvas with ONE canvas pixel per data pixel, then turn
  // it into an image (data URL). Leaflet stretches that image over the grid's bounding box and the
  // CSS class "pixelated" keeps the pixels sharp (no smoothing between values).
  // ImageData stores 4 bytes per pixel (R, G, B, alpha); untouched pixels stay transparent.
  const c = document.createElement("canvas");
  c.width = grid.cols; c.height = grid.rows;
  const ctx = c.getContext("2d"), img = ctx.createImageData(grid.cols, grid.rows);
  for (let i = 0; i < grid.rows * grid.cols; i++) {
    const rgb = colorOf(i);
    if (!rgb) continue;
    img.data.set([rgb[0], rgb[1], rgb[2], 255], i * 4);
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}
function bboxBounds(b) { return [[b[1], b[0]], [b[3], b[2]]]; }

function buildSlopeOverlay() {
  clearOverlay("slope");
  const L_ = LAYERS.slope;
  if (!L_.visible) { setStatus("slope", ""); return; }
  let n = 0, missing = "";
  SELECTION.ids.forEach((id) => {
    const g = DATA.grids[id];
    if (!g || g.error) { missing = g?.error || "loading terrain grid…"; return; }
    const url = gridImage(g, (i) => (g.in_parcel[i] && g.slope_deg[i] != null ? hex(rgbToHex(ramp(L_.meta.legend, g.slope_deg[i]))) : null));
    const ov = L.imageOverlay(url, bboxBounds(g.bbox), { pane: "grids", opacity: L_.opacity, className: "pixelated", interactive: false });
    ov.addTo(MAP.map); MAP.overlays.slope.push(ov); n++;
  });
  setStatus("slope", n ? "Native NASADEM pixels inside the parcel" : `!${missing || "No terrain grid"}`);
}
function rgbToHex(rgb) { const [r, g, b] = rgb.match(/\d+/g).map(Number); return "#" + [r, g, b].map((x) => x.toString(16).padStart(2, "0")).join(""); }

function buildRiskOverlay() {
  clearOverlay("risk");
  const L_ = LAYERS.risk;
  if (!L_.visible) { setStatus("risk", ""); return; }
  const colors = Object.fromEntries(L_.meta.legend.classes.map(([k, , c]) => [k, hex(c)]));
  const cold = hex(L_.meta.legend.cold);
  let n = 0, why = "";
  SELECTION.ids.forEach((id) => {
    const z = DATA.sims[id]?.risk_zones;
    if (!z) { why = DATA.sims[id]?.data_gaps?.find((g) => g.indicator === "risk_zones")?.reason || "Waiting for the scenario…"; return; }
    const block = z[SCENARIO.riskKind];
    const codes = block[SCENARIO.riskView];
    if (!codes) { why = "Not enough erosion factors"; return; }
    const url = gridImage(z, (i) => {
      const ch = codes[i];
      if (SCENARIO.riskKind === "erosion") return colors[ch] || null;
      return ch === "1" ? cold : null;
    });
    const ov = L.imageOverlay(url, bboxBounds(z.bbox), { pane: "grids", opacity: L_.opacity, className: "pixelated", interactive: false });
    ov.addTo(MAP.map); MAP.overlays.risk.push(ov); n++;
  });
  const lbl = SCENARIO.riskKind === "erosion" ? "Erosion screening" : "Possible cold-air pooling";
  setStatus("risk", n ? `${lbl} · ${SCENARIO.riskView === "base" ? "Base" : "Scenario"} · derived + hypothetical` : `!${why}`);
}

function applyOpacity() {
  // Only change the opacity of what is already drawn: no new requests, so the slider feels instant.
  Object.keys(MAP.parcelLayers).forEach((id) => MAP.parcelLayers[id].setStyle(parcelStyle(id)));
  ["smap", "precip"].forEach((lid) => (MAP.overlays[lid] || []).forEach((l) => l.setStyle({ fillOpacity: LAYERS[lid].opacity })));
  ["slope", "risk"].forEach((lid) => (MAP.overlays[lid] || []).forEach((l) => l.setOpacity(LAYERS[lid].opacity)));
}

async function ensureGrid(id) {
  if (DATA.grids[id] && !DATA.grids[id].error) return;
  const hash = DATA.analyses[id]?.request?.cache_key;
  if (!hash) return;
  try {
    DATA.grids[id] = await dataSource.terrainGrid(hash);
  } catch (e) {
    DATA.grids[id] = { error: e.code === "GEE_UNAVAILABLE" ? "Terrain grid needs Earth Engine (not configured)" : `Terrain grid: ${e.message}` };
  }
  buildSlopeOverlay();
  if (SELECTION.ids.includes(id)) runScenario(true);
}

// ---------------------------------------------------------------------------------------------
// Cursor inspector: values of the visible layers at the cursor, with unit, date, source, type, scale.
function pointInRing(pt, ring) {
  // Ray casting: draw an imaginary line from the point to the right and count how many polygon
  // edges it crosses. An odd number of crossings means the point is inside.
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function pointInGeom(pt, g) {
  if (!g) return false;
  const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
  return polys.some((rings) => pointInRing(pt, rings[0]) && !rings.slice(1).some((h) => pointInRing(pt, h)));
}
function gridIndex(g, ll) {
  // Which grid pixel is under the cursor? Column from the west edge, row from the north edge;
  // the flat list index is row * number_of_columns + column. -1 = outside the grid.
  const [w, s, e, n] = g.bbox;
  if (ll.lng < w || ll.lng >= e || ll.lat <= s || ll.lat > n) return -1;
  const c = Math.floor(((ll.lng - w) / (e - w)) * g.cols), r = Math.floor(((n - ll.lat) / (n - s)) * g.rows);
  return r * g.cols + c;
}

function inspect(ll) {
  const pt = [ll.lng, ll.lat], items = [];
  const anyVisible = Object.values(LAYERS).some((l) => l.visible);
  $("map").classList.toggle("inspect", anyVisible);
  SELECTION.ids.forEach((id) => {
    const p = DATA.parcels.find((x) => x.id === id), a = DATA.analyses[id], ind = a?.indicators;
    if (!ind) return;
    const inParcel = pointInGeom(pt, p.geometry.type === "Point" ? null : p.geometry);
    if (LAYERS.ndvi.visible && inParcel && ind.ndvi) {
      const v = ndviValue(id, LAYERS.ndvi.month);
      items.push(`<div class="it"><b>NDVI ${fmt(v, 2)}</b> · parcel mean, ${esc(LAYERS.ndvi.month)}<br><span class="muted">Landsat 8/9 · satellite · 30 m data averaged over the parcel</span></div>`);
    }
    if (LAYERS.smap.visible && ind.soil_moisture_smap && pointInGeom(pt, ind.soil_moisture_smap.pixel_footprint)) {
      const v = ind.soil_moisture_smap.monthly.find((m) => m.month === LAYERS.smap.month)?.value;
      items.push(`<div class="it"><b>${fmt(v, 3)} m³/m³</b> · root-zone moisture, ${esc(LAYERS.smap.month)}<br><span class="muted">Value of the ~9–11 km SMAP zone, not this point · SMAP L4 · model</span></div>`);
    }
    if (LAYERS.precip.visible && ind.agroclimate_power) {
      const [w, s, e, n] = ind.agroclimate_power.merra2_cell_bounds || [];
      if (w != null && ll.lng >= w && ll.lng <= e && ll.lat >= s && ll.lat <= n) {
        const v = ind.agroclimate_power.monthly_series.find((m) => m.month === LAYERS.precip.month)?.precip_mm;
        items.push(`<div class="it"><b>${fmt(v, 0)} mm</b> · rainfall, ${esc(LAYERS.precip.month)}<br><span class="muted">Value of the ~50 × 60 km MERRA-2 zone, not this point · NASA POWER · reanalysis</span></div>`);
      }
    }
    const g = DATA.grids[id];
    if (g && !g.error) {
      const i = gridIndex(g, ll);
      if (i >= 0 && g.in_parcel[i]) {
        if (LAYERS.slope.visible) items.push(`<div class="it"><b>${fmt(g.slope_deg[i], 1)}°</b> slope · TPI ${fmt(g.tpi_m[i], 1)} m<br><span class="muted">NASADEM pixel (~30 m) · satellite radar · static (2000)</span></div>`);
        const z = DATA.sims[id]?.risk_zones;
        if (LAYERS.risk.visible && z) {
          const codes = z[SCENARIO.riskKind][SCENARIO.riskView];
          const ch = codes ? codes[i] : null;
          const txt = SCENARIO.riskKind === "erosion" ? ({ 1: "Low", 2: "Medium", 3: "High" }[ch] || "—") + " erosion screening"
            : (ch === "1" ? "Possible cold-air pooling" : "No cold-air hollow");
          items.push(`<div class="it"><b>${esc(txt)}</b> · ${SCENARIO.riskView}<br><span class="muted">Derived + hypothetical · slope per pixel, other factors parcel/zone</span></div>`);
        }
      }
    }
  });
  const box = MAP.inspector.getContainer();
  box.innerHTML = `<h4>Under the cursor</h4>${items.join("") || '<div class="muted">No visible layer value here</div>'}`;
}

// ---------------------------------------------------------------------------------------------
// Simulator
function defaultCropFor(id) {
  const years = DATA.analyses[id]?.indicators?.crop_type?.years || [];
  const last = years[years.length - 1]?.dominant?.[0]?.name;
  return CDL_TO_CROP[last] || "corn_maize";
}

function bindSimulator() {
  const dp = $("dp"), dt = $("dt"), on = $("irr-on"), irr = $("irr"), cropSel = $("crop");
  cropSel.innerHTML = DATA.crops.crops.map((c) => `<option value="${esc(c.id)}">${esc(c.name_en)}</option>`).join("");
  if (SCENARIO.crop) cropSel.value = SCENARIO.crop;
  cropSel.addEventListener("change", () => { SCENARIO.crop = cropSel.value; SCENARIO.cropTouched = true; DATA.t0 = performance.now(); runScenario(true); });
  dp.value = SCENARIO.dp; dt.value = SCENARIO.dt; on.checked = SCENARIO.irrOn; irr.value = SCENARIO.irr; irr.disabled = !SCENARIO.irrOn;
  const sync = () => {
    $("dp-out").textContent = `${SCENARIO.dp} %`;
    dp.setAttribute("aria-valuetext", `${SCENARIO.dp} % rainfall`);
    $("dt-out").textContent = `+${SCENARIO.dt.toFixed(1)} °C`;
    dt.setAttribute("aria-valuetext", `plus ${SCENARIO.dt.toFixed(1)} degrees Celsius`);
    $("irr-out").textContent = SCENARIO.irrOn ? `${SCENARIO.irr} %` : "off";
    irr.setAttribute("aria-valuetext", SCENARIO.irrOn ? `${SCENARIO.irr} % of deficit covered` : "irrigation off");
    irr.disabled = !SCENARIO.irrOn;
  };
  // On every slider movement: remember the time (to measure speed), update the visible numbers
  // immediately, then ask the server (with a short debounce) and save the state in the URL.
  const changed = () => { DATA.t0 = performance.now(); sync(); runScenario(false); };
  dp.addEventListener("input", () => { SCENARIO.dp = Number(dp.value); changed(); });
  dt.addEventListener("input", () => { SCENARIO.dt = Number(dt.value); changed(); });
  on.addEventListener("change", () => { SCENARIO.irrOn = on.checked; changed(); });
  irr.addEventListener("input", () => { SCENARIO.irr = Number(irr.value); changed(); });
  const setAll = (p, t) => { SCENARIO.dp = p; SCENARIO.dt = t; dp.value = p; dt.value = t; changed(); };
  $("preset-dry").onclick = () => setAll(-15, 1.0);
  $("preset-hot").onclick = () => setAll(-25, 2.5);
  $("reset").onclick = () => { SCENARIO.irrOn = false; SCENARIO.irr = 0; on.checked = false; irr.value = 0; setAll(0, 0); };
  sync();
}

// Debounce: while the user drags a slider, input events fire many times per second. We restart an
// 80 ms timer on every event and only call the server when the slider pauses.
let debounceTimer = null;
function runScenario(immediate) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(doRun, immediate ? 0 : 80);
}

async function doRun() {
  const ids = SELECTION.ids.filter((id) => DATA.analyses[id]?.request?.cache_key);
  if (!SELECTION.active) return;
  if (!ids.length) {
    // Never fail silently: say why the sliders cannot answer yet.
    const a = DATA.analyses[SELECTION.active];
    $("sim-status").textContent = !a ? "Waiting for this parcel's data (a new field takes 30-60 s the first time)… the scenario runs as soon as it arrives."
      : a.error ? `This parcel could not be analyzed: ${a.error}` : "";
    return;
  }
  if (!SCENARIO.cropTouched && SELECTION.active && DATA.analyses[SELECTION.active]?.indicators) {
    SCENARIO.crop = defaultCropFor(SELECTION.active);       // follow the parcel until the user picks a crop
    $("crop").value = SCENARIO.crop;
  }
  // Race condition protection: answers can arrive in a different order than the requests.
  // Every request gets a sequence number; we cancel the previous request (AbortController) and,
  // when an answer arrives, we only use it if its number is still the latest one.
  const seq = ++DATA.seq;
  if (DATA.ctrl) DATA.ctrl.abort();
  const ctrl = new AbortController(); DATA.ctrl = ctrl;
  const sc = { ...SCENARIO };
  $("sim-status").textContent = "Recalculating…";
  try {
    const res = await Promise.all(ids.map(async (id) => {
      const hash = DATA.analyses[id].request.cache_key;
      try { return [id, await dataSource.simulate(hash, sc, ctrl.signal)]; } catch (e) {
        if (e.code === "BASELINE_NOT_CACHED") {           // baseline missing: analyze first, then retry once
          const p = DATA.parcels.find((x) => x.id === id);
          DATA.analyses[id] = await dataSource.analyze(p.geometry);
          return [id, await dataSource.simulate(DATA.analyses[id].request.cache_key, sc, ctrl.signal)];
        }
        throw e;
      }
    }));
    if (seq !== DATA.seq) return;                          // a newer request superseded this one
    DATA.sims = Object.fromEntries(res);
    renderSim();
    renderEcon();
    loadReco(seq, sc, ctrl);
    buildRiskOverlay();
    updateMode();
    // requestAnimationFrame runs after the browser has painted the new numbers, so the measured
    // time is "slider moved -> user sees the result". We keep the last 20 timings for p50/p95.
    requestAnimationFrame(() => {
      if (!DATA.t0) { $("sim-status").textContent = ""; return; }
      const ms = performance.now() - DATA.t0; DATA.t0 = 0;
      DATA.timings.push(ms); if (DATA.timings.length > 20) DATA.timings.shift();
      const s = [...DATA.timings].sort((a, b) => a - b), q = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
      const server = Object.values(DATA.sims).map((x) => x.timing_ms.server).join(" / ");
      $("sim-status").textContent = `Updated in ${ms.toFixed(0)} ms (server ${server} ms) · last ${s.length}: p50 ${q(0.5).toFixed(0)} ms, p95 ${q(0.95).toFixed(0)} ms`;
      console.info("[sim timing]", { ms, p50: q(0.5), p95: q(0.95), n: s.length });
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    if (seq === DATA.seq) $("sim-status").textContent = `Scenario failed: ${e.message}`;
  }
}

function deltaValue(x, v) {
  if (x.indicator === "last_spring_frost_p50_doy") {
    const d = new Date(Date.UTC(2001, 0, 1) + (v - 1) * 86400000);
    return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
  }
  if (x.indicator === "erosion_index") return fmt(v, 2);
  return fmt(v, Math.abs(v) < 20 && v % 1 ? 1 : 0);
}

// Short Base → Scenario summary right under the sliders, so every move shows a visible change.
function renderSummary(s) {
  const box = $("sim-summary");
  if (!box) return;
  if (!s) { box.innerHTML = ""; return; }
  const d = Object.fromEntries(s.deltas.map((x) => [x.indicator, x]));
  const item = (k, label, unit, dec = 0) => {
    const x = d[k];
    if (!x) return "";
    const cls = x.direction === "worse" ? "neg" : x.direction === "better" ? "pos" : "";
    return `<li><span>${label}</span><b>${fmt(x.baseline, dec)} → <span class="${cls}">${fmt(x.scenario, dec)}</span> ${unit}</b></li>`;
  };
  const ce = s.crop_effect, w = ce?.scenario?.water;
  box.innerHTML = `<p class="plain-summary">${esc(scenarioSentence(s, d))}</p>
    <ul class="sumlist">
    ${item("mean_annual_deficit_mm", "Water missing in dry months", "mm/yr")}
    ${item("et0_annual_mm", "Water the air pulls from plants (ET0)", "mm/yr")}
    ${item("heat_days_per_year", "Very hot days (≥ 35 °C)", "/yr", 1)}
    ${item("frost_free_days_median", "Days without frost", "days")}
    ${w && w.expected_loss_pct != null ? `<li><span>${esc(ce.crop)}: harvest lost for lack of water</span><b>${fmt(ce.baseline.water.expected_loss_pct)} → <span class="${w.expected_loss_pct > ce.baseline.water.expected_loss_pct ? "neg" : ""}">${fmt(w.expected_loss_pct)}</span> %</b></li>` : ""}
  </ul>
  <p class="small muted">Today → scenario. 1 mm of water = 1 litre per square metre. Red = worse for crops, green = better.</p>`;
}

// One sentence in everyday words: what the slider settings would mean for this field.
function scenarioSentence(s, d) {
  const sc = s.scenario, ce = s.crop_effect;
  if (!sc.delta_precip_pct && !sc.delta_temp_c && !sc.irrigation_enabled)
    return "This is today's climate on this field (average of the last 10 years). Move the sliders to imagine a drier or warmer future.";
  const what = [];
  if (sc.delta_precip_pct) what.push(`${Math.abs(sc.delta_precip_pct)} % less rain`);
  if (sc.delta_temp_c) what.push(`${sc.delta_temp_c.toFixed(1)} °C warmer`);
  const parts = [];
  const def = d.mean_annual_deficit_mm;
  if (def && def.change > 0) parts.push(`the soil would run short of about ${fmt(def.change)} more litres of water per square metre each year`);
  const hot = d.heat_days_per_year;
  if (hot && hot.change >= 1) parts.push(`there would be about ${fmt(hot.change)} more very hot days a year`);
  const ff = d.frost_free_days_median;
  if (ff && ff.change >= 3) parts.push(`frosts would end earlier, giving about ${fmt(ff.change)} more frost-free days`);
  let txt = (what.length ? `With ${what.join(" and ")}, ` : "In this scenario, ") + (parts.length ? parts.join(", ") : "little would change") + ".";
  const w0 = ce?.baseline?.water?.expected_loss_pct, w1 = ce?.scenario?.water?.expected_loss_pct;
  if (w1 != null && w0 != null && Math.round(w1) !== Math.round(w0))
    txt += ` For ${ce.crop.toLowerCase()}, lack of water could cost about ${fmt(w1)} % of the harvest (today ${fmt(w0)} %)${sc.irrigation_enabled ? ", counting the irrigation" : ""}.`;
  return txt;
}

function renderSim() {
  const blocks = SELECTION.ids.map((id) => {
    const s = DATA.sims[id], p = DATA.parcels.find((x) => x.id === id);
    if (!s) return "";
    const changeable = s.deltas.filter((x) => !(x.indicator === "remaining_deficit_mm" && !s.scenario.irrigation_enabled));
    const rows = changeable.map((x) => {
      const max = Math.max(Math.abs(x.baseline), Math.abs(x.scenario)) || 1;
      const arrow = x.direction === "worse" ? "▲ worse" : x.direction === "better" ? "▼ better" : "= same";
      const ch = x.indicator === "last_spring_frost_p50_doy" ? `${x.change > 0 ? "+" : ""}${fmt(x.change, 0)} d` : `${x.change > 0 ? "+" : ""}${deltaValue(x, x.change)}`;
      return `<tr><td>${esc(DELTA_LABELS[x.indicator] || x.indicator)}<div class="bars" aria-hidden="true">
          <span class="b" style="width:${(Math.abs(x.baseline) / max) * 100}%"></span><span class="s" style="width:${(Math.abs(x.scenario) / max) * 100}%"></span></div>
          <div class="scale">scale 0–${deltaValue(x, max)} ${esc(x.unit)}</div></td>
        <td>${deltaValue(x, x.baseline)}</td><td>${deltaValue(x, x.scenario)}</td>
        <td>${ch}<br><span class="dir ${x.direction}">${arrow}</span></td></tr>`;
    }).join("");
    const eb = s.baseline.erosion_index, es = s.scenario_result.erosion_index;
    const ero = eb && es ? `<p class="small">Erosion screening class: <strong>${esc(eb.value)}</strong> → <strong>${esc(es.value)}</strong>. ${esc(es.note)}</p>` : "";
    const gaps = s.data_gaps.map((g) => `<li>${esc(g.reason)} <code>${esc(g.code)}</code></li>`).join("");
    return `<div class="simblock">
      <h3>${esc(p.name)}</h3>
      ${id === SELECTION.active ? "" : cropCard(s.crop_effect)}
      <details><summary>Climate details of the parcel (all crops)</summary>
      <table class="cmp"><thead><tr><th>Indicator</th><th>Base<br><span class="typelabel t-reanalysis">Reanalysis · derived</span></th>
        <th>Scenario<br><span class="typelabel t-hypothetical">Hypothetical</span></th><th>Change</th></tr></thead><tbody>${rows}</tbody></table>
      ${ero}
      </details>
      <div><strong class="small">What changed</strong><ul>${(s.scenario.delta_precip_pct || s.scenario.delta_temp_c || s.scenario.irrigation_enabled)
        ? [...(s.crop_effect?.explanation || []), ...s.explanation.filter((t) => !t.startsWith("Unchanged"))].map((t) => `<li>${esc(t)}</li>`).join("")
        : "<li>No change: all controls at zero (base climate).</li>"}</ul></div>
      <div><strong class="small">What does not change</strong><ul>${s.unchanged.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
      <details><summary>Method and assumptions (${esc(s.version)}, mode ${esc(s.mode)})</summary><ul>${s.assumptions.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>
      ${gaps ? `<details><summary>Information gaps</summary><ul>${gaps}</ul></details>` : ""}
    </div>`;
  });
  const act = DATA.sims[SELECTION.active];
  renderSummary(act);
  $("sim-crop").innerHTML = act ? `${SELECTION.ids.length > 1 ? `<h3 class="small">${esc(DATA.parcels.find((x) => x.id === SELECTION.active)?.name || "")}</h3>` : ""}${cropCard(act.crop_effect)}` : "";
  $("sim-results").innerHTML = blocks.join("") || '<p class="muted small">Select a parcel to run the scenario.</p>';
  // One-line headlines on the closed sections, so the user knows what is inside before opening them.
  const ce = act?.crop_effect;
  if (ce) {
    const bad = (ce.rows || []).filter((x) => x.scenario === "limit").length, warn = (ce.rows || []).filter((x) => x.scenario === "marginal").length;
    $("hl-crop").textContent = `${ce.crop}: ${bad ? `${bad} problem${bad > 1 ? "s" : ""}` : warn ? `${warn} point${warn > 1 ? "s" : ""} to watch` : "everything fits"}`;
  }
  if (act) {
    const sc = act.scenario;
    $("hl-scenario").textContent = sc.delta_precip_pct || sc.delta_temp_c || sc.irrigation_enabled
      ? `${sc.delta_precip_pct ? `${sc.delta_precip_pct} % rain` : ""}${sc.delta_precip_pct && sc.delta_temp_c ? ", " : ""}${sc.delta_temp_c ? `+${sc.delta_temp_c} °C` : ""}${sc.irrigation_enabled ? " · irrigation" : ""}`
      : "today's climate (move the sliders on the left)";
  }
}

// ---------------------------------------------------------------------------------------------
// What to sow here: rule-based ranking of the 15 catalogue crops for the active parcel + sowing dates
const GROUP_TXT = { recommended: "Recommended", possible: "Possible with care", not_recommended: "Not recommended" };
const mmddTxt = (s) => (s ? `${MONTHS[Number(s.slice(0, 2)) - 1]} ${Number(s.slice(3))}` : "—");

async function loadReco(seq, sc, ctrl) {
  const a = DATA.analyses[SELECTION.active];
  if (!a?.request) { $("reco").innerHTML = ""; return; }
  try {
    const r = await dataSource.recommend(a.request.cache_key, sc, ctrl.signal);
    if (seq !== DATA.seq) return;
    DATA.reco = r;
    renderReco();
  } catch (e) {
    if (e.name !== "AbortError" && seq === DATA.seq) $("reco").innerHTML = `<p class="small muted">Recommendation unavailable: ${esc(e.message)}</p>`;
  }
}

function sowText(x) {
  if (!x.sowing || !x.sowing.from) return "No frost-safe sowing date inside its window";
  return `Sow ${mmddTxt(x.sowing.from)} – ${mmddTxt(x.sowing.to)} · harvest ${MONTHS[x.harvest_months[0] - 1]}–${MONTHS[x.harvest_months[1] - 1]}`;
}

const nRole = (role) => role === "adds" ? '<span class="nrole adds" title="Legume: makes its own nitrogen and leaves some in the soil">🌱 adds nitrogen</span>'
  : role === "uses" ? '<span class="nrole uses" title="Takes nitrogen from the soil: needs fertiliser">🌾 uses nitrogen</span>' : "";

// Suggested rotation: alternate crops that add nitrogen (legumes) with crops that use it.
function rotationHtml(p) {
  if (!p) return "";
  if (!p.years.length) return `<div class="rotation-plan"><p class="small">${esc(p.summary)}</p></div>`;
  return `<div class="rotation-plan">
    <h4>The next ${p.years.length} years</h4>
    <p class="small">${esc(p.summary)}</p>
    <ol class="rot-steps">${p.years.map((y) => `<li class="rot ${y.role}">
        <div class="rot-head"><b>${y.year ?? "Year " + y.step}</b> ${esc(y.crop)} ${nRole(y.role)}
          ${y.group !== "recommended" ? `<span class="grp ${y.group}">${GROUP_TXT[y.group]}</span>` : ""}</div>
        <div class="small">${esc(y.why)}</div></li>`).join("")}</ol>
    ${p.alfalfa_option ? `<p class="small">💡 ${esc(p.alfalfa_option)}</p>` : ""}
    <p class="small muted">${esc(p.start_note)}</p>
  </div>`;
}

function renderReco() {
  const r = DATA.reco;
  if (!r) return;
  const good = r.crops.filter((x) => x.group !== "not_recommended");
  const top = (good.length ? good : r.crops).slice(0, 3);
  const prev = r.previous_crop?.cdl_name ? `Last year (${r.previous_crop.year}): <strong>${esc(r.previous_crop.cdl_name)}</strong> (USDA CDL).` : "Last year's crop unknown.";
  const intro = r.summary.recommended.length ? "Best options for this field in this scenario:"
    : good.length ? "No crop passes every check in this scenario. Options that need care:"
    : "<strong>No crop passes the checks in this scenario.</strong> The least risky ones are:";
  $("hl-reco").textContent = top.length ? `${top[0].group === "recommended" ? "Best options" : good.length ? "Best options, with care" : "Least risky"}: ${top.map((x) => x.crop).join(", ")}` : "";
  const rp = r.rotation_plan;
  $("rotation-plan").innerHTML = rotationHtml(rp);
  $("hl-rotation").textContent = rp?.years?.length ? rp.years.map((y) => `${y.role === "adds" ? "🌱" : "🌾"} ${y.crop}`).join(" → ") : "";
  $("reco").innerHTML = `
    <p class="small muted">${prev} ${intro}</p>
    ${top.map((x, i) => `<div class="pick ${i === 0 && x.group === "recommended" ? "top" : ""}">
        <div class="head"><span class="name">${i + 1}. ${esc(x.crop)}</span><span class="grp ${x.group}">${GROUP_TXT[x.group]}</span></div>
        <div class="verdict">${esc(x.verdict || "")} ${nRole(x.n_role)}</div>
        <div class="sow">📅 ${esc(sowText(x))}</div>
        <ul>${x.reasons.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
        ${(x.reasons_numbers || []).length ? `<details class="numbers"><summary>📊 The numbers</summary><ul>${x.reasons_numbers.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
        <button type="button" data-crop="${esc(x.crop_id)}">See this crop in detail →</button>
      </div>`).join("")}
    <details><summary class="small">All ${r.crops.length} crops</summary>
      <table>${r.crops.map((x) => `<tr><td><button type="button" data-crop="${esc(x.crop_id)}">${esc(x.crop)}</button></td>
        <td><span class="grp ${x.group}">${GROUP_TXT[x.group]}</span></td>
        <td>${x.sowing?.from ? `${mmddTxt(x.sowing.from)}–${mmddTxt(x.sowing.to)}` : "—"}</td></tr>`).join("")}</table>
    </details>
    <details><summary class="small">How this is decided</summary><ul class="small">
      ${Object.values(r.rules).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>
    <p class="hint small muted">Rule-based screening with visible reasons, not a prediction. Check market, machinery and local advice before sowing.</p>`;
  $("reco").querySelectorAll("[data-crop]").forEach((b) => b.onclick = () => {
    SCENARIO.crop = b.dataset.crop; SCENARIO.cropTouched = true; $("crop").value = SCENARIO.crop;
    DATA.t0 = performance.now(); runScenario(true);
    const sec = $("sim-crop").closest("details");
    if (sec) { CHOSEN.add("crop"); sec.hidden = false; sec.open = true; }
    sec?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// ---------------------------------------------------------------------------------------------
// Money check: budget for the selected crop on the active parcel. Inputs are the farmer's (prefilled
// with sourced defaults); the backend does the arithmetic (/api/economics/budget). No yield forecast.
const ECON = { key: null, defaults: null, inputs: {}, timer: null, seq: 0 };
const usd = (v) => (v == null ? "—" : `${v < 0 ? "−" : ""}$${Math.abs(Math.round(v)).toLocaleString("en-US")}`);

async function renderEcon() {
  const id = SELECTION.active, a = DATA.analyses[id], crop = SCENARIO.crop;
  if (!a?.request || !crop) { $("econ").innerHTML = ""; return; }
  // The form is rebuilt only when the parcel or crop changes. If we rebuilt it on every slider
  // move, the input boxes would lose what the farmer is typing.
  const key = `${id}|${crop}`;
  if (ECON.key !== key) {                        // new parcel or crop: (re)build the form once
    ECON.key = key;
    try { ECON.defaults = await dataSource.get(`/api/economics/defaults?crop_id=${encodeURIComponent(crop)}`); }
    catch { ECON.defaults = null; }
    if (ECON.key !== key) return;
    const saved = ECON.inputs[crop] || {};
    const d = ECON.defaults || {};
    const v = (k, dk) => saved[k] ?? d[dk] ?? "";
    const bu = d.bushel_kg;
    $("econ").innerHTML = `
      <h3>Money check: can I afford ${esc(d.crop || crop)} here?</h3>
      <p class="hint">Prefilled with public averages (source below). Change any box to your own numbers.</p>
      <div class="inputs">
        <label>Expected yield (t/ha)<input type="number" min="0" step="0.1" data-econ="yield_t_ha" value="${v("yield_t_ha", "yield_t_ha")}">
          <span class="hint" data-hint="yield">${bu ? "" : "&nbsp;"}</span></label>
        <label>Sale price (USD per tonne)<input type="number" min="0" step="1" data-econ="price_usd_t" value="${v("price_usd_t", "price_usd_t")}">
          <span class="hint" data-hint="price"></span></label>
        <label>All costs (USD per ha)<input type="number" min="0" step="10" data-econ="cost_usd_ha" value="${v("cost_usd_ha", "cost_usd_ha")}">
          <span class="hint" data-hint="cost"></span></label>
        <label>Money I can spend (USD)<input type="number" min="0" step="1000" data-econ="available_usd" value="${saved.available_usd ?? ""}" placeholder="optional">
          <span class="hint">for this field</span></label>
        <label>Irrigation cost (USD per mm per ha)<input type="number" min="0" step="0.1" data-econ="irrigation_cost_usd_mm_ha" value="${saved.irrigation_cost_usd_mm_ha ?? ""}" placeholder="only if irrigating">
          <span class="hint">uses the hypothetical irrigation of the scenario</span></label>
      </div>
      <div id="econ-out" aria-live="polite"></div>
      <details><summary class="small">Where the default numbers come from</summary><ul class="small">
        <li>Yield: ${esc(d.yield_source || "—")}</li><li>Price: ${esc(d.price_source || "—")}</li>
        <li>Costs: ${esc(d.cost_source || "—")}</li>${(d.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul></details>`;
    $("econ").querySelectorAll("[data-econ]").forEach((el) => el.addEventListener("input", () => {
      (ECON.inputs[crop] ||= {})[el.dataset.econ] = el.value === "" ? null : Number(el.value);
      clearTimeout(ECON.timer); ECON.timer = setTimeout(updateEcon, 120);
    }));
  }
  updateEcon();
}

function readEcon() {
  const f = {};
  $("econ").querySelectorAll("[data-econ]").forEach((el) => { f[el.dataset.econ] = el.value === "" ? null : Number(el.value); });
  return f;
}

async function updateEcon() {
  const id = SELECTION.active, a = DATA.analyses[id];
  if (!a?.request || !$("econ-out")) return;
  const f = readEcon(), d = ECON.defaults || {}, bu = d.bushel_kg, AC = 0.40468564224;
  const hint = (k, t) => { const el = $("econ").querySelector(`[data-hint="${k}"]`); if (el) el.textContent = t; };
  if (bu) {
    hint("yield", f.yield_t_ha ? `= ${(f.yield_t_ha * AC / (bu / 1000)).toFixed(0)} bu/acre` : "");
    hint("price", f.price_usd_t ? `= $${(f.price_usd_t * bu / 1000).toFixed(2)} per bushel` : "");
  }
  hint("cost", f.cost_usd_ha ? `= $${(f.cost_usd_ha * AC).toFixed(0)} per acre` : "");
  const ce = DATA.sims[id]?.crop_effect;
  const irrMm = SCENARIO.irrOn ? (ce?.scenario?.water?.irrigation_covered_mm || 0) : 0;
  const seq = ++ECON.seq;
  let b;
  try {
    b = await dataSource.get("/api/economics/budget", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ area_ha: a.request.area_ha, ...f, irrigation_mm: irrMm, bushel_kg: bu || null }) });
  } catch (e) { $("econ-out").textContent = `Budget unavailable: ${e.message}`; return; }
  if (seq !== ECON.seq) return;
  const lines = [];
  if (b.total_cost_usd != null) lines.push(`<div class="row2"><span>Total cost for this field (${fmt(b.area_ha, 1)} ha · ${fmt(b.area_acres, 0)} acres)</span><strong>${usd(b.total_cost_usd)}</strong></div>`);
  if (b.irrigation_cost_usd_ha) lines.push(`<div class="row2"><span>…of which hypothetical irrigation (${fmt(irrMm)} mm)</span><span>${usd(b.irrigation_cost_usd_ha * b.area_ha)}</span></div>`);
  if (b.affordable != null) lines.push(`<div class="row2"><span>Money you can spend</span><strong class="${b.affordable ? "pos" : "neg"}">${b.affordable ? `✓ Enough · ${usd(b.cash_gap_usd)} left` : `✗ Short by ${usd(-b.cash_gap_usd)}`}</strong></div>`);
  if (b.missing_inputs.length) {
    lines.push(`<p class="hint">Fill in ${b.missing_inputs.join(", ")} to see income and margin.</p>`);
  } else {
    lines.push(`<div class="row2"><span>Expected income</span><span>${usd(b.revenue_usd)}</span></div>`);
    lines.push(`<div class="row2"><span>Expected result (income − costs)</span><span class="big ${b.margin_usd >= 0 ? "pos" : "neg"}">${usd(b.margin_usd)}</span></div>`);
    const be = bu ? ` (${fmt(b.breakeven_yield_bu_acre, 0)} bu/acre)` : "";
    lines.push(`<p class="small">To cover all costs you need at least <strong>${fmt(b.breakeven_yield_t_ha, 2)} t/ha${be}</strong>
      ${b.yield_buffer_pct >= 0 ? `— your yield can drop <strong>${fmt(b.yield_buffer_pct, 0)} %</strong> before you lose money` : "— <strong>more than your expected yield</strong>: at these prices you lose money"}.
      Break-even price: ${usd(b.breakeven_price_usd_t)}/t${bu ? ` ($${fmt(b.breakeven_price_usd_bu, 2)}/bu)` : ""}.</p>`);
    const risk = ce && ["water", "heat", "gdd"].filter((k) => ["marginal", "limit"].includes(ce.scenario[k]?.status));
    lines.push(`<table><thead><tr><th>If the yield is…</th><th>t/ha</th><th>Result</th></tr></thead><tbody>
      ${b.what_if.map((w) => `<tr><td>${w.yield_change_pct ? `${w.yield_change_pct} % lower` : "as expected"}</td><td>${fmt(w.yield_t_ha, 2)}</td>
        <td class="${w.margin_usd >= 0 ? "pos" : "neg"}">${usd(w.margin_usd)}</td></tr>`).join("")}</tbody></table>`);
    if (risk && risk.length) lines.push(`<p class="hint">⚠ The climate checks for this scenario flag ${risk.map((k) => ({ water: "water", heat: "heat stress", gdd: "heat accumulation" }[k])).join(" and ")} as tight or limiting: look at the lower-yield rows. The tool does not predict how much yield would drop.</p>`);
  }
  lines.push(`<p class="hint">${esc(b.note || "")}</p>`);
  $("econ-out").innerHTML = lines.join("");
  $("hl-money").textContent = b.margin_usd != null ? `${d.crop || ""}: expected result ${usd(b.margin_usd)}` : "fill in your numbers";
}

function stPair(b, s) {
  const cls = (x) => (x === "n/a" ? "na" : x);
  if (b === s) return `<span class="st-pair"><span class="stb ${cls(s)}" title="Today and in the scenario">${STATUS_TXT[s]}</span></span>`;
  return `<span class="st-pair"><span class="stb ${cls(b)}" title="Today">${STATUS_TXT[b]}</span>→<span class="stb ${cls(s)}" title="Scenario">${STATUS_TXT[s]}</span></span>`;
}

function cropCard(ce) {
  if (!ce) return '<p class="muted small">Pick a crop to see how the scenario affects it.</p>';
  const s = ce.scenario;
  const season = `${MONTHS[ce.season.months[0] - 1]}–${MONTHS[ce.season.months[ce.season.months.length - 1] - 1]}`;
  // The backend sends every check that applies to this crop as {question, base, scenario, detail}.
  const rows = (ce.rows || []).map((x) => [x.question, x.base, x.scenario, x.detail, x.plain]);
  const corr = (ce.corrections || []).length ? `<details><summary>Catalogue values corrected for this crop (${ce.corrections.length})</summary><ul>
      ${ce.corrections.map((c) => `<li><b>${esc(c.field)}</b>: ${esc(c.was ?? "—")} → ${esc(c.now ?? "not used")}. ${esc(c.reason)}</li>`).join("")}</ul></details>` : "";
  return `<div class="cropcard">
    <h3>${esc(ce.crop)} in this scenario <span class="typelabel t-hypothetical">Derived + hypothetical</span></h3>
    <div class="muted small">Season ${season}${ce.season.frost_free_window_only ? " (frost-free part only)" : ""} · averaged over ${s.seasons} seasons of real NASA POWER data · each badge shows Today → Scenario</div>
    <div class="checks">${rows.map(([q, sb, ss, n, p]) => `<div class="check"><span class="q">${esc(q)}</span>${stPair(sb, ss)}
      ${p ? `<span class="plain">${esc(p)}</span>` : ""}<span class="nums">📊 ${esc(n)}</span></div>`).join("")}</div>
    <details><summary>Rules and assumptions</summary><ul>
      ${Object.values(ce.rules).map((t) => `<li>${esc(t)}</li>`).join("")}
      ${ce.assumptions.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>
    ${corr}
    <p class="muted small">Screening checks with visible rules, not a yield forecast.</p>
  </div>`;
}

function updateMode() {
  const a = Object.values(DATA.analyses).filter((x) => x && x.served_from);
  const demo = a.length && a.every((x) => x.served_from === "demo_cache");
  const el = $("mode-badge");
  el.textContent = demo ? "Mode: demo · real data, precomputed" : "Mode: real · live or cached";
  el.className = `mode ${demo ? "demo" : "real"}`;
}

// ---------------------------------------------------------------------------------------------
// Baseline analysis of the active parcel (observed / reanalysis / model data; never the scenario)
function renderAnalysis() {
  const id = SELECTION.active, d = DATA.analyses[id], p = DATA.parcels.find((x) => x.id === id);
  $("parcel-name").textContent = p ? p.name : "";
  if (!d || d.error) { $("parcel-meta").textContent = d?.error ? `Could not load the analysis (${d.error}).` : "Loading data…"; return; }
  const ind = d.indicators, q = d.request;
  const p0 = DATA.parcels.find((x) => x.id === id);
  $("parcel-meta").textContent = `${fmt(q.area_ha, 1)} ha · ${p0?.user ? "your field" : "example parcel (approximate boundary)"} · climate of ${q.start_date.slice(0, 4)}–${q.end_date.slice(0, 4)}`;
  renderRotation(ind.crop_type);
  renderTiles(d);
  renderNdvi(ind.ndvi, ind.ndti, d.derived.bare_months);
  renderWater(ind.agroclimate_power, ind.soil_moisture_smap);
  renderCrops(d);
  renderIndicators(ind);
  renderGaps(d);
}

function renderRotation(ct) {
  const box = $("rotation");
  box.innerHTML = "";
  if (!ct) { box.innerHTML = `<span class="muted small">Crop history unavailable for this parcel.</span>`; return; }
  ct.years.forEach((y) => {
    const top = y.dominant[0] || {};
    const c = CROP_COLORS[top.name] || "#cfd8d3";
    const el = document.createElement("div");
    el.className = "chip";
    el.style.background = c + "33";
    el.style.borderColor = c;
    el.innerHTML = `<b>${esc(y.year)}</b>${esc(top.name || "—")}<br><span class="muted">${Math.round((top.fraction || 0) * 100)}%</span>`;
    box.appendChild(el);
  });
}

function frostFreeDays(power) {
  // Median number of days between the last spring frost and the first autumn frost.
  // The ?. operator returns undefined instead of crashing when a level of the object is missing.
  const rows = power?.frost?.air_frost_0c?.per_year || [];
  const days = rows.filter((r) => r.last_spring_frost && r.first_autumn_frost)
    .map((r) => (new Date(r.first_autumn_frost) - new Date(r.last_spring_frost)) / 86400000)
    .sort((a, b) => a - b);
  return days.length ? days[Math.floor(days.length / 2)] : null;
}

function mmdd(s) {
  if (!s) return "—";
  const [m, d] = s.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

function renderTiles(d) {
  const a = d.indicators.agroclimate_power, s = d.indicators.soil_openlandmap, t = d.indicators.terrain;
  const er = d.derived.erosion_index, bare = d.derived.bare_months;
  const tiles = [
    ["Last spring frost", a ? mmdd(a.frost.air_frost_0c.last_spring_frost.p50) : "—",
      a ? `1 year in 10 after ${mmdd(a.frost.air_frost_0c.last_spring_frost.p90)}` : ""],
    ["Days without frost", a ? fmt(frostFreeDays(a), 0, " days") : "—", "typical year (median)"],
    ["Rain minus what plants use", a ? fmt(a.water_balance.annual_mean_p_minus_et0_mm, 0, " mm") : "—",
      a ? `rain ${fmt(a.water_balance.annual_mean_precip_mm, 0)} mm · demand (ET0) ${fmt(a.et0.annual_mean_mm, 0)} mm a year` : ""],
    ["Heavy-rain days", a ? fmt(a.precip_extremes.mean_per_year.r20mm_days, 1, " a year") : "—",
      a ? `≥ 20 mm in a day · wettest day ${fmt(a.precip_extremes.mean_per_year.rx1day_mm, 0)} mm` : ""],
    ["Soil type", s ? (s.texture_class.name || "—") : "—",
      s ? `acidity pH ${fmt(s.ph_h2o, 1)} · organic carbon ${fmt(s.organic_carbon_g_kg, 0)} g/kg` : ""],
    ["Steepest slopes", t ? fmt(t.slope_deg.p90, 1, "°") : "—", t ? `elevation ${fmt(t.elevation_m.mean, 0)} m` : ""],
    ["Months with bare soil", bare ? (bare.value.map((m) => MONTHS[m - 1]).join(", ") || "none") : "—",
      bare ? `confidence ${bare.confidence}` : ""],
    ["Erosion risk", er ? er.value : "—", er ? "relative, compared with other fields" : "not enough data"],
  ];
  $("tiles").innerHTML = tiles.map(([l, v, s2]) =>
    `<div class="tile"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="sub">${esc(s2)}</div></div>`).join("");
  const last = d.indicators.crop_type?.years?.slice(-1)[0]?.dominant?.[0]?.name;
  $("hl-field").textContent = [s?.texture_class?.name && `${s.texture_class.name} soil`, a && `${fmt(frostFreeDays(a), 0)} frost-free days`,
    last && `last crop: ${last}`].filter(Boolean).join(" · ");
}

const charts = {};
function chart(id, config) {
  // Chart.js keeps a chart attached to its canvas; destroy the old one before drawing a new one,
  // otherwise both would be drawn on top of each other when the user changes parcel.
  if (charts[id]) charts[id].destroy();
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--line");
  charts[id] = new Chart($(id), config);
}

function renderNdvi(ndvi, ndti, bare) {
  if (!ndvi) { $("bare-note").textContent = "Landsat data unavailable."; return; }
  const bareSet = new Set(bare?.value || []);
  chart("ndvi-chart", {
    type: "line",
    data: {
      labels: MONTHS,
      datasets: [
        { label: "NDVI (green cover)", data: ndvi.climatology.map((c) => c.median), borderColor: css("--accent"),
          backgroundColor: css("--accent"), tension: 0.3, pointRadius: 3 },
        { label: "NDTI (residue, read only when NDVI is low)", data: ndti ? ndti.climatology.map((c) => c.median) : [],
          borderColor: css("--demand"), borderDash: [5, 4], pointRadius: 0, tension: 0.3 },
        { label: "Bare / low-cover month", type: "bar", data: MONTHS.map((_, i) => (bareSet.has(i + 1) ? 1 : null)),
          backgroundColor: css("--line"), barPercentage: 1, categoryPercentage: 1, order: 10 },
      ],
    },
    options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 1, title: { display: true, text: "index (0–1)" } } },
      plugins: { legend: { labels: { boxWidth: 12 } } } },
  });
  const cls = (bare?.months || []).map((m) => `${MONTHS[m.month - 1]}: ${m.class.replace(/_/g, " ")}`).join(" · ");
  $("bare-note").textContent = `Median of ${ndvi.climatology[0]?.years ?? "?"} years per month. ${cls ? "Low-cover months — " + cls + "." : ""} NDVI shows green vigour, not fertility or yield.`;
}

function renderWater(power, smap) {
  if (!power) return;
  const mc = power.monthly_climatology;
  const dry = mc.filter((m) => m.p_minus_et0_mm != null && m.p_minus_et0_mm < 0).map((m) => MONTHS[m.month - 1]);
  $("hl-climate").textContent = `${fmt(power.water_balance.annual_mean_precip_mm, 0)} mm of rain a year · ${dry.length ? `drier than plants need in ${dry.length} months` : "rain above plant demand all year"}`;
  const ds = [
    { label: "Rain (mm)", data: mc.map((m) => m.precip_mm), backgroundColor: css("--water"), yAxisID: "y" },
    { label: "Water plants need (ET0, mm)", data: mc.map((m) => m.et0_mm), backgroundColor: css("--demand"), yAxisID: "y" },
  ];
  const scales = { y: { title: { display: true, text: "mm / month" } } };
  if (smap) {
    ds.push({ label: "SMAP root-zone moisture (m³/m³)", type: "line", data: MONTHS.map((_, i) => smap.climatology.find((c) => c.month === i + 1)?.mean ?? null),
      borderColor: css("--ink"), pointRadius: 2, tension: 0.3, yAxisID: "y2" });
    scales.y2 = { position: "right", min: 0, max: 0.5, grid: { drawOnChartArea: false }, title: { display: true, text: "m³/m³" } };
  }
  chart("water-chart", { type: "bar", data: { labels: MONTHS, datasets: ds },
    options: { maintainAspectRatio: false, scales, plugins: { legend: { labels: { boxWidth: 12 } } } } });
}

// Crop catalogue screening of the observed climate (no scenario): the SAME rules as "What to sow here"
// (POST /api/parcel/recommend with all sliders at zero), so the two views can never disagree.
const ST_CLASS = { recommended: "ok", possible: "warn", not_recommended: "bad" };
async function renderCrops(d) {
  const box = $("crop-table"), key = d.request?.cache_key;
  if (!key) { box.innerHTML = ""; return; }
  let r;
  try { r = await dataSource.recommend(key, { dp: 0, dt: 0, irrOn: false, irr: 0 }); }
  catch (e) { box.innerHTML = `<tbody><tr><td class="small">Screening unavailable: ${esc(e.message)}</td></tr></tbody>`; return; }
  if (DATA.analyses[SELECTION.active]?.request?.cache_key !== key) return;     // user moved to another parcel
  const cat = Object.fromEntries(DATA.crops.crops.map((c) => [c.id, c]));
  const rows = r.crops.map((x) => {
    const c = cat[x.crop_id] || {}, w = x.checks.water || {};
    const issues = Object.entries(x.checks).filter(([, v]) => v.status === "limit" || v.status === "marginal")
      .map(([k, v]) => `<li class="${v.status === "limit" ? "bad" : "warn"}" title="${esc(v.detail || "")}">${esc(v.plain || v.detail || k)}</li>`).join("");
    const nb = c.n_balance_kg_ha;
    const nTxt = nb == null ? "—" : nb > 0 ? `<span class="st ok">🌱 adds ~${nb}</span>` : `<span class="st bad">🌾 uses ~${-nb}</span>`;
    return `<tr>
      <td><strong>${esc(x.crop)}</strong>${c.perennial ? ' <span class="muted small">perennial</span>' : ""}</td>
      <td class="st ${ST_CLASS[x.group]}">${GROUP_TXT[x.group]}</td>
      <td>${MONTHS[c.sowing_start_month - 1]}–${MONTHS[c.harvest_end_month - 1]}</td>
      <td class="wrap small">${issues ? `<ul class="issues">${issues}</ul>` : '<span class="st ok">Nothing against it here</span>'}</td>
      <td class="small">${w.status ? `${fmt(x.water_cover_pct)} % of what it needs` : "—"}</td>
      <td title="1 = needs regular water, 5 = copes well with drought">${"●".repeat(c.drought_tolerance_1_5 || 0)}<span class="muted">${"●".repeat(5 - (c.drought_tolerance_1_5 || 0))}</span></td>
      <td>${nTxt} <span class="muted small">kg N/ha</span></td>
      <td class="wrap small">${esc(c.pests_diseases_es)}</td>
    </tr>`;
  }).join("");
  const cnt = (g) => r.crops.filter((x) => x.group === g).length;
  $("hl-catalogue").textContent = `${cnt("recommended")} suit well · ${cnt("possible")} possible with care · ${cnt("not_recommended")} not advisable`;
  box.innerHTML = `<thead><tr><th>Crop</th><th>With today's climate</th><th>Season</th><th>What could go wrong here <span class="muted small">(hover for the numbers)</span></th>
    <th>Rain + soil water</th><th>Copes with drought</th><th>Nitrogen</th><th>Main pests (ES)</th></tr></thead><tbody>${rows}</tbody>`;
}

function renderIndicators(ind) {
  $("indicators").innerHTML = Object.entries(INDICATOR_TITLES).map(([k, title]) => {
    const v = ind[k];
    if (!v) return `<article class="ind missing"><h4>${esc(title)}</h4><p class="muted small">Not available in this response — see information gaps.</p></article>`;
    const w = (v.warnings || []).map((x) => `<li><code>${esc(x.code)}</code> ${esc(x.message)}</li>`).join("");
    return `<article class="ind">
      <h4>${esc(title)}</h4>
      <div class="badges">
        ${v.source.nasa ? '<span class="badge nasa">NASA data</span>' : '<span class="badge">non-NASA</span>'}
        <span class="badge">${esc(v.data_type)}</span>
        <span class="badge">${esc(v.resolution_m >= 1000 ? (v.resolution_m / 1000).toFixed(0) + " km" : v.resolution_m + " m")} · ${esc(v.scale_note.replace(/_/g, " "))}</span>
        <span class="badge conf-${esc(v.confidence)}">confidence: ${esc(v.confidence)}</span>
      </div>
      <div class="small"><strong>${esc(v.source.provider)}</strong></div>
      <div class="ids">${v.source.ids.map(esc).join("<br>")}</div>
      <div class="method">${esc(v.method)}</div>
      <details><summary>Why this confidence${w ? " · " + v.warnings.length + " warning(s)" : ""}</summary>
        <p class="small">${esc(v.confidence_reason)}</p>${w ? `<ul>${w}</ul>` : ""}</details>
    </article>`;
  }).join("");
}

function renderGaps(d) {
  const items = d.data_gaps.map((g) => `<li>${esc(g.reason)} <code>${esc(g.indicator)} · ${esc(g.code)}</code></li>`);
  const der = d.derived.vulnerability;
  if (der) items.push(`<li>Vulnerability months (${esc(der.label)}): ${der.value.length ? der.value.map((m) => MONTHS[m - 1]).join(", ") : "no recurring pattern found"}. <code>derived · vulnerability</code></li>`);
  if (d.derived.erosion_index) items.push(`<li>${esc(d.derived.erosion_index.note)} <code>derived · erosion_index</code></li>`);
  $("gaps").innerHTML = items.join("");
  const n = Object.values(d.indicators).filter(Boolean).length;
  $("hl-evidence").textContent = `${n} data sources used · ${d.data_gaps.length} information gaps`;
}

init().catch((e) => { $("parcel-name").textContent = "Could not start the page"; $("parcel-meta").textContent = e.message; console.error(e); });
