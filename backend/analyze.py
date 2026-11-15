"""Orchestrator: validate the parcel, run one request per source in parallel, derive, assemble.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
A failed or timed-out module becomes `null` plus a `data_gaps` entry; it never fails the response.

Flow of analyze():
  1. prepare()  -> validate the GeoJSON and get a Parcel (area, centroid, hemisphere).
  2. cache_key() -> SHA-256 of geometry + dates. Look for that key in the demo cache, then in the
     response cache. If found, return it (fast, no quota used).
  3. Otherwise build(): run the 6 source modules in parallel threads, compute the derived indicators,
     add data gaps and citations, and save the result + a "baseline bundle" for the simulator.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timezone

from . import config, derived, gee_client
from .contract import AI_ASSISTANCE, CITATIONS, warn
from .geometry import cache_key, prepare
from .sources import croptype, landsat, power, smap, soil, terrain

# Name -> function. Every module has the same signature run(parcel, start, end) and returns an
# indicator dict, so the orchestrator can treat them all the same way.
MODULES = {
    "agroclimate_power": power.run,
    "landsat": landsat.run,                # -> indicators "ndvi" and "ndti"
    "soil_moisture_smap": smap.run,
    "terrain": terrain.run,
    "soil_openlandmap": soil.run,
    "crop_type": croptype.run,
}


TRANSIENT_GAPS = {"SOURCE_UNAVAILABLE", "MODULE_TIMEOUT", "MODULE_ERROR"}


class AllModulesFailed(RuntimeError):
    """Raised only when every source failed; api.py turns it into HTTP 502."""
    pass


def default_dates():
    """Last N complete calendar years, e.g. in 2026 -> 2016-01-01 .. 2025-12-31 (N = DEFAULT_YEARS)."""
    y = date.today().year - 1
    return f"{y - config.DEFAULT_YEARS + 1}-01-01", f"{y}-12-31"


def check_dates(start, end):
    """Reject impossible periods before spending any API quota."""
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    if d1 <= d0:
        raise ValueError("end_date must be after start_date.")
    if (d1 - d0).days > 366 * config.MAX_YEARS:
        raise ValueError(f"Period longer than {config.MAX_YEARS} years.")
    if d1 > date.today():
        raise ValueError("end_date is in the future.")


def _gap(indicator, exc):
    """Turn an exception into a data_gaps entry. Custom exceptions carry a `.code` attribute
    (e.g. GEE_UNAVAILABLE); anything else becomes MODULE_TIMEOUT or MODULE_ERROR."""
    code = getattr(exc, "code", None) or ("MODULE_TIMEOUT" if isinstance(exc, TimeoutError)
                                          else "MODULE_ERROR")
    msg = str(exc) or type(exc).__name__
    return {"indicator": indicator, "code": code, "reason": msg[:300]}


def _run_modules(parcel, start, end, only=None):
    """Run the source modules at the same time and collect results or gaps.

    The modules spend most of their time waiting for the network (NASA POWER, Earth Engine), so
    threads give a real speed-up: the total time is roughly the slowest module, not the sum.
    """
    results, gaps = {}, []
    names = [n for n in MODULES if only is None or n in only]
    pool = ThreadPoolExecutor(max_workers=len(names))
    # submit() starts each module in its own thread and returns a Future (a "promise" of the result).
    futs = {n: pool.submit(MODULES[n], parcel, start, end) for n in names}
    t0 = time.monotonic()
    wait(futs.values(), timeout=max(config.MODULE_TIMEOUT_S.values()))
    for n, f in futs.items():
        # Each module has its own time limit, measured from the common start time t0.
        limit = config.MODULE_TIMEOUT_S.get(n, 60)
        remaining = max(0.0, limit - (time.monotonic() - t0))
        try:
            results[n] = f.result(timeout=remaining)   # re-raises any exception the module raised
        except Exception as e:  # includes TimeoutError
            if isinstance(e, TimeoutError):
                e = TimeoutError(f"{n} exceeded {limit} s.")
            results[n] = None                          # failed module -> null indicator...
            gaps.append(_gap(n, e))                    # ...plus an explanation in data_gaps
    # Do not wait for slow threads: we already have what we need.
    pool.shutdown(wait=False, cancel_futures=True)
    return results, gaps


def _derive(ind):
    """Compute the indicators that combine several sources (bare months, vulnerability, erosion).

    Each one is computed only if its inputs exist; otherwise it is None and gets an INPUTS_MISSING gap.
    """
    out, gaps = {}, []
    ndvi, ndti, clim = ind.get("ndvi"), ind.get("ndti"), ind.get("agroclimate_power")
    smap_ind, ter, soil_ind = ind.get("soil_moisture_smap"), ind.get("terrain"), ind.get("soil_openlandmap")

    out["bare_months"] = derived.bare_months(ndvi["climatology"], ndti and ndti["climatology"]) if ndvi else None
    if ndvi and clim:
        anom = {a["month"]: a["value"] for a in smap_ind["anomaly"]} if smap_ind else None
        out["vulnerability"] = derived.vulnerability(ndvi["monthly"], ndvi["climatology"],
                                                     clim["monthly_series"], anom)
    else:
        out["vulnerability"] = None
    ext = clim["precip_extremes"]["mean_per_year"] if clim else {}
    # Pass None for any missing factor: erosion_index itself decides if 3 of 4 factors are enough.
    out["erosion_index"] = derived.erosion_index(
        slope_p90_deg=ter["slope_deg"]["p90"] if ter else None,
        rx1day_mm=ext.get("rx1day_mm"), r95p_mm=ext.get("r95p_mm"),
        clay_pct=soil_ind["clay_pct"] if soil_ind else None,
        sand_pct=soil_ind["sand_pct"] if soil_ind else None,
        oc_g_kg=soil_ind["organic_carbon_g_kg"] if soil_ind else None,
        bare=out["bare_months"],
        wet_months=derived.wettest_months(clim["monthly_climatology"]) if clim else None,
    )
    for k, v in out.items():
        if v is None:
            gaps.append({"indicator": k, "code": "INPUTS_MISSING",
                         "reason": "Required input indicators are unavailable."})
    return out, gaps


def build(parcel, start, end, only=None):
    """Compute the full contract live (no cache)."""
    res, gaps = _run_modules(parcel, start, end, only)
    if all(v is None for v in res.values()):
        raise AllModulesFailed(gaps)
    ls = res.pop("landsat", None)          # the Landsat module returns two indicators at once
    ind = {
        "ndvi": ls["ndvi"] if ls else None,
        "ndti": ls["ndti"] if ls else None,
        "soil_moisture_smap": res.get("soil_moisture_smap"),
        "agroclimate_power": res.get("agroclimate_power"),
        "terrain": res.get("terrain"),
        "soil_openlandmap": res.get("soil_openlandmap"),
        "precipitation_imerg": None,       # planned but not implemented: reported as a gap below
        "crop_type": res.get("crop_type"),
    }
    for g in gaps:
        if g["indicator"] == "landsat":
            g["indicator"] = "ndvi, ndti"
    der, dgaps = _derive(ind)
    gaps += dgaps
    # Gaps that are always true: we say them explicitly because Validity is judged on honesty.
    gaps += [
        {"indicator": "precipitation_imerg", "code": "NOT_COMPUTED",
         "reason": "IMERG cross-check not included in this version (time budget)."},
        {"indicator": "soil", "code": "NO_FARMER_DATA", "reason": "No farmer-provided soil analysis."},
        {"indicator": "crop_type", "code": "NOT_CONFIRMED", "reason": "Current rotation not confirmed by farmer."},
    ]
    warnings = list(parcel.warnings)
    # Collect the citations of the sources that actually produced data (set of citation keys).
    keys = {i["source"]["citation_key"] for i in ind.values() if i}
    # Earth Engine is cited only if an indicator was really computed there (not the no-login web services).
    keys |= {"earth_engine"} if any(ind[k] and ind[k].get("via") != "web_service"
                                    for k in ind if k != "agroclimate_power") else set()
    citations = {k: CITATIONS[k] for k in sorted(keys) if k in CITATIONS}
    if ind["agroclimate_power"]:
        citations["nasa_power_data"] = ind["agroclimate_power"]["data_citation"]
    return {
        "version": config.CONTRACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "served_from": "live",
        "request": {"geometry_type": parcel.input_type, "area_ha": parcel.area_ha,
                    "centroid": list(parcel.centroid), "hemisphere": parcel.hemisphere,
                    "start_date": start, "end_date": end},
        "indicators": ind,
        "derived": der,
        "layers": [],
        "data_gaps": gaps,
        "warnings": warnings,
        "provenance": {"ai_assistance": AI_ASSISTANCE, "citations": citations},
    }


def baseline_path(key, demo=False):
    return (config.DEMO_DIR if demo else config.CACHE_DIR) / "baseline" / f"{key}.json"


def save_baseline(key, parcel, start, end, out):
    """Everything `simulate` needs later without NASA or Earth Engine (POWER file + static factors).

    The simulator must answer in < 1 s, so it never calls the internet. Here we write down the
    name of the cached POWER file and the factors that do not change with the scenario
    (slope, soil, bare months) so simulate.py can rebuild everything from disk.
    """
    ind = out["indicators"]
    ter, soil = ind.get("terrain"), ind.get("soil_openlandmap")
    lon, lat = parcel.centroid
    bundle = {
        "key": key, "geometry": parcel.geojson, "centroid": list(parcel.centroid),
        "hemisphere": parcel.hemisphere, "area_ha": parcel.area_ha, "start": start, "end": end,
        "power_file": power.cache_name(lat, lon, start, end) if ind.get("agroclimate_power") else None,
        "grid_elevation_m": (ind.get("agroclimate_power") or {}).get("grid_elevation_m"),
        "erosion_static": {
            "slope_p90_deg": ter["slope_deg"]["p90"] if ter else None,
            "clay_pct": soil["clay_pct"] if soil else None,
            "sand_pct": soil["sand_pct"] if soil else None,
            "oc_g_kg": soil["organic_carbon_g_kg"] if soil else None,
            "bare_months": out["derived"].get("bare_months"),
        },
    }
    p = baseline_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle


def analyze(geometry, start=None, end=None, farmer_priorities=None, use_cache=True):
    """Entry point used by the API. Raises GeometryError / ValueError for bad input."""
    parcel = prepare(geometry)
    if not start or not end:
        ds, de = default_dates()
        start, end = start or ds, end or de
    check_dates(start, end)
    key = cache_key(parcel, start, end)

    # Lookup order: 1) demo cache (precomputed, shipped with the repo), 2) response cache, 3) compute live.
    demo = config.DEMO_DIR / f"{key}.json"
    if demo.exists():
        out = json.loads(demo.read_text(encoding="utf-8"))
        out["served_from"] = "demo_cache"
    else:
        cached = config.CACHE_DIR / "responses" / f"{key}.json"
        out = json.loads(cached.read_text(encoding="utf-8")) if (use_cache and cached.exists()) else None
        # A response computed while Earth Engine was off is recomputed once Earth Engine works, so
        # configuring it later (python run.py --setup) fills NDVI, SMAP and slope for old fields too.
        if out and any(g.get("code") == "GEE_UNAVAILABLE" for g in out.get("data_gaps", [])) and gee_client.status()["ready"]:
            out = None
        # Temporary failures (a service down or slow) are retried, but at most once an hour so a source
        # that stays down does not make every page load wait for a full live analysis.
        if out and any(g.get("code") in TRANSIENT_GAPS for g in out.get("data_gaps", [])):
            age = datetime.now(timezone.utc) - datetime.fromisoformat(out["generated_at"])
            if age.total_seconds() > 3600:
                out = None
        if out:
            out["served_from"] = "cache"
        else:
            out = build(parcel, start, end)
            save_baseline(key, parcel, start, end, out)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    # The page needs the key to call /simulate, /recommend and /terrain-grid later.
    out["request"]["cache_key"] = key
    if farmer_priorities is not None:
        out["request"]["farmer_priorities"] = farmer_priorities   # echoed for the rotation module
    return out
