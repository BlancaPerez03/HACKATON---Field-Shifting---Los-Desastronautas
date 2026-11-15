# Field Shift: data layer for the rotation tool (Space Apps 2026)

Model: Opus 5.5 at medium. Reason: building against three external APIs with scientific-honesty calls (scale, data
type, thresholds) under a hard deadline. Sub-agents: Haiku 5.5 to map the repository, Sonnet 5.5 for the POWER client
and the pure formulas. Raise to high only if a module fails twice.

## The owner's brief

> "no hagas casi tests, solo al final"

The challenge, quoted from its page:

> Create a decision-support tool that uses NASA Earth observations along with local soil information, crop
> characteristics, and farmer priorities to help farmers explore rotation strategies [...]. You may compare at least
> three rotation strategies, including the existing rotation. For each strategy, you may explain why it was
> suggested, what evidence supports it, what benefits it may offer, where information gaps exist, and any risks that
> would need local review.

This job covers only the data layer. Given a point or a polygon, it returns traceable satellite, climate and soil
indicators for the rotation-comparison module to use. Do not build the crop recommendation logic.

## State on 2026-11-14 (verified; details and sources in the dossier)

- The hackathon runs Saturday 14 to Sunday 15 November 2026. **Submission closes Sunday 23:59 local time.** Leave
  Sunday afternoon free for the 30-second video or the slides.
- Global awards need at least one NASA dataset. The Relevance criterion wants NASA data as the core. Rules require
  disclosing AI use for code and data "in descriptive text and metadata", and listing every non-NASA source with its
  licence.
- Corrections to the team's earlier prompt, verified today:
  - NASA POWER has no ET0, so compute it.
  - `GWETROOT` is a 0 to 1 wetness index, not volumetric moisture.
  - A POWER point returns the native resolution: 0.5° × 0.625° for meteorology, 1° for solar.
  - IMERG V07 has no daily collection in GEE, and data after 2025-09-30 is provisional.
  - The SMAP ID is `NASA/SMAP/SPL4SMGP/008`.
  - `COPERNICUS/DEM/GLO30` is deprecated.
  - `earthengine-api` 1.7.52 needs Python 3.11 or later.
  - The noncommercial Community tier is capped at 150 EECU-hours a month.
  - Map IDs last "a few hours".
- This machine has no project repository. Checked with `find ~ ~/Desktop -maxdepth 4 -iname "*space*app*" -o -iname
  "*field*shift*"`, which found nothing. Work in the repository where this session starts.

## Read first

1. `/Users/alejandrolalaguna/Desktop/field-shift/DOSSIER-field-shift.md`, in this order:
   - §0 (summary)
   - §3.2 (the corrected IDs and units)
   - §3.4 (scope cut)
   - §5 (architecture and JSON contract)
   - §6 (derived indicators spec)
   - §8 (sources table)
   The rest is reference. If the file is not at that path, ask for it before writing code.
2. The repository's own README, its dependency files and any `CLAUDE.md` or `AGENTS.md`. Fit into what exists:
   framework, layout, style.

## Ask once at the start, then proceed

Ask these four questions together. Each lists its options with the recommended one first. If there is no answer,
take the recommended option and say so.

1. **Parcel region:**
   - (a) global sources only for now;
   - (b) Spain or EU, adding `JRC/D5/EUCROPMAP/V1`;
   - (c) USA, adding `USDA/NASS/CDL` to the core.
2. **`EE_PROJECT_ID`, and whether its noncommercial registration is verified.** If not, start with POWER, which
   needs no GEE.
3. **Endpoint name:**
   - (a) `POST /api/parcel/analyze`;
   - (b) the existing one, if the repository has one.
4. **Two or three real demo parcels as GeoJSON.** If there are none, pick one public agricultural parcel in the
   region and say which one.

## Goal, in priority order

Stop after each block and print a short status for the team. Do not wait for approval unless something blocks.

1. **POWER and climate indicators (no GEE):**
   - `power.py`: AG community, daily, point at the centroid, up to 20 parameters per request, cache per 0.5° cell,
     retries on 429. Read the units from the response.
   - From POWER, compute: frost dates (P10, P50 and P90 per year, by hemisphere), days at or below 0 °C and at or
     below 2 °C, heat days above a configurable threshold, ET0 (Hargreaves; also FAO-56 Penman-Monteith if the
     inputs are present), monthly P − ET0, and R95p on wet days plus R20mm and Rx1day.
2. **GEE modules:**
   - `landsat.py`: monthly median NDVI and NDTI from Landsat 8 and 9 C2 L2, with QA_PIXEL bits 0 to 5 and QA_RADSAT
     masked, reflectance kept within [0, 1], and the valid observation count and valid pixel percentage per month.
   - `smap.py`: monthly `sm_rootzone`, its climatology and its anomaly.
   - `terrain.py`: NASADEM elevation and slope in degrees, computed on a buffered DEM before reducing; outside
     60° N to 56° S, use `COPERNICUS/DEM/GLO30_2024_1`.
   - `soil.py`: OpenLandMap pH, texture, organic carbon and water at 33 kPa, averaged over 0 to 30 cm.
   - Run one request per module, in parallel, each with its own timeout. A failed module becomes `null` plus a
     `data_gaps` entry, not a failed response.
3. **`derived.py` (pure functions, no network):**
   - bare months: NDVI below the threshold, split into "bare" or "residue" by NDTI;
   - vulnerability: NDVI z-score at or below −1 at the same time as heat or a water deficit, labelled as
     co-occurrence;
   - relative erosion index from slope, extremes, soil and bare-in-wet-months, shown as low, medium or high with each
     factor.
4. **The endpoint and the JSON contract** of dossier §5.3:
   - every indicator carries its source IDs, `nasa: true` or `false`, `data_type`, `resolution_m`, `scale_note`,
     method, thresholds, `confidence` with its reason, and warnings with stable codes;
   - geometry validation (invalid, self-intersecting, too many vertices, more than 1,000 ha);
   - a point becomes a 50 m buffer, with a warning;
   - a cache keyed by a hash of the geometry and dates.
5. **Precomputed demo parcels** saved as JSON and served when the geometry matches, with `served_from:
   "demo_cache"`. This keeps the demo working through quota limits and expired map IDs.
6. **Only if time remains:** NDVI and slope tiles (`getMapId`, `expires_at_estimate`, and a legend); IMERG monthly
   totals as a satellite cross-check (time one year first); Sentinel-2 with Cloud Score+ (`cs_cdf >= 0.60`). Leave
   out MODIS NDVI, ERA5-Land, ECOSTRESS, GRACE, GEDI and a tile proxy.

## Constraints and why

- **Verify each dataset ID, band and scale on its catalog page before using it.** Some IDs have moved, and a wrong
  scale silently ruins every indicator. The dossier tables are the starting point, not the proof.
- Prefer NASA sources when two sources overlap. Relevance is judged on NASA data being core. Non-NASA sources may
  serve as a cross-check.
- Never present NDVI as fertility or yield, `GWETROOT` as volumetric moisture, or the erosion index as soil loss.
  Judges score Validity, and an honest note about scale counts in our favour.
- Keep credentials out of the frontend, the repository and the logs. Provide a `.env.example` and add key paths to
  `.gitignore`. The frontend calls only our endpoint.
- **Tests: almost none while building (owner's decision).** At the end only:
  - one smoke run against the real APIs on the demo parcels, with the trimmed real output printed;
  - unit tests of the pure formulas: ET0, frost dates, the QA bit mask, R95p and the erosion index.
- Disclose AI use. Every AI-generated or AI-assisted module gets a header line saying so. The README gets a "Use of
  AI tools" section. The response carries `provenance.ai_assistance`.

## Parallelism

- **Haiku 5.5 sub-agent:** map the repository.
  - Goal: report the framework, the entry point, the dependency file, the Python version, the existing routes and
    the test layout.
  - Rules: read only; touch no files.
  - Answer: a list of at most 30 lines.
- **Sonnet 5.5 sub-agent:** write `power.py` and the climate functions of `derived.py` while the main session does
  GEE authentication and `landsat.py`.
  - Brief: dossier §6.3 to §6.6 and §7.2.
  - It owns only those two files and touches nothing else.
  - It returns the functions' signatures and one real POWER call's trimmed output.
  - Check: the main session reruns that call.
- Everything else stays in the main session. Run at most three agents at once.

## Done when

- `POST` with each demo parcel returns the §5.3 contract with POWER, Landsat, SMAP, terrain, soil and derived
  indicators populated, or each missing one listed in `data_gaps` with its reason.
- The final smoke run and the formula tests pass, with their output printed.
- The README has:
  - local setup;
  - environment variables;
  - the switch to a service account (`roles/earthengine.writer` and `roles/serviceusage.serviceUsageConsumer`);
  - Python 3.11 or later;
  - the sources table of dossier §8 with licences and citations, including the POWER reference sentences;
  - the "Use of AI tools" section.
- A closing report: what works (with the real output), what is pending, the decisions taken, and anything still
  unverified.

Commit only when the team asks. Do it on a feature branch, never on the default branch.
