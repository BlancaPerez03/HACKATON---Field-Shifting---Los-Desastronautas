"""HTTP API of Field Shift: every URL the web page calls lives in this file.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Run: uvicorn backend.api:app --reload --port 8000
The frontend calls only these endpoints; no credentials ever reach the browser.

How FastAPI works here (short version):
- `app = FastAPI()` creates the web application.
- A decorator such as `@app.post("/api/parcel/analyze")` links a URL + HTTP method to a Python function.
- The request body is described with a pydantic `BaseModel`; FastAPI validates the JSON against it
  and returns a 422 error automatically if a field has the wrong type.
- Whatever the function returns (a dict) is sent back to the browser as JSON.
- `HTTPException(status, detail)` stops the function and sends an error response instead.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .analyze import AllModulesFailed, analyze
from .crops import load_catalog
from .economics import budget as econ_budget
from .economics import defaults as econ_defaults
from .gee_client import GeeUnavailable
from .gee_client import status as gee_status
from .geometry import GeometryError, prepare
from .simulate import (BaselineNotCached, UnknownCrop, clear_simulation_cache, load_bundle, load_terrain_grid,
                       recommend, save_terrain_grid, simulate)
from .sources import terrain_grid

app = FastAPI(title="Field Shift data layer", version="1")

# CORS: browsers block calls from a page on another origin (e.g. a React dev server on :5173)
# unless the server allows it. We only allow the origins listed in FS_CORS_ORIGINS.
origins = [o.strip() for o in os.environ.get("FS_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["*"])


@app.middleware("http")
async def no_stale_page(request, call_next):
    """Make the browser revalidate index.html / app.js / styles.css on every load.

    Without this, a browser can keep an old app.js from its cache after the code changes, and the
    page then talks to the new API with old code (sliders that 'do nothing').
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class AnalyzeRequest(BaseModel):
    """Body of POST /api/parcel/analyze. Only `geometry` is required."""
    geometry: dict[str, Any]                         # GeoJSON Point, Polygon, MultiPolygon, Feature or FeatureCollection
    start_date: Optional[str] = None                 # "YYYY-MM-DD"; default = last 10 complete years
    end_date: Optional[str] = None
    farmer_priorities: Optional[dict[str, Any]] = None   # not used here, just echoed back for the rotation module


@app.on_event("startup")
def warm_demo_baselines():
    """Load the demo parcels' POWER series once, so the first slider move is fast.

    _baseline() is memoized (lru_cache), so calling it here fills the cache before the first user arrives.
    Errors are ignored on purpose: a missing demo file must not stop the server from starting.
    """
    idx = config.DEMO_DIR / "index.json"
    if not idx.exists():
        return
    from .simulate import _baseline
    for d in json.loads(idx.read_text()):
        try:
            _baseline(d["cache_key"])
        except Exception:
            pass


@app.get("/api/health")
def health():
    """Tiny endpoint to check the server is alive."""
    return {"ok": True}


@app.get("/api/status")
def status():
    """Which data sources are available (the page shows a setup hint when Earth Engine is off)."""
    ee = gee_status()
    return {"earth_engine": ee,
            "no_login_sources": ["NASA POWER (climate)", "USDA SSURGO via Soil Data Access (soil, US)",
                                 "USDA CDL via CropScape (crop history, contiguous US)"],
            "needs_earth_engine": [] if ee["ready"] else ["NDVI / NDTI (Landsat)", "SMAP root-zone moisture",
                                                          "Slope and risk zones (NASADEM)"]}


@app.post("/api/parcel/analyze")
def parcel_analyze(req: AnalyzeRequest):
    """Analyze a parcel with all data sources (or serve it from the demo cache / response cache)."""
    try:
        return analyze(req.geometry, req.start_date, req.end_date, req.farmer_priorities)
    except GeometryError as e:          # invalid / too big / too many vertices -> the user's fault
        raise HTTPException(422, {"code": e.code, "message": e.message})
    except ValueError as e:             # bad dates
        raise HTTPException(422, {"code": "BAD_REQUEST", "message": str(e)})
    except AllModulesFailed as e:       # every single source failed -> upstream problem (502 Bad Gateway)
        raise HTTPException(502, {"code": "ALL_SOURCES_FAILED", "data_gaps": e.args[0]})


class SimulateRequest(BaseModel):
    """Body of /simulate and /recommend: which parcel (by its cache key) and the three slider values."""
    geometry_hash: str
    start_date: Optional[str] = None      # informative: the hash already encodes the dates
    end_date: Optional[str] = None
    delta_precip_pct: float = 0           # -30 .. 0
    delta_temp_c: float = 0               # 0 .. 3
    irrigation_enabled: bool = False
    irrigation_availability_pct: float = 0
    crop_id: Optional[str] = None         # e.g. "corn_maize"; only used by /simulate


@app.post("/api/parcel/simulate")
def parcel_simulate(req: SimulateRequest, response: Response):
    """Recalculate the indicators for a hypothetical scenario (no NASA / Earth Engine calls, cache only)."""
    try:
        out = simulate(req.geometry_hash, req.delta_precip_pct, req.delta_temp_c,
                       req.irrigation_enabled, req.irrigation_availability_pct, req.crop_id)
    except BaselineNotCached as e:      # 409 Conflict: the page must call /analyze first, then retry
        raise HTTPException(409, {"code": "BASELINE_NOT_CACHED", "message": str(e)})
    except UnknownCrop as e:
        raise HTTPException(422, {"code": "UNKNOWN_CROP", "message": str(e)})
    # Server-Timing header: the browser dev tools show how long the server took.
    response.headers["Server-Timing"] = f"simulate;dur={out['timing_ms']['server']}"
    return out


@app.post("/api/parcel/recommend")
def parcel_recommend(req: SimulateRequest, response: Response):
    """Which crops suit this field under the scenario, and when to sow them (rule-based, transparent)."""
    try:
        out = recommend(req.geometry_hash, req.delta_precip_pct, req.delta_temp_c,
                        req.irrigation_enabled, req.irrigation_availability_pct)
    except BaselineNotCached as e:
        raise HTTPException(409, {"code": "BASELINE_NOT_CACHED", "message": str(e)})
    response.headers["Server-Timing"] = f"recommend;dur={out['timing_ms']['server']}"
    return out


@app.get("/api/parcel/terrain-grid")
def parcel_terrain_grid(hash: str):
    """30 m slope/TPI grid for the risk zones. Cached on disk; computed with Earth Engine only the first time."""
    grid = load_terrain_grid(hash)                  # 1) already on disk (demo cache or cache)?
    if grid is not None:
        return grid
    try:
        bundle = load_bundle(hash)                  # 2) we need the parcel geometry saved by /analyze
    except BaselineNotCached as e:
        raise HTTPException(409, {"code": "BASELINE_NOT_CACHED", "message": str(e)})
    try:
        grid = terrain_grid.fetch(prepare(bundle["geometry"]))   # 3) ask Earth Engine
    except GeeUnavailable as e:                     # no EE_PROJECT_ID / not authenticated
        raise HTTPException(503, {"code": "GEE_UNAVAILABLE", "message": str(e)})
    except Exception as e:
        raise HTTPException(502, {"code": "TERRAIN_GRID_FAILED", "message": str(e)[:300]})
    save_terrain_grid(hash, grid)
    clear_simulation_cache()                        # old simulations had no grid -> forget them so zones appear
    return grid


@app.get("/api/economics/defaults")
def economics_defaults(crop_id: str):
    """Sourced default yield, price and cost for one crop (the farmer can overwrite them on the page)."""
    try:
        return econ_defaults(crop_id)
    except KeyError:
        raise HTTPException(422, {"code": "UNKNOWN_CROP", "message": f"Unknown crop id {crop_id!r}."})


class BudgetRequest(BaseModel):
    """Body of /api/economics/budget. Everything is per hectare, in USD and tonnes."""
    area_ha: float
    yield_t_ha: Optional[float] = None
    price_usd_t: Optional[float] = None
    cost_usd_ha: Optional[float] = None
    available_usd: Optional[float] = None
    irrigation_mm: Optional[float] = 0          # empty boxes arrive as null and count as 0
    irrigation_cost_usd_mm_ha: Optional[float] = 0
    bushel_kg: Optional[float] = None           # lets the result also be shown in bushels


@app.post("/api/economics/budget")
def economics_budget(req: BudgetRequest):
    """Budget arithmetic for the whole parcel (total cost, income, break-even, what-if table)."""
    if req.area_ha <= 0 or req.area_ha > config.MAX_AREA_HA:
        raise HTTPException(422, {"code": "BAD_AREA", "message": "Area must be between 0 and 1000 ha."})
    # model_dump() turns the pydantic object into a dict; ** passes it as keyword arguments.
    return econ_budget(**req.model_dump())


@app.get("/api/demo/parcels")
def demo_parcels():
    """The precomputed demo parcels with their geometry (the page posts each geometry back)."""
    parcels = json.loads((config.ROOT / "scripts" / "demo_parcels.json").read_text(encoding="utf-8"))["parcels"]
    idx_file = config.DEMO_DIR / "index.json"
    # A set comprehension: the ids that build_demo.py already precomputed.
    ready = {d["id"] for d in json.loads(idx_file.read_text())} if idx_file.exists() else set()
    return [{"id": p["id"], "name": p["name"], "geometry": p["geometry"], "precomputed": p["id"] in ready}
            for p in parcels]


@app.get("/api/crops")
def crops():
    """The team crop catalogue, parsed from the CSV."""
    return load_catalog()


# The web page (must be mounted last so /api routes win).
# StaticFiles serves index.html, app.js, styles.css... from backend/static at the root URL "/".
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
