// Integration options: `map` (attach to an existing Leaflet map) and `active`, plus
// setActive()/isActive(). Without those options the component behaves exactly as before.
/*
 * FieldPicker: embeddable Leaflet map to pick ONE crop field in the United States and get its size and location.
 * It does not analyse anything inside the field; it only returns geometry, area, perimeter, centre and place.
 *
 * Needs Leaflet 1.9.x loaded first:
 *   <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
 *   <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
 *   <script src="field-picker.js"></script>
 *
 * Usage:
 *   const picker = FieldPicker.create(document.getElementById("map"), {
 *     onSelect(info) { console.log(info.area.ha, info.centroid.lat, info.centroid.lon, info.geometry); }
 *   });
 *
 * How a field is found:
 *   - Zoom >= 14: crop fields in view are outlined in yellow; click one to select it. Source: USDA NASS Crop Sequence
 *     Boundaries 2017-2024 (contiguous US, field polygons derived from the 30 m CDL); outside the contiguous US,
 *     OpenStreetMap landuse=farmland/meadow/orchard/vineyard through Overpass.
 *   - Click anywhere else: the map asks CSB (then OSM) which field contains that point.
 *   - No field there, or the polygon is wrong: use "Draw" and click the corners yourself; double-click or click the
 *     first corner to finish.
 *   - Optional USDA NASS Cropland Data Layer overlay (CropScape WMS) colours crop types so fields stand out.
 *
 * info passed to onSelect / returned by getSelection():
 *   { geometry: GeoJSON Polygon|MultiPolygon (WGS84, [lon, lat]),
 *     area: { m2, ha, acres }, perimeter_m,
 *     centroid: { lat, lon }, bbox: { south, west, north, east },
 *     place: { state, county, country_code } | null   (filled asynchronously, then onPlace(info) fires),
 *     in_us: boolean, source: "usda_csb" | "osm" | "drawn" | "geojson", source_id: "csb/1924..." | "way/123" | null,
 *     warnings: [string] }
 * The geometry can be sent as is to POST /api/parcel/analyze as {"geometry": info.geometry}.
 */
(function (global) {
  "use strict";

  // USDA NASS Crop Sequence Boundaries 2017-2024: field polygons for the contiguous US (ArcGIS FeatureServer, CORS ok).
  const CSB = "https://pdi.scinet.usda.gov/hosting/rest/services/Hosted/Crop_Sequence_Boundaries_2024/FeatureServer/0/query";
  const OVERPASS = "https://overpass-api.de/api/interpreter";
  const NOMINATIM = "https://nominatim.openstreetmap.org";
  const FIELD_TAGS = "^(farmland|meadow|orchard|vineyard|plant_nursery)$";
  // Rough boxes: contiguous US, Alaska, Hawaii, Puerto Rico. Only used to warn, not to block.
  const US_BOXES = [[24.4, -125.0, 49.5, -66.9], [51.2, -180.0, 71.5, -129.9], [18.8, -160.4, 22.3, -154.7], [17.8, -67.3, 18.6, -65.2]];

  const DEFAULTS = {
    center: [41.99, -93.69],   // central Iowa
    zoom: 13,
    basemap: "satellite",      // "satellite" | "streets"
    highlightFields: true,     // outline OSM crop fields in view
    highlightMinZoom: 14,
    showCdl: false,            // USDA Cropland Data Layer overlay
    cdlYear: 2024,
    reverseGeocode: true,      // state / county through Nominatim
    showSearch: true,
    showPanel: true,
    maxAreaHa: 1000,           // backend limit (config.MAX_AREA_HA); larger selections get a warning
    onSelect: null,
    onPlace: null,
    onClear: null,
  };

  const SOURCE_LABEL = { usda_csb: "USDA Crop Sequence Boundaries", osm: "OpenStreetMap", drawn: "drawn by hand", geojson: "GeoJSON" };
  const STYLE_CANDIDATE = { color: "#ffd400", weight: 1.5, fillColor: "#ffd400", fillOpacity: 0.08 };
  const STYLE_HOVER = { color: "#ffd400", weight: 3, fillOpacity: 0.25 };
  const STYLE_SELECTED = { color: "#ff5a1f", weight: 4, fillColor: "#ff5a1f", fillOpacity: 0.3 };
  const STYLE_DRAFT = { color: "#ff5a1f", weight: 3, dashArray: "6 6" };

  // ---------------------------------------------------------------------------------------------
  // Geometry helpers (WGS84). Areas use the spherical-excess formula, error well under 1% for fields.
  // ---------------------------------------------------------------------------------------------
  const R = 6378137;
  const rad = (d) => (d * Math.PI) / 180;

  function ringArea(ring) {
    let a = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
      a += rad(x2 - x1) * (2 + Math.sin(rad(y1)) + Math.sin(rad(y2)));
    }
    return Math.abs((a * R * R) / 2);
  }
  const polygons = (gj) => (gj.type === "Polygon" ? [gj.coordinates] : gj.coordinates);
  function areaM2(gj) {
    return polygons(gj).reduce((s, p) => s + ringArea(p[0]) - p.slice(1).reduce((h, r) => h + ringArea(r), 0), 0);
  }
  function haversine([x1, y1], [x2, y2]) {
    const a = Math.sin(rad(y2 - y1) / 2) ** 2 + Math.cos(rad(y1)) * Math.cos(rad(y2)) * Math.sin(rad(x2 - x1) / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }
  function perimeterM(gj) {
    let p = 0;
    polygons(gj).forEach((poly) => { const r = poly[0]; for (let i = 0; i < r.length - 1; i++) p += haversine(r[i], r[i + 1]); });
    return p;
  }
  function centroid(gj) {
    // Area-weighted planar centroid of the outer rings; fine at field scale.
    let A = 0, cx = 0, cy = 0;
    polygons(gj).forEach((poly) => {
      const r = poly[0];
      for (let i = 0; i < r.length - 1; i++) {
        const [x1, y1] = r[i], [x2, y2] = r[i + 1], k = x1 * y2 - x2 * y1;
        A += k; cx += (x1 + x2) * k; cy += (y1 + y2) * k;
      }
    });
    if (!A) { const p = polygons(gj)[0][0][0]; return { lat: p[1], lon: p[0] }; }
    return { lat: cy / (3 * A), lon: cx / (3 * A) };
  }
  function bbox(gj) {
    let s = 90, w = 180, n = -90, e = -180;
    polygons(gj).forEach((p) => p[0].forEach(([x, y]) => { s = Math.min(s, y); n = Math.max(n, y); w = Math.min(w, x); e = Math.max(e, x); }));
    return { south: s, west: w, north: n, east: e };
  }
  function pointInRing([x, y], ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function containsPoint(gj, pt) {
    return polygons(gj).some((p) => pointInRing(pt, p[0]) && !p.slice(1).some((h) => pointInRing(pt, h)));
  }
  const inConus = (lat, lon) => { const [s, w, n, e] = US_BOXES[0]; return lat >= s && lat <= n && lon >= w && lon <= e; };
  const inUS = (lat, lon) => US_BOXES.some(([s, w, n, e]) => lat >= s && lat <= n && lon >= w && lon <= e);
  const round6 = (v) => Math.round(v * 1e6) / 1e6;
  function roundGeom(gj) {
    const rr = (ring) => ring.map(([x, y]) => [round6(x), round6(y)]);
    return gj.type === "Polygon"
      ? { type: "Polygon", coordinates: gj.coordinates.map(rr) }
      : { type: "MultiPolygon", coordinates: gj.coordinates.map((p) => p.map(rr)) };
  }
  const same = (a, b) => a[0] === b[0] && a[1] === b[1];
  const close = (ring) => (same(ring[0], ring[ring.length - 1]) ? ring : ring.concat([ring[0]]));

  // Join OSM way segments into closed rings (multipolygon relations split rings across several ways).
  function stitch(segments) {
    const pool = segments.map((s) => s.slice()), rings = [];
    while (pool.length) {
      let ring = pool.shift(), guard = 0;
      while (!same(ring[0], ring[ring.length - 1]) && guard++ < 5000) {
        const end = ring[ring.length - 1];
        const i = pool.findIndex((w) => same(w[0], end) || same(w[w.length - 1], end));
        if (i < 0) break;
        let w = pool.splice(i, 1)[0];
        if (!same(w[0], end)) w = w.reverse();
        ring = ring.concat(w.slice(1));
      }
      if (same(ring[0], ring[ring.length - 1]) && ring.length >= 4) rings.push(ring);
    }
    return rings;
  }

  // Overpass element (out geom) -> GeoJSON Polygon/MultiPolygon, or null.
  function elementToGeom(el) {
    const pts = (g) => g.map((p) => [p.lon, p.lat]);
    if (el.type === "way" && el.geometry && el.geometry.length >= 4) {
      return { type: "Polygon", coordinates: [close(pts(el.geometry))] };
    }
    if (el.type === "relation" && el.members) {
      const outer = [], inner = [];
      el.members.forEach((m) => { if (m.type === "way" && m.geometry) (m.role === "inner" ? inner : outer).push(pts(m.geometry)); });
      const outers = stitch(outer), inners = stitch(inner);
      if (!outers.length) return null;
      const polys = outers.map((o) => [o]);
      inners.forEach((h) => { const p = polys.find((poly) => pointInRing(h[0], poly[0])); if (p) p.push(h); });
      return polys.length === 1 ? { type: "Polygon", coordinates: polys[0] } : { type: "MultiPolygon", coordinates: polys };
    }
    return null;
  }

  async function overpass(query, signal) {
    const r = await fetch(OVERPASS, {
      method: "POST", signal,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "data=" + encodeURIComponent(query),
    });
    if (!r.ok) throw new Error("Overpass HTTP " + r.status);
    const data = await r.json();
    return (data.elements || [])
      .map((el) => ({ id: el.type + "/" + el.id, tags: el.tags || {}, geom: elementToGeom(el) }))
      .filter((f) => f.geom);
  }
  const fieldsInBBox = (b, signal) => overpass(
    `[out:json][timeout:20];(way["landuse"~"${FIELD_TAGS}"](${b});relation["landuse"~"${FIELD_TAGS}"](${b}););out geom;`, signal);
  const fieldsAtPoint = (lat, lon, signal) => overpass(
    `[out:json][timeout:20];is_in(${lat},${lon})->.a;(way(pivot.a)["landuse"~"${FIELD_TAGS}"];relation(pivot.a)["landuse"~"${FIELD_TAGS}"];);out geom;`, signal);

  async function csbQuery(geometry, geometryType, signal) {
    const p = new URLSearchParams({
      f: "geojson", geometry, geometryType, inSR: "4326", outSR: "4326", spatialRel: "esriSpatialRelIntersects",
      outFields: "csbid,csbacres,cnty,statefips", returnGeometry: "true", geometryPrecision: "6", resultRecordCount: "2000",
    });
    const r = await fetch(CSB + "?" + p, { signal });
    if (!r.ok) throw new Error("USDA CSB HTTP " + r.status);
    const data = await r.json();
    if (data.error) throw new Error("USDA CSB: " + (data.error.message || "error"));
    return (data.features || [])
      .filter((f) => f.geometry && /^(Multi)?Polygon$/.test(f.geometry.type))
      .map((f) => ({ id: "csb/" + f.properties.csbid, tags: f.properties, geom: f.geometry }));
  }
  const csbInBBox = (b, signal) => { const [s, w, n, e] = b.split(","); return csbQuery([w, s, e, n].join(","), "esriGeometryEnvelope", signal); };
  const csbAtPoint = (lat, lon, signal) => csbQuery(`${lon},${lat}`, "esriGeometryPoint", signal);

  async function reverseGeocode(lat, lon) {
    const r = await fetch(`${NOMINATIM}/reverse?format=jsonv2&zoom=10&addressdetails=1&lat=${lat}&lon=${lon}`);
    if (!r.ok) throw new Error("Nominatim HTTP " + r.status);
    const a = (await r.json()).address || {};
    return { state: a.state || null, county: a.county || a.city || a.town || null, country_code: (a.country_code || "").toUpperCase() || null };
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtN = (v, d) => v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });

  // ---------------------------------------------------------------------------------------------
  // Styles (scoped with the .fp- prefix, injected once)
  // ---------------------------------------------------------------------------------------------
  function injectCss() {
    if (document.getElementById("fp-css")) return;
    const s = document.createElement("style");
    s.id = "fp-css";
    s.textContent = `
      .fp-box { background:#fff; color:#1d2420; border-radius:8px; box-shadow:0 1px 5px rgba(0,0,0,.35);
        font:13px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
      .fp-bar { display:flex; gap:4px; padding:4px; flex-wrap:wrap; max-width:320px; }
      .fp-bar input { flex:1; min-width:120px; padding:5px 7px; border:1px solid #cfd6cf; border-radius:6px; font:inherit; }
      .fp-btn { padding:5px 9px; border:1px solid #cfd6cf; border-radius:6px; background:#f6f7f4; color:inherit; font:inherit; cursor:pointer; }
      .fp-btn:hover { border-color:#2f7d4f; }
      .fp-btn.fp-on { background:#2f7d4f; border-color:#2f7d4f; color:#fff; }
      .fp-status { padding:4px 8px; font-size:12px; color:#5d6a62; }
      .fp-status:empty { display:none; }
      .fp-panel { width:270px; max-width:calc(100vw - 40px); padding:10px 12px; }
      .fp-panel h4 { margin:0 0 6px; font-size:13px; }
      .fp-row { display:flex; justify-content:space-between; gap:10px; padding:3px 0; border-top:1px dashed #dfe4df; }
      .fp-row span:last-child { text-align:right; font-family:ui-monospace,Consolas,monospace; font-size:12px; }
      .fp-warn { color:#9a5b00; font-size:12px; margin-top:6px; }
      .fp-muted { color:#5d6a62; font-size:12px; }
      @media (prefers-color-scheme: dark) {
        .fp-box { background:#1b201d; color:#e6ebe7; }
        .fp-bar input, .fp-btn { background:#121614; border-color:#2c3430; color:#e6ebe7; }
        .fp-status, .fp-muted { color:#9aa69f; }
        .fp-row { border-color:#2c3430; }
        .fp-warn { color:#f0b45a; }
      }`;
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------------------------------------
  // Component
  // ---------------------------------------------------------------------------------------------
  function create(container, options) {
    if (!global.L) throw new Error("FieldPicker needs Leaflet (window.L) loaded first.");
    const L = global.L;
    const opts = Object.assign({}, DEFAULTS, options || {});
    injectCss();

    // Integration (Field Shift viewer): `opts.map` attaches the picker to an existing Leaflet map instead of
    // creating one (one map instance per page); the host keeps its own basemap, layer control and scale.
    const attached = !!opts.map;
    const map = attached ? opts.map : L.map(container, { zoomControl: true, doubleClickZoom: true }).setView(opts.center, opts.zoom);
    const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
    const labels = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19 });
    const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" });
    if (!attached) {
      (opts.basemap === "streets" ? streets : satellite).addTo(map);
      labels.addTo(map);
    }
    // USDA NASS CDL through CropScape WMS. The service rejects EPSG:3857, so request EPSG:4326 tiles.
    const cdl = L.tileLayer.wms("https://nassgeodata.gmu.edu/CropScapeService/wms_cdlall.cgi", {
      layers: "cdl_" + opts.cdlYear, format: "image/png", transparent: true, opacity: 0.5, version: "1.1.1",
      crs: L.CRS.EPSG4326, attribution: "USDA NASS Cropland Data Layer " + opts.cdlYear });
    if (opts.showCdl) cdl.addTo(map);
    const candidates = L.featureGroup().addTo(map);
    if (!attached) {
      const overlays = { "Place labels": labels, ["Crop types (USDA CDL " + opts.cdlYear + ")"]: cdl };
      if (opts.highlightFields) overlays["Field outlines"] = candidates;
      L.control.layers({ Satellite: satellite, Streets: streets }, overlays, { position: "topleft" }).addTo(map);
      L.control.scale({ imperial: true, metric: true }).addTo(map);
    }
    map.attributionControl.addAttribution("Fields: USDA NASS Crop Sequence Boundaries, © OpenStreetMap contributors");
    // Integration: when `active` is false the picker ignores map clicks, hides its controls and field outlines.
    let active = opts.active !== false;

    // ---- toolbar (top-right) ------------------------------------------------------------------
    const Bar = L.Control.extend({
      onAdd() {
        const div = L.DomUtil.create("div", "fp-box");
        div.innerHTML = `
          ${opts.showSearch ? `<form class="fp-bar" data-fp="search"><input type="search" placeholder="Search a US place" aria-label="Search a US place"><button class="fp-btn" type="submit">Go</button></form>` : ""}
          <div class="fp-bar">
            <button class="fp-btn fp-on" data-fp="click" title="Click a field on the map to select it">Click field</button>
            <button class="fp-btn" data-fp="draw" title="Click the field corners; double-click to finish">Draw</button>
            <button class="fp-btn" data-fp="clear">Clear</button>
          </div>
          <div class="fp-status" data-fp="status"></div>`;
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        return div;
      },
    });
    const bar = new Bar({ position: "topright" }).addTo(map);
    const barEl = bar.getContainer();
    const $ = (k) => barEl.querySelector(`[data-fp="${k}"]`);
    const statusEl = $("status");
    const setStatus = (t) => { statusEl.textContent = t || ""; };

    let panel = null;
    if (opts.showPanel) {
      const Panel = L.Control.extend({
        onAdd() { const d = L.DomUtil.create("div", "fp-box fp-panel"); L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); return d; },
      });
      panel = new Panel({ position: "bottomleft" }).addTo(map);
    }

    // ---- state --------------------------------------------------------------------------------
    let mode = "click";
    let selection = null;     // info object
    let selectedLayer = null;
    let bboxCtl = null, pointCtl = null, placeSeq = 0, loadTimer = null, lastBBox = "";

    function describe(geom, source, sourceId) {
      const g = roundGeom(geom);
      const m2 = areaM2(g), c = centroid(g);
      const warnings = [];
      if (!inUS(c.lat, c.lon)) warnings.push("Outside the United States: CDL and US soil layers will not cover it.");
      if (m2 / 1e4 > opts.maxAreaHa) warnings.push(`Larger than ${opts.maxAreaHa} ha; the backend will reject it. The source may group several fields here: use Draw.`);
      if (source === "usda_csb") warnings.push("USDA CSB edges follow 30 m Landsat pixels, so they look stepped; area is approximate.");
      if (m2 / 1e4 < 0.1) warnings.push("Very small polygon (< 0.1 ha).");
      return {
        geometry: g,
        area: { m2: Math.round(m2), ha: Math.round(m2 / 100) / 100, acres: Math.round((m2 / 4046.8564224) * 100) / 100 },
        perimeter_m: Math.round(perimeterM(g)),
        centroid: { lat: round6(c.lat), lon: round6(c.lon) },
        bbox: Object.fromEntries(Object.entries(bbox(g)).map(([k, v]) => [k, round6(v)])),
        place: null, in_us: inUS(c.lat, c.lon), source, source_id: sourceId || null, warnings,
      };
    }

    function select(geom, source, osmId) {
      clearSelection(false);
      const info = describe(geom, source, osmId);
      selection = info;
      selectedLayer = L.geoJSON(info.geometry, { style: () => STYLE_SELECTED, interactive: false }).addTo(map);
      renderPanel();
      setStatus("");
      if (typeof opts.onSelect === "function") opts.onSelect(info);
      if (opts.reverseGeocode) {
        const seq = ++placeSeq;
        reverseGeocode(info.centroid.lat, info.centroid.lon)
          .then((place) => {
            if (seq !== placeSeq || selection !== info) return;
            info.place = place;
            renderPanel();
            if (typeof opts.onPlace === "function") opts.onPlace(info);
          })
          .catch(() => { /* place is optional */ });
      }
      return info;
    }

    function clearSelection(notify = true) {
      if (selectedLayer) map.removeLayer(selectedLayer);
      selectedLayer = null;
      const had = !!selection;
      selection = null;
      placeSeq++;
      renderPanel();
      if (notify && had && typeof opts.onClear === "function") opts.onClear();
    }

    function renderPanel() {
      if (!panel) return;
      const el = panel.getContainer();
      if (!selection) {
        el.innerHTML = `<h4>No field selected</h4><div class="fp-muted">Zoom in (fields are outlined in yellow from zoom ${opts.highlightMinZoom}) and click a field, or use <b>Draw</b> to outline it.</div>`;
        return;
      }
      const s = selection, c = s.centroid, b = s.bbox;
      const place = s.place ? [s.place.county, s.place.state].filter(Boolean).join(", ") || "-" : (opts.reverseGeocode ? "…" : "-");
      el.innerHTML = `
        <h4>Selected field <span class="fp-muted">(${esc(SOURCE_LABEL[s.source] || s.source)}${s.source_id ? " " + esc(s.source_id) : ""})</span></h4>
        <div class="fp-row"><span>Area</span><span>${fmtN(s.area.ha, 2)} ha<br>${fmtN(s.area.acres, 2)} ac</span></div>
        <div class="fp-row"><span>Perimeter</span><span>${fmtN(s.perimeter_m, 0)} m</span></div>
        <div class="fp-row"><span>Centre (lat, lon)</span><span>${c.lat.toFixed(6)}, ${c.lon.toFixed(6)}</span></div>
        <div class="fp-row"><span>Bounds S,W</span><span>${b.south.toFixed(5)}, ${b.west.toFixed(5)}</span></div>
        <div class="fp-row"><span>Bounds N,E</span><span>${b.north.toFixed(5)}, ${b.east.toFixed(5)}</span></div>
        <div class="fp-row"><span>Place</span><span>${esc(place)}</span></div>
        ${s.warnings.map((w) => `<div class="fp-warn">⚠ ${esc(w)}</div>`).join("")}
        <div class="fp-bar" style="padding:6px 0 0">
          <button class="fp-btn" data-copy="centre">Copy centre</button>
          <button class="fp-btn" data-copy="json">Copy JSON</button>
        </div>`;
      el.querySelectorAll("[data-copy]").forEach((btn) => {
        btn.onclick = () => {
          const text = btn.dataset.copy === "centre" ? `${c.lat}, ${c.lon}` : JSON.stringify(s, null, 2);
          (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
            .then(() => { const t = btn.textContent; btn.textContent = "Copied ✓"; setTimeout(() => (btn.textContent = t), 1200); })
            .catch(() => global.prompt("Copy:", text));
        };
      });
    }

    // ---- highlight mapped fields in view --------------------------------------------------------
    function loadCandidates() {
      if (!active || !opts.highlightFields || !map.hasLayer(candidates)) return;
      if (map.getZoom() < opts.highlightMinZoom) { candidates.clearLayers(); lastBBox = ""; return; }
      const b = map.getBounds().pad(0.1);
      const key = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map((v) => v.toFixed(4)).join(",");
      if (key === lastBBox) return;
      if (bboxCtl) bboxCtl.abort();
      bboxCtl = new AbortController();
      setStatus("Looking for crop fields…");
      const c = b.getCenter(), useCsb = inConus(c.lat, c.lng);
      (useCsb ? csbInBBox(key, bboxCtl.signal) : fieldsInBBox(key, bboxCtl.signal))
        .then((found) => {
          lastBBox = key;
          candidates.clearLayers();
          found.forEach((f) => {
            const layer = L.geoJSON(f.geom, { style: () => STYLE_CANDIDATE });
            layer.on("mouseover", (e) => { if (mode === "click") e.layer.setStyle(STYLE_HOVER); });
            layer.on("mouseout", (e) => e.layer.setStyle(STYLE_CANDIDATE));
            layer.on("click", (e) => { if (mode !== "click") return; L.DomEvent.stopPropagation(e); select(f.geom, useCsb ? "usda_csb" : "osm", f.id); });
            layer.bindTooltip(() => useCsb ? `Field ${f.tags.csbid} · ${fmtN(+f.tags.csbacres || 0, 1)} ac` : (f.tags.crop ? `${f.tags.landuse} · ${f.tags.crop}` : f.tags.landuse), { sticky: true });
            candidates.addLayer(layer);
          });
          setStatus(found.length ? `${found.length} crop field${found.length > 1 ? "s" : ""} in view${found.length >= 2000 ? " (first 2000; zoom in)" : ""}` : "No crop fields mapped here: use Draw");
        })
        .catch((err) => { if (err.name !== "AbortError") setStatus("Field outlines unavailable (" + err.message + ")"); });
    }
    map.on("moveend", () => { clearTimeout(loadTimer); loadTimer = setTimeout(loadCandidates, 400); });
    map.on("overlayadd", (e) => { if (e.layer === candidates) { lastBBox = ""; loadCandidates(); } });

    // ---- click mode: find the field that contains the point -------------------------------------
    function pickAt(latlng) {
      const lat = round6(latlng.lat), lon = round6(latlng.lng);
      if (!inUS(lat, lon)) { setStatus("That point is outside the United States."); return; }
      // Already loaded outline under the cursor? Use the smallest one.
      if (pointCtl) pointCtl.abort();
      pointCtl = new AbortController();
      const signal = pointCtl.signal;
      setStatus("Finding the field at this point…");
      const best = (found) => found.filter((f) => containsPoint(f.geom, [lon, lat])).sort((a, b) => areaM2(a.geom) - areaM2(b.geom))[0];
      (async () => {
        let hit = null, src = "usda_csb";
        if (inConus(lat, lon)) { try { hit = best(await csbAtPoint(lat, lon, signal)); } catch (err) { if (err.name === "AbortError") throw err; } }
        if (!hit) { src = "osm"; hit = best(await fieldsAtPoint(lat, lon, signal)); }
        if (!hit) { setStatus("No crop field mapped at this point: use Draw to outline it."); return; }
        select(hit.geom, src, hit.id);
      })().catch((err) => { if (err.name !== "AbortError") setStatus("Lookup failed (" + err.message + "): use Draw."); });
    }

    // ---- draw mode: click corners, double-click / first corner to finish ------------------------
    let pts = [], draftLine = null, draftGuide = null, draftMarkers = null;
    function resetDraft() {
      pts = [];
      [draftLine, draftGuide, draftMarkers].forEach((l) => l && map.removeLayer(l));
      draftLine = L.polyline([], STYLE_DRAFT).addTo(map);
      draftGuide = L.polyline([], { ...STYLE_DRAFT, weight: 1.5, opacity: 0.7 }).addTo(map);
      draftMarkers = L.layerGroup().addTo(map);
    }
    function finishDraft() {
      if (pts.length < 3) { setStatus("A field needs at least 3 corners."); return; }
      const ring = close(pts.map((p) => [p.lng, p.lat]));
      setMode("click");
      select({ type: "Polygon", coordinates: [ring] }, "drawn", null);
    }
    function addCorner(latlng) {
      if (pts.length >= 3 && map.latLngToContainerPoint(latlng).distanceTo(map.latLngToContainerPoint(pts[0])) < 10) { finishDraft(); return; }
      pts.push(latlng);
      draftLine.setLatLngs(pts);
      L.circleMarker(latlng, { radius: pts.length === 1 ? 6 : 4, color: "#ff5a1f", fillColor: "#fff", fillOpacity: 1, weight: 2 }).addTo(draftMarkers);
      setStatus(`${pts.length} corner${pts.length > 1 ? "s" : ""}. Double-click or click the first corner to finish · Backspace undo · Esc cancel`);
    }

    function setMode(m) {
      mode = m;
      $("click").classList.toggle("fp-on", m === "click");
      $("draw").classList.toggle("fp-on", m === "draw");
      map.getContainer().style.cursor = m === "draw" ? "crosshair" : "";
      if (m === "draw") { map.doubleClickZoom.disable(); resetDraft(); setStatus("Click the first corner of the field."); }
      else {
        map.doubleClickZoom.enable();
        [draftLine, draftGuide, draftMarkers].forEach((l) => l && map.removeLayer(l));
        draftLine = draftGuide = draftMarkers = null; pts = [];
        setStatus("");
      }
    }

    map.on("click", (e) => { if (!active) return; if (mode === "draw") addCorner(e.latlng); else pickAt(e.latlng); });
    map.on("dblclick", (e) => {
      if (!active || mode !== "draw") return;
      // The two clicks of a double-click already added the same corner twice; drop the duplicate.
      if (pts.length >= 2 && map.latLngToContainerPoint(pts[pts.length - 1]).distanceTo(map.latLngToContainerPoint(pts[pts.length - 2])) < 6) pts.pop();
      finishDraft();
    });
    map.on("mousemove", (e) => { if (active && mode === "draw" && pts.length && draftGuide) draftGuide.setLatLngs([pts[pts.length - 1], e.latlng, pts[0]]); });
    const onKey = (e) => {
      if (!active || mode !== "draw") return;
      if (e.key === "Escape") setMode("click");
      if (e.key === "Backspace" && pts.length && !/input|textarea/i.test(e.target.tagName)) {
        e.preventDefault(); pts.pop(); const p = pts.slice(); resetDraft(); p.forEach(addCorner);
      }
    };
    document.addEventListener("keydown", onKey);

    $("click").onclick = () => setMode("click");
    $("draw").onclick = () => setMode(mode === "draw" ? "click" : "draw");
    $("clear").onclick = () => { setMode("click"); clearSelection(true); };

    if (opts.showSearch) {
      $("search").onsubmit = async (e) => {
        e.preventDefault();
        const q = e.target.querySelector("input").value.trim();
        if (!q) return;
        setStatus("Searching…");
        try {
          const r = await fetch(`${NOMINATIM}/search?format=jsonv2&limit=1&countrycodes=us&q=` + encodeURIComponent(q));
          const [hit] = await r.json();
          if (!hit) { setStatus("No US place found for: " + q); return; }
          const [s, n, w, ea] = hit.boundingbox.map(Number);
          map.fitBounds([[s, w], [n, ea]], { maxZoom: 15 });
          setStatus("");
        } catch (err) { setStatus("Search failed (" + err.message + ")"); }
      };
    }

    function setActive(on) {
      active = !!on;
      if (active) {
        if (!bar._map) bar.addTo(map);
        if (panel && !panel._map) panel.addTo(map);
        lastBBox = "";
        renderPanel();
        loadCandidates();
      } else {
        setMode("click");
        if (bboxCtl) bboxCtl.abort();
        if (pointCtl) pointCtl.abort();
        candidates.clearLayers();
        lastBBox = "";
        clearSelection(false);
        if (bar._map) map.removeControl(bar);
        if (panel && panel._map) map.removeControl(panel);
      }
    }

    renderPanel();
    if (active) loadCandidates(); else setActive(false);

    // ---- public API ---------------------------------------------------------------------------
    return {
      map,
      getSelection: () => selection,
      clear: () => clearSelection(true),
      setMode,
      setActive,
      isActive: () => active,
      /** Select an existing GeoJSON Polygon/MultiPolygon (or Feature), e.g. a saved parcel. */
      selectGeoJSON(gj, zoom = true) {
        const g = gj.type === "Feature" ? gj.geometry : gj;
        if (!g || !/^(Multi)?Polygon$/.test(g.type)) throw new Error("Polygon or MultiPolygon expected");
        const info = select(g, "geojson", null);
        if (zoom) map.fitBounds(selectedLayer.getBounds().pad(0.4), { maxZoom: 17 });
        return info;
      },
      flyTo: (lat, lon, zoom = 15) => map.flyTo([lat, lon], zoom),
      showCdl: (on) => (on ? cdl.addTo(map) : map.removeLayer(cdl)),
      destroy() { document.removeEventListener("keydown", onKey); map.remove(); },
    };
  }

  global.FieldPicker = { create, areaM2, centroid, bbox, version: "1.0.0" };
})(window);
