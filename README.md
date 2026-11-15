# Field Shift: data layer (NASA Space Apps 2026)

Team **Los Desastronautas** · Challenge "Field Shift: Adapting Farms with NASA Data"

Backend for the "Field Shift: Adapting Farms with NASA Data" challenge. Given a parcel (GeoJSON
point or polygon) it returns traceable satellite, climate and soil indicators for the
rotation-comparison module. It does **not** recommend crops.

Every indicator carries its source IDs, `nasa: true|false`, `data_type`, `resolution_m`,
`scale_note`, method, thresholds, `confidence` with its reason, and warnings with stable codes.
Design and the verified dataset facts are in [docs/DOSSIER-field-shift.md](docs/DOSSIER-field-shift.md)
(sections 3.2, 5, 6, 8); the build brief is [docs/PROMPT-field-shift-backend.md](docs/PROMPT-field-shift-backend.md).

## Quick start (one command)

Requires **Python 3.11 or later** (`earthengine-api` 1.7.52 needs it).

- **Windows:** double-click `start.bat` (creates `.venv`, installs the packages, starts the app).
- **Any OS:** `python run.py`

`run.py` creates `.env`, installs missing packages, asks whether you want Earth Engine and opens
http://127.0.0.1:8000/. **Earth Engine is optional**: without it the app runs with sources that need
no account (NASA POWER climate, USDA SSURGO soil, USDA CropScape crop history), so the simulator and
the crop recommendation work out of the box. Earth Engine adds NDVI (Landsat), SMAP soil moisture
and the 30 m slope / risk zones. `python run.py --setup` configures it at any time: it opens the Google
sign-in, reuses a project that already works (stored in your EE credentials or listed by `gcloud`),
otherwise opens the project-creation and Earth Engine registration pages, checks the project answers
and writes `EE_PROJECT_ID` to `.env`. (Google does not let the Earth Engine sign-in create or list
Cloud projects by API, so those two web pages remain a one-time manual step.)

## Local setup (manual)

Windows / PowerShell (the team's setup):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env              # optional: fill EE_PROJECT_ID (or run python run.py --setup)
python -m pytest tests -q                # formula + simulator unit tests (no network)
python -m scripts.smoke                  # real APIs on the demo parcels, trimmed output
python -m scripts.build_demo             # precompute demo parcels (analysis, POWER series, terrain grid)
uvicorn backend.api:app --reload --port 8000
# open http://127.0.0.1:8000/  (viewer + simulator)  or  http://127.0.0.1:8000/docs  (API test page)
python -m scripts.simulate_smoke --http  # simulator deltas + 20-move HTTP timing (server running)
```

Use `127.0.0.1` rather than `localhost` in scripts on Windows: `localhost` tries IPv6 first and
adds ~2 s per request from Python.

```bash
curl -X POST http://localhost:8000/api/parcel/analyze -H "Content-Type: application/json" \
  -d '{"geometry": {"type": "Point", "coordinates": [-120.11, 36.34]}}'
```

Without Earth Engine the API still answers: NASA POWER and the climate indicators are filled; soil
comes from USDA SSURGO (Soil Data Access) and crop history from the CDL through CropScape (3 sample
points per year), both public and without login; NDVI/NDTI, SMAP and terrain are `null` with a
`GEE_UNAVAILABLE` entry in `data_gaps`. When Earth Engine is configured later, cached fields with
`GEE_UNAVAILABLE` gaps are recomputed automatically; gaps from a temporarily unavailable service
are retried after one hour. Checked on the cached Iowa fields: SSURGO pH / clay / sand within ~0.7
pH unit and ~6 points of OpenLandMap, same texture class in 3 of 5 (SSURGO organic carbon and field
capacity run higher than OpenLandMap's); CropScape dominant crop equal to
the Earth Engine histogram in every year that answered (42 of 45).

### Earth Engine authentication

- **Development:** `earthengine authenticate` (or `gcloud auth application-default login`), and
  set `EE_PROJECT_ID` to a Cloud project registered for noncommercial Earth Engine use.
- **Production / shared server:** a service account with `roles/earthengine.writer` and
  `roles/serviceusage.serviceUsageConsumer` (without the latter `ee.Initialize` fails), Earth
  Engine API enabled on the project. Expose it through `GOOGLE_APPLICATION_CREDENTIALS` or the
  platform identity (e.g. Cloud Run); no code changes. Never commit the key (see `.gitignore`).
- Quota: the noncommercial Community tier is **150 EECU-hours/month**. Precompute the demo
  parcels (`python -m scripts.build_demo`) before recording, and do not use several projects to
  dodge the quota (against the terms).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `EE_PROJECT_ID` | none | Cloud project for Earth Engine (`python run.py --setup` fills it). Unset = project stored in the EE credentials, else no-login sources only |
| `GOOGLE_APPLICATION_CREDENTIALS` | none | Service-account key path (production only) |
| `FS_CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Frontend origins |
| `FS_POINT_BUFFER_M` | 50 | Buffer applied to point input |
| `FS_MAX_AREA_HA` / `FS_MAX_VERTICES` | 1000 / 2000 | Geometry limits |
| `FS_DEFAULT_YEARS` / `FS_MAX_YEARS` | 10 / 25 | Default period (last N complete years) / maximum |
| `FS_CACHE_DIR` | `data/cache` | POWER cell cache and response cache |

## Layout

```
backend/
  config.py        dataset IDs, thresholds (each tagged standard / hypothesis), limits
  gee_client.py    one-time ee.Initialize
  geometry.py      validation, point buffer, area, cache hash
  contract.py      indicator builder, warning codes, citations
  et0.py           FAO-56 Penman-Monteith and Hargreaves-Samani
  derived.py       pure functions: frost, heat, ET0, P-ET0, R95p/R20mm/Rx1day, bare months,
                   vulnerability, erosion index
  sources/         power.py, landsat.py, smap.py, terrain.py, soil.py, croptype.py;
                   no-login fallbacks soil_sda.py (USDA SSURGO) and cdl_cropscape.py (USDA CropScape)
  crop_effects.py  per-crop screening checks (FAO-56 water, GDD, heat, frost, winter, humidity)
  catalog/         crops_us.csv (team catalogue) + crop_params.json (sourced parameters, corrections)
  analyze.py       parallel modules with per-module timeouts, cache, demo cache
  api.py           POST /api/parcel/analyze, GET /api/demo/parcels, GET /api/crops, serves the page
  crops.py         parses the team crop catalogue (catalog/crops_us.csv)
  static/          web page (index.html, app.js, styles.css): http://localhost:8000/
  demo_cache/      precomputed demo responses (served with "served_from": "demo_cache")
run.py, start.bat  one-command launcher and optional Earth Engine setup
scripts/           demo_parcels.json, build_demo.py, smoke.py, validate_crops.py (reality check)
tests/             test_formulas.py
legacy/            the earlier climate-only module (climate.json); superseded, kept for reference
```

## API contract (version 1)

`POST /api/parcel/analyze` with `{"geometry": GeoJSON, "start_date"?, "end_date"?, "farmer_priorities"?}`.
Response: `version, generated_at, served_from (live|cache|demo_cache), request, indicators
{ndvi, ndti, soil_moisture_smap, agroclimate_power, terrain, soil_openlandmap,
precipitation_imerg, crop_type}, derived {bare_months, vulnerability, erosion_index}, layers,
data_gaps [{indicator, code, reason}], warnings [{code, message}], provenance {ai_assistance, citations}`.
Errors: 422 with `{code, message}` (`GEOMETRY_INVALID`, `GEOMETRY_TOO_LARGE`,
`GEOMETRY_TOO_MANY_VERTICES`, `GEOMETRY_UNSUPPORTED_TYPE`, `GEOMETRY_OUT_OF_RANGE`, `BAD_REQUEST`);
502 only if every source fails.

Other endpoints: `GET /api/demo/parcels`, `GET /api/crops`, `GET /api/parcel/terrain-grid?hash=`,
`POST /api/parcel/simulate` (see below).

`data_type`: `satellite`, `satellite_gauge_merged`, `reanalysis`, `model`, `derived`,
`user_input`, `in_situ`. `scale_note`: `parcel`, `sub_parcel_mixed`, `zone`.

Honesty rules built into the output: NDVI is labelled as green vigour, not fertility or yield;
`GWETROOT` is a 0-1 wetness index, not volumetric moisture (and is hidden when flat); the erosion
index is a relative screening index, never t/ha/yr, and needs at least 3 of its 4 factors;
vulnerability is labelled co-occurrence, not causation.

## Adding a real field (team module `field-picker.js`)

"+ Add a field from the map" turns on the team's field picker on the same map: from zoom 14,
USDA Crop Sequence Boundaries fields are outlined in yellow (OSM outside the contiguous US);
click one, or press Draw and click the corners. "Analyze this field" posts the polygon to
`/api/parcel/analyze` (~30-60 s live the first time), adds it to the parcel list (kept in the
viewer's browser) and it works with every layer, the simulator and the crop checks.
Integration changes to `field-picker.js`: options `map` (attach to the existing map) and
`active` + `setActive()`; without them it behaves as the standalone version
(see `docs/conversacion-field-picker.md`).

## What to sow here: crop recommendation and sowing dates

`POST /api/parcel/recommend` (same body as `simulate`; `backend/recommend.py`) screens the 15
catalogue crops for the parcel under the current scenario and returns them in three groups:
**recommended** (no check tight or limiting), **possible with care** (some tight) and **not
recommended** (any limiting). Checks per crop, all visible with their reason
(`backend/crop_effects.py`, parameters and sources in `backend/catalog/crop_params.json`):

| Check | Rule | Source |
|---|---|---|
| Heat to mature | GDD of the frost-free part of the season (killing freeze -2 °C) vs the minimum of the earliest commercial cultivars; 86/50 caps for corn, soybean, sorghum | McMaster & Wilhelm 1997; ISU/NDSU |
| Water | need = Kc × ET0 of the season; supply = rain + soil water stored before the season (≤ 100 mm) + hypothetical irrigation; FAO-33 loss = Ky × (1 − supply/need): ok < 15 %, limit ≥ 75 % or < 25 % covered | FAO-56 Tables 11-12, FAO-33 |
| Heat at flowering | days with Tmax ≥ the crop's reproductive failure temperature; ≥ 10 = tight, never limiting alone | Hatfield et al. 2011 |
| Summer heat (potato, sugar beet, barley) | mean temperature of the hottest season month | team calibration |
| Frost-free season, frost at sowing | median frost-free days vs crop minimum; P90 last spring frost vs sowing window | |
| Winter cold (wheat, grape, almond, sugarcane) | average annual extreme minimum (the USDA hardiness-zone variable) | USDA zones |
| Vernalization (winter wheat) | days 0-10 °C, October-March | Porter & Gawith 1999 |
| Humid climate (almond, vinifera grape, alfalfa) | June-August rain; Pierce's disease (mild winter + humid summer) | team rules |
| Frost at bloom (almond) | P90 last spring frost vs February-March bloom | team rule |
| Soil pH, texture (rice, peanut), rotation | catalogue optimum pH; texture classes; last year's CDL crop | |

Within a group: fewest tight checks, rotation benefit, years grown on this field (CDL), rain cover.

**Plain language.** Every check carries `plain` (what it means, in everyday words) next to `detail`
(the numbers); every crop carries a one-line `verdict`, `reasons` in plain words and
`reasons_numbers`. The page shows the explanation first and the figures under "📊".

**Rotation plan (`rotation_plan` in `/recommend`).** For the next 4 seasons it alternates a crop that
adds nitrogen (legume, positive N balance in the catalogue: soybean, peanut) with one that uses it
(negative balance: corn, wheat, sorghum, cotton…), choosing among the crops that pass the checks
(ignoring the "repeats last year" rule, which only applies to year 1), preferring crops already grown
on the field; the two best of each kind are alternated. It starts from the last CDL crop (after a
nitrogen user, a legume first), reports the nitrogen fertiliser saved by the legume credits, and
offers alfalfa (3-4 years) as an alternative legume phase. Trees, vines and cane are never rotated.
If no legume passes, it suggests a winter legume cover crop.

Catalogue values that were wrong for a feasibility screen are corrected in `crop_params.json` with
the old value and the reason (shown on the crop card), e.g. corn GDD 1500 → 1200 (earliest hybrids),
sugarcane season = March-December growth (not planting-to-harvest), sugar beet and barley frost
tolerant.

**Reality check (`python -m scripts.validate_crops [--irrigated]`).** The screen runs on 10 US
reference sites (Corn Belt, San Joaquin Valley, Louisiana cane belt, Everglades, Texas High Plains,
Red River Valley, Arkansas Grand Prairie, Georgia Coastal Plain, Snake River Plain, Yakima) and is
compared with what USDA NASS shows is grown there and with crops excluded by climate. Before the
revision: 29 commercial crops marked "not recommended" and 11 non-viable crops passed. Now, with
irrigation where the region irrigates: 0 and 1. The remaining false pass (sorghum in the Snake River
Plain) comes from MERRA-2 nights ~5 °C warmer than NOAA normals in that arid basin; rainfed, the
irrigated regions' crops correctly fail on water. Climate is a ~50 km cell: valley frost, hollows
and local rain (e.g. Yakima's rain shadow) are smoothed.
Sowing window per crop: from the later of the catalogue window opening and the day after the
1-in-10-year last spring frost of the scenario, until the window closes (winter and perennial
crops use the catalogue window). Rule-based screening, not a prediction; the page says so.

## Farmer tools: safe sowing date and money check

- **When can I sow without frost risk?** (crop card): the date after which spring frost is over in
  9 years out of 10 (P90 of the last frost, Tmin ≤ 0 °C), Base → Scenario, compared with the crop's
  sowing window from the catalogue.
- **Money check** (`backend/economics.py`, `GET /api/economics/defaults`, `POST /api/economics/budget`):
  total cost for the parcel, expected income and result, cash check against the money the farmer
  can spend, break-even yield and price, and a what-if table for 10/20/30 % lower yields. Inputs
  are the farmer's, prefilled with sourced defaults (`backend/catalog/economics_us.json`):
  Iowa State University 2026 crop budgets (corn, soybeans), USDA ERS 2025 cost forecasts (other
  row crops) and USDA WASDE November 2026 season-average prices. Several cost defaults come from
  secondary summaries and are flagged for checking. Hypothetical irrigation in the scenario can be
  costed per mm and ha. No yield or price forecast: the climate checks only point the farmer to
  the lower-yield rows.

## Viewer and scenario simulator (module 5)

The page at `/` is a 2D viewer (Leaflet, one map instance) with the demo parcels, four
environmental layers, risk zones, a cursor inspector and a scenario simulator.

| Layer | Source | Type | Real resolution | How it is drawn |
|---|---|---|---|---|
| NDVI | Landsat 8/9 C2 L2 | satellite | 30 m | Parcel filled with its monthly parcel-mean NDVI (the analysis stores the mean; 30 m tiles are pending) |
| Root-zone moisture | SMAP L4 `sm_rootzone` | model | ~9-11 km | The SMAP grid cell containing the parcel, as one polygon (footprint from GEE) |
| Rainfall | NASA POWER `PRECTOTCORR` | reanalysis | 0.5° × 0.625° | The MERRA-2 cell as one polygon, monthly total |
| Slope | NASADEM | satellite | 1 arc-second | Native pixels inside the parcel (nearest, no smoothing) |
| Risk zones | Derived | derived + hypothetical | 1 arc-second | Erosion screening per pixel (only slope varies per pixel) and possible cold-air pooling (TPI ≤ -1 m, slope ≤ 2°) |

Months without data are disabled in the date selectors with their reason. The inspector says
"value of the ~N km zone" for zone layers, never "value at this point".

**Simulator (`POST /api/parcel/simulate`, contract `sim-1`).** Delta method on the parcel's real
NASA POWER daily series, re-run through the same `derived.py` functions:

- Rain −30 % to 0 %: every day × (1 + ΔP).
- Temperature 0 to +3 °C: ΔT added to T2M, T2M_MAX, T2M_MIN; **dew point held constant** (VPD rises).
  Variability is kept; it is not a validated projection.
- Irrigation (off by default, rainfed): a hypothetical share of each monthly deficit covered. The
  climatic deficit and the deficit left after irrigation are reported separately; no volume,
  efficiency or applied depth; it never changes heat, frost or erosion.
- With all controls at zero the result equals `analyze` (checked by a test and on the demo parcels).
- **Effect on the selected crop** (`crop_id`, default = the parcel's last CDL crop): four screening
  checks over the crop's own season from the team catalogue, Base → Scenario, each ok / tight /
  limit with a visible rule: enough heat to mature (growing degree-days vs requirement), enough
  water (season rain + hypothetical irrigation vs crop need, need scaled with ET0), too much heat
  (days ≥ 35 °C in season; days above the crop optimum shown as context only), long enough
  frost-free season. Screening only, not a yield forecast (`backend/crop_effects.py`).
- No scores, yields, probabilities or losses: no team rotation-scoring module exists yet.
- Always shown: "Escenario hipotético, no es una predicción / Hypothetical scenario, not a prediction".

Performance (i9-11900H, Windows, demo mode): server 190-200 ms per new scenario; HTTP round trip
over 20 random moves p50 95 ms, p95 115 ms; repeats are memoized. The page shows its own
input-to-paint p50/p95 under the sliders.

## Data sources

| Source | ID or endpoint | NASA? | Type | Resolution | Period | Coverage | Licence / terms | Use |
|---|---|---|---|---|---|---|---|---|
| Landsat 8 and 9 C2 L2 | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | Yes (with USGS) | satellite | 30 m | 2013 / 2021 to present | Global | Public domain | NDVI, NDTI, bare months, vulnerability |
| SMAP L4 | `NASA/SMAP/SPL4SMGP/008` | Yes | model (assimilates satellite) | ~9-11 km | 2015 to present | Global | NASA open data | Root-zone moisture, anomalies |
| NASA POWER | Daily API, AG community | Yes | reanalysis + satellite | 0.5° × 0.625° (met), 1° (solar) | 1981 to present | Global | Citation required | Frost, heat, ET0, water balance, extremes |
| NASADEM | `NASA/NASADEM_HGT/001` | Yes | satellite (radar) | 30 m | 2000 | 60° N to 56° S | NASA open data | Elevation, slope, erosion factor |
| Copernicus DEM GLO-30 | `COPERNICUS/DEM/GLO30_2024_1` | No (ESA) | satellite | 30 m | 2024 release | Global | Copernicus DEM licence | Fallback outside NASADEM |
| OpenLandMap | `OpenLandMap/SOL/...` (pH, texture, clay, sand, OC, 33 kPa) | No | model | 250 m | Static (1950-2018) | Global | **CC-BY-SA 4.0** (share-alike) | pH, texture, organic carbon, field capacity |
| USDA CDL | `USDA/NASS/CDL` | No | satellite (classification) | 30 m | 1997-2024 | Contiguous USA | Public domain | Historical crop types |
| GPM IMERG V07 | `NASA/GPM_L3/IMERG_V07` | Yes | satellite_gauge_merged | 0.1° | 1998 to present | Global | NASA open data | Planned cross-check (not in v1) |
| Google Earth Engine | Platform | No | Tool | | | | Earth Engine terms (noncommercial) | Computation |
| Iowa State University, Estimated Costs of Crop Production in Iowa 2026 (FM 1712) | extension.iastate.edu/agdm/crops/pdf/a1-20.pdf | No | Crop budgets | Iowa | 2026 | Iowa | Public extension publication; cite | Default costs and yields (corn, soybeans) |
| USDA ERS Commodity Costs and Returns | ers.usda.gov/data-products/commodity-costs-and-returns | No | Cost statistics | US average | 2025 forecast | US | Public domain | Default costs (other row crops) |
| USDA WASDE, November 2026 | usda.gov/oce/commodity/wasde/wasde1126.pdf | No | Price forecast | US | 2026/27 | US | Public domain | Default prices (corn, soybeans, wheat) |
| Team crop catalogue | `backend/catalog/crops_us.csv` | No | Knowledge base | | | USA crops | Team-compiled; per-attribute references still to be cited | Crop screening table on the page |
| Crop parameters and corrections | `backend/catalog/crop_params.json` | No | Knowledge base | | | USA crops | FAO-56, FAO-33, Hatfield et al. 2011, USDA zones (cited per value) | Kc, Ky, cardinal temperatures, winter/humidity rules |
| USDA SSURGO via Soil Data Access | `sdmdataaccess.sc.egov.usda.gov` (no key) | No | Soil survey | 1:12,000-1:24,000 | Current | USA | Public domain | Soil 0-30 cm when Earth Engine is off |
| USDA CDL via CropScape GetCDLValue | `nassgeodata.gmu.edu/axis2/services/CDLService` (no key) | No | Crop classification (point samples) | 30 m | 2008-2024 | Contiguous US | Public domain | Crop history when Earth Engine is off |
| Esri World Imagery | Basemap tiles | No | Imagery (display only) | | | Global | Esri terms, attribution shown on the map | Background satellite image on the page |
| Leaflet 1.9.4, Chart.js 4.4.1 | unpkg / jsdelivr CDN | No | Libraries | | | | BSD-2-Clause / MIT | Map and charts |
| USDA NASS Crop Sequence Boundaries 2017-2024 | ArcGIS FeatureServer `pdi.scinet.usda.gov/.../Crop_Sequence_Boundaries_2024` | No | Field polygons (from 30 m CDL) | ~30 m edges | 2017-2024 | Contiguous US | Public domain (USDA) | "Add a field": outline and pick real fields |
| OpenStreetMap (Overpass API, Nominatim) | `overpass-api.de`, `nominatim.openstreetmap.org` | No | Volunteered geography | | | Global | ODbL; attribution "© OpenStreetMap contributors"; Nominatim usage policy (≤ 1 req/s) | Field fallback outside CONUS, place search, county/state |
| USDA CDL via CropScape WMS | `nassgeodata.gmu.edu/CropScapeService` | No | Crop classification tiles | 30 m | Yearly | Contiguous US | Public domain | Optional crop-type overlay in the field picker |

**Citations**

- NASA POWER, project: "The data was obtained from the National Aeronautics and Space
  Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource
  (POWER) Project funded through the NASA Earth Science/Applied Science Program."
- NASA POWER, data: "The data was obtained from the POWER Project's Daily v2.10.3 version on
  2026/11/14." (The API returns the current version; the response's `provenance.citations.nasa_power_data`
  carries the exact version and date of each download.)
- Landsat: Landsat 8 and Landsat 9 Collection 2 Level-2 data courtesy of the U.S. Geological Survey.
- SMAP L4: Reichle, R. et al., SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil
  Moisture Geophysical Data, Version 8, NASA NSIDC DAAC. *(Copy the exact citation and DOI from
  the GEE catalog page before submission.)*
- NASADEM: NASA JPL (2020). NASADEM Merged DEM Global 1 arc second V001. NASA EOSDIS LP DAAC.
  doi:10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001
- OpenLandMap: Hengl, T. et al., OpenLandMap soil property maps at 250 m, Zenodo, CC-BY-SA 4.0.
  *(Copy the per-layer DOIs from the GEE catalog pages.)*
- USDA CDL: USDA National Agricultural Statistics Service Cropland Data Layer, USDA-NASS, Washington, DC.
- Earth Engine: Gorelick, N. et al. (2017). Google Earth Engine: Planetary-scale geospatial
  analysis for everyone. Remote Sensing of Environment 202, 18-27.
- USDA SSURGO: Soil Survey Staff, NRCS, USDA. Soil Survey Geographic (SSURGO) Database, via Soil Data Access.
- Crop screening: Allen et al. (1998) FAO-56; Doorenbos & Kassam (1979) FAO-33; Hatfield, J.L. et al.
  (2011) Agronomy Journal 103: 351-370; Porter & Gawith (1999) Eur. J. Agron. 10: 23-36; USDA Plant
  Hardiness Zone Map (2023). Full list per value in `backend/catalog/crop_params.json`.
- Methods: Allen, R. G. et al. (1998). FAO Irrigation and Drainage Paper 56; ETCCDI climate
  extremes indices; NDTI after Van Deventer et al. (1997).

## Use of AI tools

As the Space Apps rules require, we disclose that AI coding tools were used to write the code of
this data layer.

- **What:** every module in `backend/` (including the simulator `simulate.py`, the terrain grid
  and the web page in `backend/static/`), `scripts/` and `tests/` was generated or substantially
  written with an AI coding assistant (Claude, by Anthropic). Simulator responses carry
  `provenance.ai_assistance` too. The explanation sentences are deterministic templates filled
  with computed numbers, not LLM output. The FAO-56 Penman-Monteith
  implementation was ported from the team's earlier climate module. Each Python file has a header
  line that says so; the web page files (`backend/static/`) carry no such note so the interface
  stays clean, and this section is the disclosure for them.
- **What it did not do:** the AI did not come up with the solution concept. Indicator values come
  from the cited datasets, not from a model. The choice of challenge, scope and approach, plus the
  dataset research, are in `docs/`.
- **Review:** the team reviewed the code. The formulas are checked by unit tests against FAO-56
  worked examples and hand calculations, and a smoke run against the real APIs is printed.
  Dataset IDs, bands and scale factors were checked on the GEE catalog pages on 2026-11-14.
- **Metadata:** every API response includes `provenance.ai_assistance`.

## Status (2026-11-14)

- Working and verified with real data: NASA POWER client and all climate indicators, geometry
  validation, cache, endpoint, contract, formula tests.
- Written but **not yet run** (needs `EE_PROJECT_ID`): Landsat NDVI/NDTI, SMAP, terrain,
  OpenLandMap, CDL, and the derived bare months / vulnerability / erosion index that depend on them.
- Not included: IMERG cross-check, NDVI/slope map tiles, Sentinel-2 (optional per the brief).
