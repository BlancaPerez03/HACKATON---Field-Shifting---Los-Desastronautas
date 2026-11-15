"""Derived indicators (dossier section 6). Pure functions: no network, no Earth Engine.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Every function returns values plus the method, thresholds, inputs, confidence and gaps it used.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config
from .config import T
from .contract import r
from .et0 import et0_hargreaves, et0_pm

# =============================================================================================
# Climate (NASA POWER daily)
# =============================================================================================


def et0_daily(df, lat, elevation_m):
    """FAO-56 Penman-Monteith where all inputs exist; Hargreaves-Samani otherwise.

    Returns (et0 Series in mm/day, method Series with 'pm' / 'hargreaves' / NaN).
    """
    doy = df.index.day_of_year.values        # day of year (1..366) needed for the sun position
    has = lambda c: c in df.columns  # noqa: E731   small helper: does the DataFrame have this column?
    pm = pd.Series(np.nan, index=df.index)
    if all(has(c) for c in ("T2M_MAX", "T2M_MIN", "ALLSKY_SFC_SW_DWN", "WS2M")) and \
            (has("T2MDEW") or has("RH2M")):
        pm = pd.Series(et0_pm(
            df["T2M_MAX"], df["T2M_MIN"], df["ALLSKY_SFC_SW_DWN"], df["WS2M"], lat, doy, elevation_m,
            tdew=df["T2MDEW"] if has("T2MDEW") else None,
            rh_mean=df["RH2M"] if not has("T2MDEW") else None,
            pressure_kpa=df["PS"] if has("PS") and df["PS"].notna().all() else None,
        ), index=df.index)
        need = ["T2M_MAX", "T2M_MIN", "ALLSKY_SFC_SW_DWN", "WS2M", "T2MDEW" if has("T2MDEW") else "RH2M"]
        pm[df[need].isna().any(axis=1)] = np.nan
    hg = pd.Series(et0_hargreaves(df["T2M_MAX"], df["T2M_MIN"], lat, doy,
                                  tmean=df["T2M"] if has("T2M") else None), index=df.index)
    hg[df[["T2M_MAX", "T2M_MIN"]].isna().any(axis=1)] = np.nan
    # Use Penman-Monteith where possible and fill the remaining gaps with Hargreaves.
    et0 = pm.fillna(hg)
    method = pd.Series(np.where(pm.notna(), "pm", np.where(hg.notna(), "hargreaves", None)),
                       index=df.index)
    return et0, method, hg


def _doy_to_mmdd(doy):
    # Day of year -> "MM-DD" using 2001 (not a leap year) as a reference calendar.
    if doy is None:
        return None
    return (date(2001, 1, 1) + timedelta(days=int(round(doy)) - 1)).strftime("%m-%d")


def frost_dates(tmin, hemisphere="north", threshold=None, min_coverage=0.9):
    """Last spring and first autumn frost per agricultural year, as P10/P50/P90 across years.

    North: the year splits on 1 July (last spring frost = last day Jan-Jun with Tmin <= thr;
    first autumn frost = first day Jul-Dec). South: the frost season is mid-year, so last spring
    frost is the last day Jul-Dec and first autumn frost the first day Jan-Jun.
    Windows with less than `min_coverage` valid days are skipped.
    """
    thr = T("frost_tmin_c") if threshold is None else threshold
    per_year, spring, autumn = [], [], []
    n_no_spring = n_no_autumn = 0
    # numpy masks instead of per-year date slicing (same result, ~10x faster for the simulator)
    vals = tmin.to_numpy(dtype=float)
    years = tmin.index.year.to_numpy()
    months = tmin.index.month.to_numpy()
    doys = tmin.index.day_of_year.to_numpy()
    valid = ~np.isnan(vals)
    frost = valid & (vals <= thr)
    for y in np.unique(years):
        in_y = years == y
        h1, h2 = in_y & (months <= 6), in_y & (months >= 7)
        sp_win, au_win = (h1, h2) if hemisphere == "north" else (h2, h1)
        row = {"year": int(y), "last_spring_frost": None, "first_autumn_frost": None}
        if sp_win.sum() >= 150 and valid[sp_win].mean() >= min_coverage:
            hits = np.flatnonzero(sp_win & frost)
            if hits.size == 0:
                n_no_spring += 1
            else:
                spring.append(int(doys[hits[-1]]))
                row["last_spring_frost"] = tmin.index[hits[-1]].strftime("%Y-%m-%d")
        if au_win.sum() >= 150 and valid[au_win].mean() >= min_coverage:
            hits = np.flatnonzero(au_win & frost)
            if hits.size == 0:
                n_no_autumn += 1
            else:
                autumn.append(int(doys[hits[0]]))
                row["first_autumn_frost"] = tmin.index[hits[0]].strftime("%Y-%m-%d")
        per_year.append(row)

    # Percentiles across years: P50 = the "typical" year, P10 / P90 = early / late years
    # (1 year in 10 is earlier than P10, 1 year in 10 is later than P90).
    def pct(v):
        if not v:
            return {"p10": None, "p50": None, "p90": None}
        return {f"p{q}": _doy_to_mmdd(np.percentile(v, q)) for q in (10, 50, 90)}

    return {
        "threshold_c": thr,
        "hemisphere": hemisphere,
        "last_spring_frost": {**pct(spring), "years_with_frost": len(spring),
                              "years_without_frost": n_no_spring},
        "first_autumn_frost": {**pct(autumn), "years_with_frost": len(autumn),
                               "years_without_frost": n_no_autumn},
        "per_year": per_year,
        "note": ("Percentiles across years (MM-DD). For the last spring frost, P90 is the late date "
                 "exceeded 1 year in 10; for the first autumn frost, P10 is the early date. "
                 "Years without frost are excluded from the percentiles and counted separately."),
    }


def _monthly_sum(s, min_count=20):
    # resample("MS") groups daily rows by month ("Month Start"). min_count=20 means: if a month has
    # fewer than 20 valid days the result is NaN instead of an artificially low sum.
    return s.resample("MS").sum(min_count=min_count)


def precip_extremes(p, wet_mm=None, heavy_mm=None, pct=None):
    """ETCCDI R95p (wet-day percentile), R20mm and Rx1day, per year and averaged."""
    wet_mm = T("wet_day_mm") if wet_mm is None else wet_mm
    heavy_mm = T("very_heavy_precip_mm") if heavy_mm is None else heavy_mm
    pct = T("r95_percentile") if pct is None else pct
    # The threshold is the 95th percentile of WET days only (P >= 1 mm). Using all days would give a
    # tiny threshold because most days have no rain at all.
    wet = p[p >= wet_mm].dropna()
    thr = float(np.percentile(wet, pct)) if len(wet) >= 20 else None
    rows = []
    for y, g in p.groupby(p.index.year):
        if g.notna().mean() < 0.9:
            continue
        rows.append({
            "year": int(y),
            "r95p_days": int((g > thr).sum()) if thr is not None else None,
            "r95p_mm": r(g[g > thr].sum(), 1) if thr is not None else None,
            "r20mm_days": int((g >= heavy_mm).sum()),
            "rx1day_mm": r(g.max(), 1),
            "prcptot_wet_mm": r(g[g >= wet_mm].sum(), 1),
        })
    df = pd.DataFrame(rows)

    def mean(c):
        return r(df[c].mean(), 1) if len(df) and df[c].notna().any() else None

    return {
        "r95_threshold_mm": r(thr, 1),
        "wet_days_in_reference": int(len(wet)),
        "mean_per_year": {"r95p_days": mean("r95p_days"), "r95p_mm": mean("r95p_mm"),
                          "r20mm_days": mean("r20mm_days"), "rx1day_mm": mean("rx1day_mm")},
        "per_year": rows,
        "method": (f"R95p: days with P above the {pct}th percentile of wet days (P >= {wet_mm} mm) "
                   f"over the whole request period, and their total. R20mm: days with P >= {heavy_mm} mm. "
                   "Rx1day: annual maximum daily P."),
    }


def climate_summary(df, lat, elevation_m, hemisphere="north"):
    """All POWER-derived climate indicators for one location."""
    # Step 1: daily values (ET0 and 0/1 flags for frost and heat days). `.where(notna)` keeps NaN on
    # days without temperature, so a missing day is not counted as "no frost".
    d = df.copy()
    d["ET0"], method, hg = et0_daily(d, lat, elevation_m)
    p = d["PRECTOTCORR"]
    d["frost0"] = (d["T2M_MIN"] <= T("frost_tmin_c")).astype(float).where(d["T2M_MIN"].notna())
    d["frost2"] = (d["T2M_MIN"] <= T("ground_frost_tmin_c")).astype(float).where(d["T2M_MIN"].notna())
    d["heat"] = (d["T2M_MAX"] >= T("heat_tmax_c")).astype(float).where(d["T2M_MAX"].notna())

    # Step 2: one row per month of the series (120 rows for 10 years). Summing the 0/1 flags gives
    # the number of frost / heat days in each month.
    sums = pd.DataFrame({"precip_mm": p, "et0_mm": d["ET0"], "et0_hargreaves_mm": hg,
                         "frost_days_le0": d["frost0"], "frost_days_le2": d["frost2"], "heat_days": d["heat"]})
    if "FROST_DAYS" in d:
        sums["power_frost_days"] = d["FROST_DAYS"]
    m = sums.resample("MS").sum(min_count=20)            # one resample for all monthly sums
    means = d[["T2M_MAX", "T2M_MIN"]].resample("MS").mean()
    m["tmax_c"], m["tmin_c"] = means["T2M_MAX"], means["T2M_MIN"]
    if "GWETROOT" in d:
        m["gwetroot"] = d["GWETROOT"].resample("MS").mean()
    m["p_minus_et0_mm"] = m["precip_mm"] - m["et0_mm"]
    m["cal_month"] = m.index.month

    # Water deficit flag: monthly P - ET0 at or below the 20th percentile of the same calendar month.
    q = T("deficit_percentile") / 100
    p20 = m.groupby("cal_month")["p_minus_et0_mm"].transform(lambda s: s.quantile(q))
    m["deficit"] = (m["p_minus_et0_mm"] <= p20) & m["p_minus_et0_mm"].notna()

    # Step 3: climatology = average of all Januaries, all Februaries... (12 rows).
    g = m.groupby("cal_month")
    mean, mx = g.mean(numeric_only=True), g.max(numeric_only=True)
    monthly = []
    for mo in range(1, 13):
        if mo not in mean.index:
            continue
        row = mean.loc[mo]
        monthly.append({
            "month": mo,
            "precip_mm": r(row["precip_mm"], 1),
            "et0_mm": r(row["et0_mm"], 1),
            "et0_hargreaves_mm": r(row["et0_hargreaves_mm"], 1),
            "p_minus_et0_mm": r(row["p_minus_et0_mm"], 1),
            "tmax_c": r(row["tmax_c"], 1),
            "tmin_c": r(row["tmin_c"], 1),
            "frost_days_le0": r(row["frost_days_le0"], 1),
            "frost_days_le2": r(row["frost_days_le2"], 1),
            "power_frost_days": r(row.get("power_frost_days"), 1),
            "heat_days_mean": r(row["heat_days"], 1),
            "heat_days_max": r(mx.loc[mo, "heat_days"], 0),
            "years": int(g["precip_mm"].count().loc[mo]),
        })

    # Step 4: yearly totals (a year needs 330+ valid days) and a linear trend per decade.
    # np.polyfit(x, y, 1) fits a straight line; [0] is its slope (mm per year), * 10 = per decade.
    yearly = pd.DataFrame({"p": p.resample("YS").sum(min_count=330),
                           "et0": d["ET0"].resample("YS").sum(min_count=330)}).dropna()
    yearly["bal"] = yearly["p"] - yearly["et0"]
    trend = None
    if len(yearly) >= 8:
        trend = r(np.polyfit(yearly.index.year.astype(float), yearly["bal"].values, 1)[0] * 10, 1)

    # GWETROOT: wetness index 0-1 (not volumetric). Hide it if it is flat (observed constant 0.5).
    swi = None
    if "GWETROOT" in d and d["GWETROOT"].std() >= T("gwetroot_min_std"):
        swi = {"unit": "dimensionless wetness index (0-1), not volumetric",
               "monthly_mean": [{"month": mo, "value": r(mean.loc[mo, "gwetroot"], 3)}
                                for mo in mean.index],
               "daily_std": r(d["GWETROOT"].std(), 3)}

    complete = int((p.groupby(p.index.year).count() >= 360).sum())
    series = [{"month": i.strftime("%Y-%m"), "precip_mm": r(pm, 1), "et0_mm": r(em, 1),
               "p_minus_et0_mm": r(bm, 1), "heat_days": r(hd, 0), "deficit": bool(df_)}
              for i, pm, em, bm, hd, df_ in zip(m.index, m["precip_mm"], m["et0_mm"], m["p_minus_et0_mm"],
                                                m["heat_days"], m["deficit"])]
    return {
        "years_complete": complete,
        "monthly_climatology": monthly,
        "monthly_series": series,
        "frost": {"air_frost_0c": frost_dates(d["T2M_MIN"], hemisphere, T("frost_tmin_c")),
                  "ground_frost_2c": frost_dates(d["T2M_MIN"], hemisphere, T("ground_frost_tmin_c"))},
        "et0": {
            "annual_mean_mm": r(yearly["et0"].mean(), 0) if len(yearly) else None,
            "hargreaves_annual_mean_mm": r(hg.resample("YS").sum(min_count=330).mean(), 0),
            "pm_days": int((method == "pm").sum()),
            "hargreaves_days": int((method == "hargreaves").sum()),
            "method": "FAO-56 Penman-Monteith (eq. 6) with POWER surface pressure and dew point; "
                      "Hargreaves-Samani (eq. 52) where radiation, wind or humidity is missing. "
                      "Hargreaves is also reported for every month as a cross-check.",
        },
        "water_balance": {
            "deficit_months": [x["month"] for x in monthly
                               if x["p_minus_et0_mm"] is not None and x["p_minus_et0_mm"] < 0],
            "annual_mean_p_minus_et0_mm": r(yearly["bal"].mean(), 0) if len(yearly) else None,
            "annual_mean_precip_mm": r(yearly["p"].mean(), 0) if len(yearly) else None,
            "trend_mm_per_decade": trend,
            "method": "Monthly P (PRECTOTCORR) minus reference ET0; no soil water storage is modelled. "
                      "For a crop, multiply ET0 by its Kc. Trend is a descriptive OLS slope, not a forecast.",
        },
        "precip_extremes": precip_extremes(p),
        "soil_wetness_index": swi,
    }


# =============================================================================================
# Vegetation, vulnerability and erosion (Landsat + climate + terrain + soil)
# =============================================================================================


def _obs_confidence(years_ok):
    return "high" if years_ok >= 5 else "medium" if years_ok >= 3 else "low"


def bare_months(ndvi_clim, ndti_clim=None, ndvi_thr=None, ndti_thr=None):
    """Calendar months with low green cover, split into likely bare soil vs likely residue.

    ndvi_clim / ndti_clim: [{"month": 1-12, "median": float|None, "years_2obs": int}, ...]
    """
    ndvi_thr = T("ndvi_bare") if ndvi_thr is None else ndvi_thr
    ndti_thr = T("ndti_residue") if ndti_thr is None else ndti_thr
    ndti = {x["month"]: x.get("median") for x in (ndti_clim or [])}
    months, confs = [], []
    for x in ndvi_clim:
        v = x.get("median")
        if v is None or v >= ndvi_thr:
            continue
        t = ndti.get(x["month"])
        cls = "low_cover_unclassified" if t is None else ("residue" if t >= ndti_thr else "bare")
        conf = _obs_confidence(x.get("years_2obs", 0))
        confs.append(conf)
        months.append({"month": x["month"], "class": cls, "ndvi_median": r(v, 3),
                       "ndti_median": r(t, 3), "confidence": conf})
    order = {"low": 0, "medium": 1, "high": 2}
    overall = min(confs, key=order.get) if confs else _obs_confidence(
        min((x.get("years_2obs", 0) for x in ndvi_clim), default=0))
    thin = [x["month"] for x in ndvi_clim if x.get("years_2obs", 0) < 3]
    return {
        "value": [m["month"] for m in months],
        "bare": [m["month"] for m in months if m["class"] == "bare"],
        "residue": [m["month"] for m in months if m["class"] == "residue"],
        "months": months,
        "method": f"Calendar month with NDVI climatology median < {ndvi_thr}; NDTI >= {ndti_thr} -> "
                  "likely residue, otherwise likely bare soil.",
        "inputs": ["ndvi", "ndti"],
        "thresholds": {"ndvi": ndvi_thr, "ndti": ndti_thr},
        "confidence": overall,
        "confidence_reason": ("High = 5+ years with >= 2 valid observations in the month; "
                              "medium = 3-4; low = fewer. "
                              + (f"Months with < 3 such years: {thin}." if thin else "")),
        "gaps": ["NDTI residue threshold not validated locally",
                 "Wet soil after rain can look like residue in NDTI"],
    }


def vulnerability(ndvi_monthly, ndvi_clim, climate_series, smap_anomaly=None, z_thr=None):
    """Months where low NDVI (z <= -1) co-occurs with heat or water deficit. Not causation.

    ndvi_monthly: [{"month": "YYYY-MM", "median": float|None}]
    ndvi_clim: [{"month": 1-12, "mean": float, "std": float, "years": int}]
    climate_series: [{"month": "YYYY-MM", "heat_days": n, "deficit": bool}]
    smap_anomaly: {"YYYY-MM": anomaly} (optional)
    """
    z_thr = T("ndvi_anomaly_z") if z_thr is None else z_thr
    # Only growing-season months: low NDVI in a month that is normally bare (winter, fallow, snow)
    # is not stress.
    clim = {c["month"]: c for c in ndvi_clim
            if c.get("median") is not None and c["median"] >= T("ndvi_bare")}
    cl = {c["month"]: c for c in climate_series}
    smap_anomaly = smap_anomaly or {}
    # "Abnormal" heat / dryness: above the month's own mean heat days; SMAP anomaly <= -1 std.
    heat_by_m, smap_by_m = {}, {}
    for c in climate_series:
        if c.get("heat_days") is not None:
            heat_by_m.setdefault(int(c["month"][5:7]), []).append(c["heat_days"])
    for k, v in smap_anomaly.items():
        if v is not None:
            smap_by_m.setdefault(int(k[5:7]), []).append(v)
    heat_mean = {m: float(np.mean(v)) for m, v in heat_by_m.items()}
    smap_std = {m: float(np.std(v, ddof=1)) for m, v in smap_by_m.items() if len(v) > 2}
    stats = {m: {"evaluated": 0, "low_vigor": 0, "co_heat": 0, "co_deficit": 0, "co_smap_dry": 0,
                 "co_any": 0} for m in range(1, 13)}
    events = []
    for x in ndvi_monthly:
        v = x.get("median")
        mo = int(x["month"][5:7])        # "2024-07"[5:7] -> "07" -> 7
        c = clim.get(mo)
        if v is None or not c or c.get("years", 0) < 5 or not c.get("std"):
            continue
        s = stats[mo]
        s["evaluated"] += 1
        # z-score: how many standard deviations this month is below/above the usual value for that
        # calendar month. z <= -1 means "clearly less green than normal".
        z = (v - c["mean"]) / c["std"]
        if z > z_thr:
            continue
        s["low_vigor"] += 1
        k = cl.get(x["month"], {})
        hd = k.get("heat_days") or 0
        heat = hd > 0 and hd > heat_mean.get(mo, 0)
        deficit = bool(k.get("deficit"))
        a, sd = smap_anomaly.get(x["month"]), smap_std.get(mo)
        dry = a is not None and sd is not None and sd > 0 and a <= -sd
        s["co_heat"] += heat
        s["co_deficit"] += deficit
        s["co_smap_dry"] += dry
        if heat or deficit or dry:
            s["co_any"] += 1
            events.append({"month": x["month"], "ndvi_z": r(z, 2), "heat": heat,
                           "water_deficit": deficit, "smap_dry_anomaly": dry})
    months = [{"month": m, **s, "co_occurrence_frequency": r(s["co_any"] / s["evaluated"], 2)}
              for m, s in stats.items() if s["evaluated"]]
    flagged = [m["month"] for m in months if m["co_any"] >= 2]
    years = max((m["evaluated"] for m in months), default=0)
    return {
        "value": flagged,
        "label": "co-occurrence, not causation",
        "months": months,
        "events": events,
        "method": (f"Growing-season months only (NDVI climatology >= {T('ndvi_bare')}). NDVI z-score per "
                   f"month and year against the parcel's own climatology; months with z <= {z_thr} are "
                   "flagged when they coincide with more heat days than that month's mean, a monthly "
                   "P - ET0 deficit (<= its 20th percentile) or a SMAP root-zone anomaly <= -1 std. "
                   "`value` lists calendar months with at least 2 such co-occurrences."),
        "inputs": ["ndvi", "agroclimate_power", "soil_moisture_smap"],
        "thresholds": {"ndvi_z": z_thr, "deficit_percentile": T("deficit_percentile"),
                       "heat_tmax_c": T("heat_tmax_c")},
        "confidence": _obs_confidence(years),
        "confidence_reason": f"Up to {years} years evaluated per month (climatology needs >= 5).",
        "gaps": ["Low NDVI can also be harvest, fallow or a crop change, not stress",
                 "Crop calendar not known; the rotation module must check the growth stage"],
    }


def _interp(x, xs, ys):
    return None if x is None else float(np.interp(x, xs, ys))


# Factor scalings (team hypothesis, piecewise linear). Public so the simulator and the per-pixel
# risk zones use exactly the same rules as the parcel index.
SLOPE_BREAKS = ([0, 2, 5, 10, 20], [0.05, 0.15, 0.4, 0.7, 1.0])
EROSION_CLASS_LIMITS = (0.25, 0.5)     # low < 0.25 <= medium < 0.5 <= high


def slope_factor(slope_deg):
    if slope_deg is None:
        return None
    return float(np.interp(slope_deg, *SLOPE_BREAKS))


def slope_factor_array(slope_deg):
    return np.interp(np.asarray(slope_deg, float), *SLOPE_BREAKS)


def erosivity_factor(rx1day_mm=None, r95p_mm=None):
    e = [v for v in (_interp(rx1day_mm, [10, 25, 50, 100], [0.1, 0.3, 0.6, 1.0]),
                     _interp(r95p_mm, [20, 75, 150, 300], [0.1, 0.3, 0.6, 1.0])) if v is not None]
    return float(np.mean(e)) if e else None


def erodibility_factor(clay_pct=None, sand_pct=None, oc_g_kg=None):
    k = []
    if clay_pct is not None and sand_pct is not None:
        silt = max(0.0, 100 - clay_pct - sand_pct)
        k.append(_interp(silt, [10, 40, 70], [0.2, 0.6, 1.0]))
    if oc_g_kg is not None:
        k.append(_interp(oc_g_kg, [5, 10, 20, 40], [1.0, 0.7, 0.4, 0.2]))
    return float(np.mean(k)) if k else None


def cover_factor(bare=None, wet_months=None):
    if bare is None or not wet_months:
        return None
    weight = {"bare": 1.0, "low_cover_unclassified": 0.75, "residue": 0.25}
    cls = {m["month"]: m["class"] for m in bare.get("months", [])}
    return max(0.05, float(np.mean([weight.get(cls.get(m), 0.0) for m in wet_months])))


def geometric_mean(values):
    # exp(mean(log(x))) = (x1 * x2 * ... * xn) ** (1/n). Unlike the normal mean, one small factor
    # pulls the result down strongly (flat land => low erosion even with heavy rain).
    # max(v, 1e-6) avoids log(0).
    return float(np.exp(np.mean(np.log([max(v, 1e-6) for v in values]))))


def erosion_class(idx):
    lo, hi = EROSION_CLASS_LIMITS
    return "low" if idx < lo else "medium" if idx < hi else "high"


def erosion_index(slope_p90_deg=None, rx1day_mm=None, r95p_mm=None, clay_pct=None, sand_pct=None,
                  oc_g_kg=None, bare=None, wet_months=None):
    """Relative erosion screening index (0-1) inspired by RUSLE factors. Not a soil-loss estimate.

    bare: bare_months() output; wet_months: the 3 wettest calendar months.
    Factors are scaled 0-1 by piecewise-linear breakpoints (team hypothesis) and combined by
    geometric mean, so one low factor pulls the total down. One missing factor is left out and
    lowers the confidence; with fewer than 3 factors the function returns None.
    """
    f = {"slope_LS": slope_factor(slope_p90_deg),
         "erosivity_R": erosivity_factor(rx1day_mm, r95p_mm),
         "erodibility_K": erodibility_factor(clay_pct, sand_pct, oc_g_kg),
         "cover_C": cover_factor(bare, wet_months)}

    present = {k_: v for k_, v in f.items() if v is not None}
    if len(present) < 3:   # one or two factors alone would be misleading
        return None
    idx = geometric_mean(present.values())
    level = erosion_class(idx)
    missing = [k_ for k_, v in f.items() if v is None]
    return {
        "value": level,
        "index": r(idx, 3),
        "factors": {k_: r(v, 3) for k_, v in f.items()},
        "factor_inputs": {"slope_p90_deg": r(slope_p90_deg, 1), "rx1day_mm": r(rx1day_mm, 1),
                          "r95p_mm": r(r95p_mm, 1), "clay_pct": r(clay_pct, 1),
                          "sand_pct": r(sand_pct, 1), "oc_g_kg": r(oc_g_kg, 1),
                          "wet_months": wet_months},
        "note": "Relative screening index inspired by RUSLE factors; not a soil-loss estimate.",
        "method": "Geometric mean of factors scaled 0-1; low < 0.25 <= medium < 0.5 <= high.",
        "inputs": ["terrain", "agroclimate_power", "soil_openlandmap", "bare_months"],
        "thresholds": {"low_lt": 0.25, "medium_lt": 0.5, "kind": "hypothesis"},
        "confidence": "medium" if not missing else "low",
        "confidence_reason": ("All four factors available; scaling breakpoints are team hypotheses."
                              if not missing else f"Missing factors: {missing}."),
        "gaps": ["Breakpoints not calibrated against local erosion measurements"]
                + ([f"Missing: {', '.join(missing)}"] if missing else []),
    }


def wettest_months(monthly_climatology, n=3):
    """The n calendar months with the most rain (used by the erosion cover factor)."""
    rows = [x for x in monthly_climatology if x.get("precip_mm") is not None]
    return sorted(m["month"] for m in sorted(rows, key=lambda x: -x["precip_mm"])[:n])
