"""Scenario simulator: delta method on the parcel's real NASA POWER daily series (contract sim-1).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Pure: no network, no Earth Engine. It reads the baseline bundle and the cached POWER file written
by `analyze`, perturbs the daily series uniformly, and re-runs the same functions of derived.py.
With the three controls at zero the baseline block equals `analyze`'s agroclimate indicator.

Deltas:
  rain        P'(day) = P(day) * (1 + dP/100), dP in [-30, 0]
  temperature T2M, T2M_MAX, T2M_MIN += dT, dT in [0, 3]; dew point held constant (so VPD rises)
  irrigation  hypothetical availability a in [0, 100] % of each monthly deficit (P' - ET0' < 0);
              remaining deficit = deficit * (1 - a). No volumes, no efficiency, no effect on heat,
              frost or erosion.
"""
import json
import time
from functools import lru_cache

import numpy as np
import pandas as pd

from . import config, derived
from . import recommend as rec
from .contract import AI_ASSISTANCE, r
from .crop_effects import crop_effect
from .crops import load_catalog
from .sources.power import parse

RULES_VERSION = "sim-1"
# (min, max, step) of each slider. clamp() forces any incoming value into this range and rounds
# it to the step, so the server never computes impossible scenarios and the memo cache gets hits.
LIMITS = {"delta_precip_pct": (-30, 0, 1), "delta_temp_c": (0, 3, 0.1),
          "irrigation_availability_pct": (0, 100, 5)}
COLD_AIR = {"tpi_max_m": -1.0, "slope_max_deg": 2.0, "frost_days_full": 30}


class BaselineNotCached(LookupError):
    code = "BASELINE_NOT_CACHED"


class UnknownCrop(ValueError):
    code = "UNKNOWN_CROP"


def _find(sub, name):
    # Look first in the demo cache (shipped with the project) and then in the normal disk cache.
    for base in (config.DEMO_DIR, config.CACHE_DIR):
        p = base / sub / name
        if p.exists():
            return p
    return None


def load_bundle(key):
    p = _find("baseline", f"{key}.json")
    if p is None:
        raise BaselineNotCached(f"No baseline for {key[:12]}; call /api/parcel/analyze first.")
    return json.loads(p.read_text(encoding="utf-8"))


def load_terrain_grid(key):
    p = _find("terrain", f"{key}.json")
    return json.loads(p.read_text(encoding="utf-8")) if p else None


def save_terrain_grid(key, grid):
    p = config.CACHE_DIR / "terrain" / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(grid), encoding="utf-8")


# @lru_cache remembers the result of a function for each set of arguments ("memoization").
# The first call for a parcel reads the POWER file and computes the baseline (~300 ms); later
# calls with the same key return instantly from memory.
@lru_cache(maxsize=16)
def _baseline(key):
    bundle = load_bundle(key)
    if not bundle.get("power_file"):
        raise BaselineNotCached("The baseline has no NASA POWER series.")
    pf = _find("power", bundle["power_file"])
    if pf is None:
        raise BaselineNotCached("POWER daily series not in cache.")
    df, _, _ = parse(json.loads(pf.read_text()))
    lat = bundle["centroid"][1]
    elev = bundle.get("grid_elevation_m") or 0.0
    summary = derived.climate_summary(df, lat, elev, bundle["hemisphere"])
    return bundle, df, summary, load_terrain_grid(key)


@lru_cache(maxsize=16)
def _base_et0(key):
    bundle, df, _, _ = _baseline(key)
    return derived.et0_daily(df, bundle["centroid"][1], bundle.get("grid_elevation_m") or 0.0)[0]


@lru_cache(maxsize=64)
def _scenario_summary(key, dp, dt):
    """Climate summary of the perturbed series (memoized: /simulate and /recommend share it)."""
    bundle, df, _, _ = _baseline(key)
    return derived.climate_summary(perturb(df, dp, dt), bundle["centroid"][1], bundle.get("grid_elevation_m") or 0.0,
                                   bundle["hemisphere"])


def clamp(name, v):
    lo, hi, step = LIMITS[name]
    v = min(max(float(v), lo), hi)
    return round(round(v / step) * step, 3)


def perturb(df, d_precip_pct, d_temp_c):
    """Uniform delta on the daily series. Series that cannot be shifted honestly are dropped."""
    out = df.drop(columns=[c for c in ("FROST_DAYS", "GWETROOT") if c in df.columns])
    out["PRECTOTCORR"] = out["PRECTOTCORR"] * (1 + d_precip_pct / 100)
    for c in ("T2M", "T2M_MAX", "T2M_MIN"):
        if c in out:
            out[c] = out[c] + d_temp_c
    return out   # T2MDEW unchanged: dew point held constant


# ---------------------------------------------------------------------------------------------
def _days_between(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days


def metrics(summary, static, irrigation_pct=0.0):
    """The indicator set the simulator compares (all from derived.py output).

    Called twice per request: once for the baseline (real climate) and once for the scenario, so
    both columns of the Base vs Scenario table are built by exactly the same code.
    """
    # Climatic deficit: for each complete year, add up only the months where rain < ET0 (negative
    # balances), then average over the years. clip(upper=0) turns surplus months into 0.
    series = pd.DataFrame(summary["monthly_series"])
    series["year"] = series["month"].str[:4]
    full = series.groupby("year").filter(lambda g: g["p_minus_et0_mm"].notna().sum() == 12)
    neg = full.assign(d=full["p_minus_et0_mm"].clip(upper=0)).groupby("year")["d"].sum()
    deficit = float(-neg.mean()) if len(neg) else None
    a = irrigation_pct / 100
    clim = summary["monthly_climatology"]
    deficit_months = [m["month"] for m in clim if m["p_minus_et0_mm"] is not None and m["p_minus_et0_mm"] < 0]
    if a >= 1:
        deficit_months = []
    fr = summary["frost"]["air_frost_0c"]
    ff_median, _ = _frost_stats(summary)
    ext = summary["precip_extremes"]["mean_per_year"]
    er = derived.erosion_index(
        slope_p90_deg=static.get("slope_p90_deg"), rx1day_mm=ext["rx1day_mm"], r95p_mm=ext["r95p_mm"],
        clay_pct=static.get("clay_pct"), sand_pct=static.get("sand_pct"), oc_g_kg=static.get("oc_g_kg"),
        bare=static.get("bare_months"), wet_months=derived.wettest_months(clim))
    return {
        "water_balance": {
            "mean_annual_deficit_mm": r(deficit, 1),        # climatic: sum of monthly P - ET0 < 0
            "remaining_deficit_mm": r(deficit * (1 - a), 1) if deficit is not None else None,
            "irrigation_covered_mm": r(deficit * a, 1) if deficit is not None else None,
            "deficit_months": deficit_months,
            "annual_mean_p_minus_et0_mm": summary["water_balance"]["annual_mean_p_minus_et0_mm"],
            "annual_mean_precip_mm": summary["water_balance"]["annual_mean_precip_mm"],
            "et0_annual_mm": summary["et0"]["annual_mean_mm"],
        },
        "heat": {
            "threshold_c": config.T("heat_tmax_c"),
            "heat_days_per_year": r(sum(m["heat_days_mean"] or 0 for m in clim), 1),
            "monthly_heat_days": [m["heat_days_mean"] for m in clim],
        },
        "frost": {
            "frost_days_le0_per_year": r(sum(m["frost_days_le0"] or 0 for m in clim), 1),
            "frost_days_le2_per_year": r(sum(m["frost_days_le2"] or 0 for m in clim), 1),
            "last_spring_frost": {k: fr["last_spring_frost"][k] for k in ("p10", "p50", "p90")},
            "first_autumn_frost": {k: fr["first_autumn_frost"][k] for k in ("p10", "p50", "p90")},
            "frost_free_days_median": ff_median,
        },
        "precip_extremes": {"rx1day_mm": ext["rx1day_mm"], "r95p_mm": ext["r95p_mm"],
                            "r95p_days": ext["r95p_days"], "r20mm_days": ext["r20mm_days"],
                            "r95_threshold_mm": summary["precip_extremes"]["r95_threshold_mm"]},
        "erosion_index": er and {k: er[k] for k in ("value", "index", "factors", "confidence", "note")},
        "wettest_months": derived.wettest_months(clim),
    }


def _mmdd_doy(s):
    if not s:
        return None
    return pd.Timestamp(f"2001-{s}").day_of_year


# (indicator, getter, unit, which direction is worse)
# "up" means a higher value is worse (more deficit, more heat days); "down" means lower is worse
# (a shorter frost-free season). The lambdas pull one number out of the metrics dict.
DELTA_SPECS = [
    ("mean_annual_deficit_mm", lambda m: m["water_balance"]["mean_annual_deficit_mm"], "mm/yr", "up"),
    ("remaining_deficit_mm", lambda m: m["water_balance"]["remaining_deficit_mm"], "mm/yr", "up"),
    ("deficit_months", lambda m: len(m["water_balance"]["deficit_months"]), "months", "up"),
    ("et0_annual_mm", lambda m: m["water_balance"]["et0_annual_mm"], "mm/yr", "up"),
    ("heat_days_per_year", lambda m: m["heat"]["heat_days_per_year"], "days/yr", "up"),
    ("frost_days_le0_per_year", lambda m: m["frost"]["frost_days_le0_per_year"], "days/yr", "up"),
    ("frost_days_le2_per_year", lambda m: m["frost"]["frost_days_le2_per_year"], "days/yr", "up"),
    ("last_spring_frost_p50_doy", lambda m: _mmdd_doy(m["frost"]["last_spring_frost"]["p50"]), "day of year", "up"),
    ("frost_free_days_median", lambda m: m["frost"]["frost_free_days_median"], "days", "down"),
    ("rx1day_mm", lambda m: m["precip_extremes"]["rx1day_mm"], "mm", "up"),
    ("r95p_mm", lambda m: m["precip_extremes"]["r95p_mm"], "mm/yr", "up"),
    ("erosion_index", lambda m: (m["erosion_index"] or {}).get("index"), "index 0-1", "up"),
]


def deltas(base, scen):
    out = []
    for name, get, unit, worse in DELTA_SPECS:
        b, s = get(base), get(scen)
        if b is None or s is None:
            continue
        ch = round(s - b, 2)
        direction = "same" if abs(ch) < 1e-9 else (
            "worse" if (ch > 0) == (worse == "up") else "better")
        out.append({"indicator": name, "baseline": r(b, 2), "scenario": r(s, 2), "change": r(ch, 2),
                    "unit": unit, "direction": direction})
    return out


# ---------------------------------------------------------------------------------------------
def risk_zones(grid, static, scen_metrics, base_metrics):
    """Per-pixel erosion class (slope varies per pixel; R, K, C are parcel/zone factors) and
    possible cold-air pooling (TPI hollow + low slope, scaled by the scenario's frost days)."""
    if grid is None:
        return None
    # The grid is stored as flat lists (row by row, north to south). numpy arrays let us apply the
    # same formula to every pixel at once.
    slope = np.array([np.nan if v is None else v for v in grid["slope_deg"]], float)
    tpi = np.array([np.nan if v is None else v for v in grid["tpi_m"]], float)
    inside = np.array(grid["in_parcel"]) == 1
    valid = inside & ~np.isnan(slope)
    sf = derived.slope_factor_array(np.nan_to_num(slope))

    def erosion_codes(m):
        ext = m["precip_extremes"]
        others = [f for f in (derived.erosivity_factor(ext["rx1day_mm"], ext["r95p_mm"]),
                              derived.erodibility_factor(static.get("clay_pct"), static.get("sand_pct"),
                                                         static.get("oc_g_kg")),
                              derived.cover_factor(static.get("bare_months"),
                                                   m["wettest_months"]))
                  if f is not None]
        if len(others) < 2:                          # slope + at least 2 others (same 3-of-4 rule)
            return None, None
        # Same geometric mean as derived.erosion_index, but slope is an array (one value per pixel)
        # while the other factors are single numbers for the whole parcel.
        logs = np.log(np.maximum(sf, 1e-6)) + sum(np.log(max(f, 1e-6)) for f in others)
        idx = np.exp(logs / (1 + len(others)))
        lo, hi = derived.EROSION_CLASS_LIMITS
        cls = np.where(idx < lo, 1, np.where(idx < hi, 2, 3))
        # Encode the classes as one short string ("1" low, "2" medium, "3" high, "." outside), which is
        # much smaller to send to the browser than a JSON list of numbers.
        codes = "".join(str(c) if v else "." for c, v in zip(cls, valid))
        n = valid.sum() or 1
        return codes, {k: r((cls[valid] == i).sum() / n, 3) for i, k in ((1, "low"), (2, "medium"), (3, "high"))}

    def cold_codes(m):
        fd = m["frost"]["frost_days_le0_per_year"] or 0
        hollow = valid & (tpi <= COLD_AIR["tpi_max_m"]) & (slope <= COLD_AIR["slope_max_deg"])
        intensity = min(1.0, fd / COLD_AIR["frost_days_full"]) if fd > 0 else 0.0
        codes = "".join(("1" if h and intensity > 0 else "0") if v else "." for h, v in zip(hollow, valid))
        return codes, r(intensity, 3), r(hollow.sum() / (valid.sum() or 1), 3)

    eb, eb_sum = erosion_codes(base_metrics)
    es, es_sum = erosion_codes(scen_metrics)
    cb, ib, frac = cold_codes(base_metrics)
    cs, is_, _ = cold_codes(scen_metrics)
    return {
        "grid_ref": grid.get("ref"), "bbox": grid["bbox"], "rows": grid["rows"], "cols": grid["cols"],
        "erosion": {"base": eb, "scenario": es, "legend": {"1": "low", "2": "medium", "3": "high", ".": "outside parcel"},
                    "summary": {"base": eb_sum, "scenario": es_sum},
                    "note": "Relative screening index; not a soil-loss estimate. Inside the parcel only slope "
                            "varies per pixel; rainfall erosivity, soil and cover are parcel/zone factors."},
        "cold_air": {"base": cb, "scenario": cs, "intensity": {"base": ib, "scenario": is_},
                     "hollow_fraction": frac, "rule": COLD_AIR,
                     "note": "Possible cold-air pooling: TPI <= -1 m and slope <= 2 deg (team screening rule, not a "
                             "validated model). Frost comes from 2 m air in a ~50 km cell; relief only shows where "
                             "it could be worse."},
        "data_type": "derived + hypothetical",
    }


def _explain(p, base, scen, dl):
    """Plain-English sentences built from the computed deltas (fixed templates, no AI text).
    A sentence is only added when its number exists and actually changed."""
    d = {x["indicator"]: x for x in dl}
    out = []
    parts = []
    if p["delta_precip_pct"]:
        parts.append(f"{p['delta_precip_pct']:+.0f}% rain")
    if p["delta_temp_c"]:
        parts.append(f"{p['delta_temp_c']:+.1f} °C")
    lead = f"With {' and '.join(parts)}" if parts else "With no climate change applied"
    x = d.get("mean_annual_deficit_mm")
    if x:
        out.append(f"{lead}, the mean annual climatic water deficit (months with rain below ET0) goes from "
                   f"{x['baseline']:.0f} mm to {x['scenario']:.0f} mm ({x['change']:+.0f} mm).")
    x = d.get("heat_days_per_year")
    if x and x["change"]:
        out.append(f"Days with Tmax ≥ {config.T('heat_tmax_c'):.0f} °C go from {x['baseline']:.1f} to "
                   f"{x['scenario']:.1f} per year on average.")
    x = d.get("frost_days_le0_per_year")
    if x and x["change"]:
        out.append(f"Frost days (Tmin ≤ 0 °C) go from {x['baseline']:.1f} to {x['scenario']:.1f} per year.")
    x = d.get("frost_free_days_median")
    if x and x["change"]:
        out.append(f"The median frost-free season changes by {x['change']:+.0f} days "
                   f"({x['baseline']:.0f} → {x['scenario']:.0f}).")
    x = d.get("et0_annual_mm")
    if x and x["change"]:
        out.append(f"Reference evapotranspiration rises from {x['baseline']:.0f} to {x['scenario']:.0f} mm/yr "
                   "(dew point held constant).")
    x = d.get("rx1day_mm")
    if x and x["change"]:
        out.append(f"The wettest day of the year averages {x['scenario']:.0f} mm instead of {x['baseline']:.0f} mm.")
    eb, es = base.get("erosion_index"), scen.get("erosion_index")
    if eb and es and eb["value"] != es["value"]:
        out.append(f"The relative erosion screening class changes from {eb['value']} to {es['value']}.")
    if p["irrigation_enabled"] and scen["water_balance"]["irrigation_covered_mm"] is not None:
        out.append(f"A hypothetical irrigation availability of {p['irrigation_availability_pct']:.0f}% covers "
                   f"{scen['water_balance']['irrigation_covered_mm']:.0f} mm of that deficit, leaving "
                   f"{scen['water_balance']['remaining_deficit_mm']:.0f} mm; efficiency and applied depth are "
                   "not modelled.")
    return out


@lru_cache(maxsize=512)
def _simulate_cached(key, dp, dt, irr_on, irr, crop_id=None):
    t0 = time.perf_counter()
    bundle, df, base_summary, grid = _baseline(key)
    static = bundle["erosion_static"]
    lat, elev = bundle["centroid"][1], bundle.get("grid_elevation_m") or 0.0
    # With both climate sliders at zero we reuse the baseline objects. This is also what guarantees
    # "controls at zero == analyze" (tested in tests/test_simulate.py).
    df_scen = df if (dp == 0 and dt == 0) else perturb(df, dp, dt)
    scen_summary = base_summary if (dp == 0 and dt == 0) else _scenario_summary(key, dp, dt)
    a = irr if irr_on else 0.0
    base_m = metrics(base_summary, static, 0.0)
    scen_m = metrics(scen_summary, static, a)
    crop_block = None
    if crop_id:
        crop = next((c for c in load_catalog()["crops"] if c["id"] == crop_id), None)
        if crop is None:
            raise UnknownCrop(f"Unknown crop id {crop_id!r}.")
        et0_b = _base_et0(key)
        et0_s = et0_b if df_scen is df else derived.et0_daily(df_scen, lat, elev)[0]
        crop_block = crop_effect(crop, df, et0_b, df_scen, et0_s,
                                 base_m["frost"]["frost_free_days_median"],
                                 scen_m["frost"]["frost_free_days_median"], a,
                                 base_m["frost"]["last_spring_frost"]["p90"],
                                 scen_m["frost"]["last_spring_frost"]["p90"])
    p = {"delta_precip_pct": dp, "delta_temp_c": dt, "irrigation_enabled": irr_on,
         "irrigation_availability_pct": irr if irr_on else 0}
    dl = deltas(base_m, scen_m)
    if grid is not None:
        grid = dict(grid, ref=key[:16])
    zones = risk_zones(grid, static, scen_m, base_m)
    gaps = []
    if zones is None:
        gaps.append({"indicator": "risk_zones", "code": "TERRAIN_GRID_NOT_CACHED",
                     "reason": "No 30 m terrain grid for this parcel (needs Earth Engine once)."})
    if scen_m["erosion_index"] is None:
        gaps.append({"indicator": "erosion_index", "code": "INPUTS_MISSING",
                     "reason": "Fewer than 3 of the 4 erosion factors are available."})
    assumptions = [
        f"Uniform delta applied to the {bundle['start'][:4]}-{bundle['end'][:4]} NASA POWER daily series of this "
        "parcel's MERRA-2 cell; variability is kept, heatwave frequency only changes through the shift.",
        "Rain: every day multiplied by (1 + ΔP).",
        "Temperature: ΔT added to T2M, T2M_MAX and T2M_MIN; dew point held constant (vapour-pressure deficit rises).",
        "POWER FROST_DAYS and GWETROOT are not shifted and are left out of the scenario.",
        "Irrigation is a hypothetical share of each monthly deficit covered; no volume, efficiency or applied "
        "depth is modelled and it does not change heat, frost or erosion.",
        "Erosion keeps slope, soil and bare months fixed; only rainfall erosivity changes.",
    ]
    return {
        "version": RULES_VERSION,
        "mode": "demo" if _find("baseline", f"{key}.json").parent.parent == config.DEMO_DIR else "real",
        "geometry_hash": key,
        "scenario": p,
        "assumptions": assumptions,
        "baseline": base_m,
        "scenario_result": scen_m,
        "deltas": dl,
        "crop_effect": crop_block,
        "risk_zones": zones,
        "explanation": _explain(p, base_m, scen_m, dl) + [
            "Unchanged: NDVI history, soil properties, slope and crop history."],
        "unchanged": ["NDVI history", "Soil properties (OpenLandMap)", "Slope (NASADEM)", "Crop history (CDL)",
                      "SMAP soil moisture"],
        "labels": {"baseline": "reanalysis + derived", "scenario_result": "hypothetical"},
        "warnings": [{"code": "HYPOTHETICAL_SCENARIO", "message": "Hypothetical scenario, not a prediction."},
                     {"code": "ZONE_SCALE_DATA", "message": "Climate values describe a ~50 x 60 km cell."}],
        "data_gaps": gaps,
        "provenance": {"sources": ["NASA POWER (daily, AG)", "NASA/NASADEM_HGT/001", "OpenLandMap", "Landsat 8/9"],
                       "rules_version": RULES_VERSION, "ai_assistance": AI_ASSISTANCE},
        "timing_ms": {"server": round((time.perf_counter() - t0) * 1000, 1)},
    }


CDL_TO_CROP = {"Corn": "corn_maize", "Soybeans": "soybean", "Winter Wheat": "winter_wheat",
               "Alfalfa": "alfalfa_hay_perennial", "Sugarbeets": "sugar_beet", "Sugarcane": "sugarcane_perennial",
               "Potatoes": "potato", "Sorghum": "sorghum", "Cotton": "cotton", "Rice": "rice", "Barley": "barley",
               "Peanuts": "peanut", "Tomatoes": "processing_tomato", "Grapes": "grape_perennial",
               "Almonds": "almond_perennial"}


def load_analysis(key):
    """The cached analyze response for this key (demo cache first)."""
    for p in (config.DEMO_DIR / f"{key}.json", config.CACHE_DIR / "responses" / f"{key}.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def _frost_stats(summary):
    """(median frost-free days, P90 last spring frost MM-DD) from a climate_summary."""
    fr = summary["frost"]["air_frost_0c"]
    ff = sorted(_days_between(y["last_spring_frost"], y["first_autumn_frost"]) for y in fr["per_year"]
                if y["last_spring_frost"] and y["first_autumn_frost"])
    if ff:
        return float(np.median(ff)), fr["last_spring_frost"]["p90"]
    # No year with both frosts: if the series shows frost-free years, the season is the whole year.
    no_frost = fr["last_spring_frost"]["years_without_frost"] + fr["first_autumn_frost"]["years_without_frost"]
    return (365.0 if no_frost else None), fr["last_spring_frost"]["p90"]


def screen_crops(df, lat, elev, hemisphere="north", dp=0.0, dt=0.0, irrigation_pct=0.0, ph=None, prev_crop=None,
                 grown=None, n_years=0, soil=None, base_summary=None, scen_summary=None, et0_base=None):
    """Evaluate every catalogue crop on one daily series and scenario, ranked (pure, no cache, no network).

    Used by /recommend and by scripts/validate_crops.py, so the reality check runs the very same code.
    The optional summaries / ET0 let the API pass memoized values instead of recomputing them.
    """
    df_scen = df if (dp == 0 and dt == 0) else perturb(df, dp, dt)
    base_summary = base_summary or derived.climate_summary(df, lat, elev, hemisphere)
    if scen_summary is None:
        scen_summary = base_summary if df_scen is df else derived.climate_summary(df_scen, lat, elev, hemisphere)
    et0_b = et0_base if et0_base is not None else derived.et0_daily(df, lat, elev)[0]
    et0_s = et0_b if df_scen is df else derived.et0_daily(df_scen, lat, elev)[0]
    ff_b, lsf_b = _frost_stats(base_summary)
    ff_s, lsf_s = _frost_stats(scen_summary)
    grown = grown or {}
    items = []
    for crop in load_catalog()["crops"]:
        eff = crop_effect(crop, df, et0_b, df_scen, et0_s, ff_b, ff_s, irrigation_pct, lsf_b, lsf_s)
        items.append(rec.evaluate(crop, eff, ph, prev_crop, grown.get(crop["id"], 0), n_years, soil))
    return rec.rank(items)


def _next_season_year():
    """Calendar year of the next growing season (from September on, plan for next year)."""
    from datetime import date
    t = date.today()
    return t.year + 1 if t.month >= 9 else t.year


@lru_cache(maxsize=256)
def recommend_cached(key, dp, dt, irr_on, irr):
    """Evaluate all 15 catalogue crops for one parcel and scenario, then rank them (see recommend.py).

    It reuses the memoized scenario metrics and the daily series, so 15 crops take ~0.2-0.3 s.
    """
    t0 = time.perf_counter()
    bundle, df, base_summary, _ = _baseline(key)
    sim = _simulate_cached(key, dp, dt, irr_on, irr, None)        # memoized scenario metrics
    lat, elev = bundle["centroid"][1], bundle.get("grid_elevation_m") or 0.0
    a = irr if irr_on else 0.0
    scen_summary = base_summary if (dp == 0 and dt == 0) else _scenario_summary(key, dp, dt)

    analysis = load_analysis(key) or {}
    ind = analysis.get("indicators") or {}
    soil = ind.get("soil_openlandmap") or {}
    ph = soil.get("ph_h2o")
    years = (ind.get("crop_type") or {}).get("years") or []
    catalog = {c["id"]: c for c in load_catalog()["crops"]}
    prev_name = years[-1]["dominant"][0]["name"] if years and years[-1]["dominant"] else None
    prev_crop = catalog.get(CDL_TO_CROP.get(prev_name)) if prev_name else None

    # Count how many years each crop was the dominant CDL class on this field (crop history).
    grown = {}
    for y in years:
        cid = CDL_TO_CROP.get(y["dominant"][0]["name"]) if y.get("dominant") else None
        if cid:
            grown[cid] = grown.get(cid, 0) + 1
    ranked = screen_crops(df, lat, elev, bundle["hemisphere"], dp, dt, a, ph, prev_crop, grown, len(years),
                          soil, base_summary, scen_summary, _base_et0(key))
    return {
        "version": "rec-1", "geometry_hash": key, "scenario": sim["scenario"],
        "previous_crop": {"cdl_name": prev_name, "year": years[-1]["year"] if years else None,
                          "catalogue_id": prev_crop["id"] if prev_crop else None},
        "soil_ph": ph,
        "crops": ranked,
        "rotation_plan": rec.rotation_plan(ranked, catalog, prev_crop, years[-1]["year"] if years else None,
                                           start_year=_next_season_year()),
        "summary": {g: [x["crop"] for x in ranked if x["group"] == g] for g in rec.GROUP_ORDER},
        "rules": rec.RULES,
        "warnings": [{"code": "HYPOTHETICAL_SCENARIO", "message": "Hypothetical scenario, not a prediction."},
                     {"code": "SCREENING_NOT_ADVICE", "message": "Rule-based screening to support the farmer's "
                      "decision; check with a local agronomist, market and machinery before sowing."}],
        "provenance": {"sources": ["NASA POWER (daily)", "OpenLandMap pH", "USDA CDL", "Team crop catalogue"],
                       "ai_assistance": AI_ASSISTANCE},
        "timing_ms": {"server": round((time.perf_counter() - t0) * 1000, 1)},
    }


def recommend(key, delta_precip_pct=0, delta_temp_c=0, irrigation_enabled=False, irrigation_availability_pct=0):
    dp = clamp("delta_precip_pct", delta_precip_pct)
    dt = clamp("delta_temp_c", delta_temp_c)
    irr = clamp("irrigation_availability_pct", irrigation_availability_pct)
    return recommend_cached(key, dp, dt, bool(irrigation_enabled), irr if irrigation_enabled else 0.0)


def clear_simulation_cache():
    """Call after a terrain grid is added so risk zones appear on the next request."""
    recommend_cached.cache_clear()
    _scenario_summary.cache_clear()
    _baseline.cache_clear()
    _base_et0.cache_clear()
    _simulate_cached.cache_clear()


def simulate(key, delta_precip_pct=0, delta_temp_c=0, irrigation_enabled=False, irrigation_availability_pct=0,
             crop_id=None):
    """Public entry point used by api.py: clean the inputs, then call the memoized function.
    Rounding first means 1.04 degC and 1.0 degC share the same cache entry."""
    dp = clamp("delta_precip_pct", delta_precip_pct)
    dt = clamp("delta_temp_c", delta_temp_c)
    irr = clamp("irrigation_availability_pct", irrigation_availability_pct)
    return _simulate_cached(key, dp, dt, bool(irrigation_enabled), irr if irrigation_enabled else 0.0, crop_id or None)
