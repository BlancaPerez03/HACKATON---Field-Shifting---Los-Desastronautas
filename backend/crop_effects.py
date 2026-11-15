"""How a scenario affects one crop: screening checks from the daily series + the team crop catalogue.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Pure functions (no network). Not a yield model: no yield forecast, probability or score. Each check
compares a climate quantity of the crop's own season with a requirement from the catalogue
(backend/catalog/crops_us.csv + sourced parameters in crop_params.json) and labels it
ok / marginal / limit with a visible rule. Requirements are minimums for the earliest commercial
cultivars, checked against 10 US producing regions (scripts/validate_crops.py).

Season: catalogue months from sowing start to harvest end (or the crop's growth season, e.g.
sugarcane March-December), northern hemisphere calendar. Frost-sensitive annual crops only count
the days between that year's last spring frost (Tmin <= 0 degC) and first hard freeze
(Tmin <= -2 degC): the crop cannot be in the field outside that window.
"""
import numpy as np
import pandas as pd

from .contract import r
from .crops import load_params

RULES = {
    "gdd": "Heat to mature: growing degree-days of the frost-free part of the season (86/50 caps for corn, soybean "
           "and sorghum) vs the minimum of the earliest commercial cultivars. ok >= 110 %, tight 100-110 %, limit below.",
    "water": "Water: crop need = Kc x ET0 of the season (FAO-56). Supply = season rain + soil water stored before the "
             "season (at most 100 mm) + hypothetical irrigation. Expected yield loss from the shortfall = Ky x "
             "(1 - supply/need) (FAO-33). ok < 15 %, tight 15-75 %, limit >= 75 % or under 25 % of the need "
             "covered (needs irrigation). Water before the season = surplus of the 6 previous months.",
    "heat": "Heat at flowering: days with Tmax at or above the crop's reproductive failure temperature (Hatfield et al. "
            "2011). 10 or more per season = tight (yield risk). Never limiting by itself.",
    "cool_season": "Cool-season crops (potato, sugar beet, barley): mean temperature of the hottest season month; above "
                   "the crop's limit it is a winter crop there, not a spring-sown one.",
    "frost_free": "Frost-free season: median days between last spring and first autumn frost (Tmin <= 0 degC) vs the "
                  "crop minimum. ok >= 15 days spare, tight 0-15, limit shorter.",
    "safe_sowing": "Sowing: ok if frost is over (9 years in 10) before the window opens, tight if it ends inside the "
                   "window (sow later), limit if only after the window.",
    "winter_cold": "Winter survival: average annual extreme minimum temperature (the USDA hardiness-zone definition) vs "
                   "the crop's tolerance.",
    "vernalization": "Winter wheat must be chilled to flower: days with mean temperature 0-10 degC from October to March.",
    "humid_summer": "Almond needs a dry Mediterranean summer; vinifera grapes fail where mild winters and humid summers "
                    "allow Pierce's disease.",
    "bloom_frost": "Almond flowers in February-March: the 1-in-10-year last spring frost must come before bloom ends.",
}
QUESTIONS = {
    "gdd": "Enough heat to mature?", "water": "Enough water?", "heat": "Heat at flowering?",
    "cool_season": "Summer too hot for this cool-season crop?", "frost_free": "Long enough frost-free season?",
    "safe_sowing": "When can I sow without frost risk?", "winter_cold": "Survives the winter cold?",
    "vernalization": "Enough winter cold to flower?", "humid_summer": "Climate dry enough for this crop?",
    "bloom_frost": "Frost at flowering?",
}
CHECK_ORDER = list(QUESTIONS)
MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _shared(name):
    return load_params()["_shared"][name]["value"]


def season_months(start, end):
    """Months from start to end, wrapping over December: (9, 7) -> [9, 10, 11, 12, 1, ..., 7].
    m % 12 + 1 moves to the next month and turns 12 into 1."""
    out, m = [], start
    while True:
        out.append(m)
        if m == end or len(out) > 12:
            return out
        m = m % 12 + 1


def crop_season(crop):
    """Growth-season months of the crop (override in crop_params.json, else sowing start -> harvest end)."""
    return list(crop.get("season_months") or season_months(crop["sowing_start_month"], crop["harvest_end_month"]))


def frost_sensitive(crop):
    """Annual crops with a frost-free requirement are killed by frost: count only the frost-free window."""
    months = crop_season(crop)
    return crop.get("min_frost_free_days") is not None and not crop.get("perennial") and months[-1] >= months[0]


def gdd_daily(tmax, tmin, tmean, base, method):
    """Daily growing degree-days. capped_10_30 = the US 86/50 method (both temperatures clipped to 10-30 degC)."""
    if method == "capped_10_30":
        hi, lo = np.clip(tmax, 10, 30), np.clip(tmin, 10, 30)
        return (hi + lo) / 2 - 10
    return np.clip(tmean - base, 0, None)


def site_climate(df):
    """Location stats that do not depend on the crop: winter extreme minimum, winter chill, summer rain."""
    tmin = df["T2M_MIN"]
    tmean = df["T2M"] if "T2M" in df else (df["T2M_MAX"] + df["T2M_MIN"]) / 2
    # Winter = July to June, labelled by the year it starts; a winter needs 90 % valid days.
    wy = np.where(df.index.month >= 7, df.index.year, df.index.year - 1)
    g = pd.DataFrame({"tmin": tmin.to_numpy(), "wy": wy}, index=df.index)
    ok = g.groupby("wy")["tmin"].agg(lambda s: s.notna().sum() >= 330)
    ext = g.groupby("wy")["tmin"].min()[ok]
    oct_mar = df.index.month.isin([10, 11, 12, 1, 2, 3])
    v = pd.DataFrame({"chill": ((tmean >= 0) & (tmean <= 10)).to_numpy() & oct_mar, "wy": wy, "ok": oct_mar})
    vern = v[v["wy"].isin(ext.index)].groupby("wy")["chill"].sum()
    p = df["PRECTOTCORR"]
    summer = p[p.index.month.isin([6, 7, 8])]
    sy = summer.groupby(summer.index.year).agg(["sum", "count"])
    sy = sy[sy["count"] >= 85]["sum"]
    return {"ext_min_c": float(ext.mean()) if len(ext) else None, "winters": int(len(ext)),
            "vern_days": float(vern.mean()) if len(vern) else None,
            "summer_rain_mm": float(sy.mean()) if len(sy) else None}


def season_climate(df, et0, crop):
    """Mean per complete season of the quantities the checks need.

    Vectorised per season: every day gets a season id (the year the season starts). Seasons that start
    before the series or end after it are dropped, as are seasons with < 90 % valid Tmax.
    """
    base = crop.get("gdd_base_c")
    base = 10.0 if base is None else base          # 0 degC is a real base (wheat, barley), not "missing"
    method = crop.get("gdd_method", "simple")
    topt, fail = crop.get("t_opt_max_c"), crop.get("heat_fail_c")
    months_list = crop_season(crop)
    s, e = months_list[0], months_list[-1]
    sensitive = frost_sensitive(crop)
    kill = _shared("killing_freeze_c")
    cap = _shared("stored_soil_water_cap_mm")
    idx = df.index
    months, years = idx.month.to_numpy(), idx.year.to_numpy()
    in_season = np.isin(months, months_list)
    wraps = e < s                                          # winter crop: season crosses New Year
    # Season id = the year the season STARTS. For a Sep-Jul wheat season, March 2020 belongs to the
    # season that started in 2019, so we subtract 1 for the months before the start month.
    sid = np.where(wraps & (months < s), years - 1, years)
    # The crop uses water until it matures, i.e. until the harvest window OPENS (corn Apr-Sep, not Apr-Nov);
    # heat is counted until the window closes (the latest it can still mature).
    # Perennials (alfalfa, orchards) keep transpiring after the first harvest: their whole season counts.
    water_months = (months_list if crop.get("season_months") or crop.get("perennial")
                    else season_months(s, crop.get("harvest_start_month") or e))
    in_water = np.isin(months, water_months)
    first, last = idx[0], idx[-1]
    tmax = df["T2M_MAX"].to_numpy(float)
    tmin = df["T2M_MIN"].to_numpy(float)
    tmean = df["T2M"].to_numpy(float) if "T2M" in df else (tmax + tmin) / 2
    rain = df["PRECTOTCORR"].to_numpy(float)
    et = np.asarray(et0, float)
    gdd_d = gdd_daily(tmax, tmin, tmean, base, method)
    monthly = pd.DataFrame({"p": rain, "et0": et, "t": tmean}, index=idx).resample("MS").agg(
        {"p": "sum", "et0": "sum", "t": "mean"})
    rows = []
    for y in np.unique(sid[in_season]):
        start = pd.Timestamp(year=int(y), month=s, day=1)
        end = pd.Timestamp(year=int(y) + (1 if wraps else 0), month=e, day=1) + pd.offsets.MonthEnd(0)
        if start < first or end > last:
            continue
        m = in_season & (sid == y)
        if np.mean(~np.isnan(tmax[m])) < 0.9:
            continue
        if sensitive:
            # The crop can only be in the field after this year's last spring frost and before the
            # first hard freeze (POWER 2 m air temperature over the MERRA-2 cell).
            yr = years == y
            spring = np.flatnonzero(yr & (months <= 6) & (tmin <= 0))
            autumn = np.flatnonzero(yr & (months >= 7) & (tmin <= kill))
            lo = spring[-1] + 1 if spring.size else 0
            hi = autumn[0] if autumn.size else len(idx)
            pos = np.arange(len(idx))
            m = m & (pos >= lo) & (pos < hi)
        # Soil water stored before the season: surplus months (rain > ET0) of the 6 months before it.
        pre = monthly.loc[start - pd.DateOffset(months=6): start - pd.DateOffset(days=1)]
        stored = float(np.clip((pre["p"] - pre["et0"]).clip(lower=0).sum(), 0, cap)) if len(pre) == 6 else 0.0
        mon = monthly.loc[start:end]
        mw = m & in_water
        rows.append({
            "rain_mm": np.nansum(rain[mw]),
            "et0_mm": np.nansum(et[mw]),
            "days": int(mw.sum()),
            "stored_mm": stored,
            "gdd": np.nansum(gdd_d[m]),
            "above_opt_days": int(np.sum(tmax[m] > topt)) if topt is not None else None,
            "heat_days": int(np.sum(tmax[m] >= fail)) if fail is not None else None,
            "frost_days": int(np.sum(tmin[in_season & (sid == y)] <= 0)),
            "hottest_month_t": float(mon["t"].max()) if len(mon) else None,
        })
    if not rows:
        return None
    t = pd.DataFrame(rows)
    return {k: (float(t[k].mean()) if t[k].notna().any() else None) for k in t.columns} | {"seasons": len(t)}


def _status(value, ok, marginal, higher_is_better=True):
    """Turn a number into ok / marginal / limit using two thresholds.
    Example (higher is better, ok=1.10, marginal=1.0): 1.2 -> ok, 1.05 -> marginal, 0.9 -> limit."""
    if value is None:
        return "n/a"
    if higher_is_better:
        return "ok" if value >= ok else "marginal" if value >= marginal else "limit"
    return "ok" if value < ok else "marginal" if value <= marginal else "limit"


def _doy(mmdd):
    return pd.Timestamp(f"2001-{mmdd}").day_of_year if mmdd else None


def safe_sowing(crop, last_frost_p90):
    """Earliest sowing date with frost over in 9 years out of 10 vs the crop's sowing window."""
    s, e = crop.get("sowing_start_month"), crop.get("sowing_end_month")
    if crop.get("min_frost_free_days") is None:
        return {"status": "n/a", "safe_from": None, "window": [s, e],
                "note": "Not applicable (frost-tolerant, overwintering or perennial crop)."}
    if not last_frost_p90:
        return {"status": "ok", "safe_from": None, "window": [s, e], "note": "No spring frost in the series."}
    m, d = (int(x) for x in last_frost_p90.split("-"))
    status = "ok" if m < s else "marginal" if m <= e else "limit"
    return {"status": status, "safe_from": f"{m:02d}-{d:02d}", "window": [s, e],
            "note": "safe_from = last spring frost (Tmin <= 0 degC) exceeded only 1 year in 10 (P90)."}


def checks(sc, site, crop, frost_free_median, irrigation_pct=0.0, last_frost_p90=None):
    """Screening checks for one season climate `sc` (from season_climate) and site climate `site`."""
    if sc is None:
        return None
    out = {}
    # Heat to mature
    gdd_req = crop.get("gdd_required")
    ratio = sc["gdd"] / gdd_req if gdd_req else None
    out["gdd"] = {"available": r(sc["gdd"], 0), "required": gdd_req, "base_c": crop.get("gdd_base_c"),
                  "method": crop.get("gdd_method", "simple"),
                  "pct_of_required": r(ratio * 100, 0) if ratio else None, "status": _status(ratio, 1.10, 1.0)}
    # Water (FAO-56 crop need, FAO-33 yield response)
    kc, ky = crop.get("kc_avg"), crop.get("ky")
    need = sc["et0_mm"] * kc + (crop.get("percolation_mm_day") or 0) * sc["days"] if kc else None
    supply = sc["rain_mm"] + sc["stored_mm"]
    short = max(0.0, need - supply) if need else None
    covered = short * irrigation_pct / 100 if short is not None else None
    cover = (supply + (covered or 0)) / need if need else None
    loss = ky * (1 - min(1.0, cover)) * 100 if (cover is not None and ky) else None
    if loss is None:
        wst = "n/a"
    elif cover < _shared("water_cover_limit_pct") / 100:   # FAO-33 is linear only for moderate deficits
        wst = "limit"
    else:
        wst = _status(loss, _shared("water_loss_ok_pct"), _shared("water_loss_limit_pct"), False)
    out["water"] = {"season_rain_mm": r(sc["rain_mm"], 0), "stored_soil_water_mm": r(sc["stored_mm"], 0),
                    "crop_need_mm": r(need, 0), "kc": kc, "ky": ky, "shortfall_mm": r(short, 0),
                    "irrigation_covered_mm": r(covered, 0), "cover_pct": r(cover * 100, 0) if cover is not None else None,
                    "expected_loss_pct": r(loss, 0), "status": wst}
    # Heat at flowering (never limiting alone)
    fail = crop.get("heat_fail_c")
    if fail is not None:
        hd = sc["heat_days"]
        out["heat"] = {"stress_days": r(hd, 1), "stress_threshold_c": fail, "t_opt_max_c": crop.get("t_opt_max_c"),
                       "days_above_topt": r(sc["above_opt_days"], 1),
                       "status": "ok" if hd < _shared("heat_days_marginal") else "marginal"}
    cs = crop.get("cool_season")
    if cs:
        t = sc["hottest_month_t"]
        out["cool_season"] = {"hottest_month_mean_c": r(t, 1), "ok_max_c": cs["ok_max_c"], "limit_max_c": cs["limit_max_c"],
                              "status": _status(t, cs["ok_max_c"], cs["limit_max_c"], False) if t is not None else "n/a"}
    # Frost-free season and sowing date
    min_ff = crop.get("min_frost_free_days")
    if min_ff is not None:
        margin = frost_free_median - min_ff if frost_free_median is not None else None
        out["frost_free"] = {"median_days": r(frost_free_median, 0), "crop_min_days": min_ff, "margin_days": r(margin, 0),
                             "status": _status(margin, 15, 0) if margin is not None else "n/a"}
        out["safe_sowing"] = safe_sowing(crop, last_frost_p90)
    else:
        out["frost_free"] = {"status": "n/a", "note": "Not applicable (frost-tolerant, overwintering or perennial crop)."}
        out["safe_sowing"] = safe_sowing(crop, last_frost_p90)
    # Winter survival (USDA hardiness-zone variable)
    wh = crop.get("winter_hardiness")
    if wh:
        x = site["ext_min_c"]
        out["winter_cold"] = {"mean_extreme_min_c": r(x, 1), "ok_min_c": wh["ok_min_c"], "limit_min_c": wh["limit_min_c"],
                              "status": _status(x, wh["ok_min_c"], wh["limit_min_c"]) if x is not None else "n/a"}
    vz = crop.get("vernalization")
    if vz:
        x = site["vern_days"]
        out["vernalization"] = {"chill_days": r(x, 0), "ok_days": vz["ok_days"], "limit_days": vz["limit_days"],
                                "status": _status(x, vz["ok_days"], vz["limit_days"]) if x is not None else "n/a"}
    hs = crop.get("humid_summer")
    if hs:
        rain, ext = site["summer_rain_mm"], site["ext_min_c"]
        if hs["rule"] == "dry_summer":
            st = _status(rain, hs["ok_max_mm"], hs["limit_max_mm"], False) if rain is not None else "n/a"
        elif hs["rule"] == "humid_heat":   # hot AND humid summer: tight at most
            t = sc["hottest_month_t"]
            st = "n/a" if rain is None or t is None else (
                "marginal" if t >= hs["hottest_month_c"] and rain > hs["summer_rain_mm"] else "ok")
        else:   # pierce: mild winter AND humid summer
            st = "n/a" if rain is None or ext is None else (
                "limit" if ext > hs["ext_min_warmer_than_c"] and rain > hs["summer_rain_mm"] else
                "marginal" if ext > hs["marginal_warmer_than_c"] and rain > hs["marginal_summer_rain_mm"] else "ok")
        out["humid_summer"] = {"rule": hs["rule"], "summer_rain_mm": r(rain, 0), "mean_extreme_min_c": r(ext, 1),
                               "hottest_month_mean_c": r(sc["hottest_month_t"], 1), "status": st}
    bf = crop.get("bloom_frost")
    if bf:
        d = _doy(last_frost_p90)
        st = "ok" if d is None or d < _doy(bf["ok_before"]) else "marginal" if d <= _doy(bf["limit_after"]) else "limit"
        out["bloom_frost"] = {"last_frost_p90": last_frost_p90, "ok_before": bf["ok_before"],
                              "limit_after": bf["limit_after"], "status": st}
    out["frost_days_in_season"] = r(sc["frost_days"], 1)
    out["seasons"] = sc["seasons"]
    return out


def _mmdd(s):
    return f"{MONTH[int(s[:2]) - 1]} {int(s[3:])}" if s else "none"


def _detail(k, b, s):
    """Base -> Scenario numbers of one check, in plain words."""
    if k == "gdd":
        meth = " (86/50 caps)" if b["method"] == "capped_10_30" else ""
        return (f"Growing degree-days in its frost-free season: {b['available']:.0f} → {s['available']:.0f} "
                f"(needs {s['required']:.0f}, base {s['base_c']:g} °C{meth})")
    if k == "water":
        txt = (f"Rain {b['season_rain_mm']:.0f} → {s['season_rain_mm']:.0f} mm + stored soil water {s['stored_soil_water_mm']:.0f} mm "
               f"vs need {b['crop_need_mm']:.0f} → {s['crop_need_mm']:.0f} mm (Kc {s['kc']:g} × ET0); expected loss "
               f"{b['expected_loss_pct']:.0f} % → {s['expected_loss_pct']:.0f} % (Ky {s['ky']:g})")
        if s.get("irrigation_covered_mm"):
            txt += f" · hypothetical irrigation adds {s['irrigation_covered_mm']:.0f} mm"
        return txt
    if k == "heat":
        return (f"Days with Tmax ≥ {s['stress_threshold_c']:g} °C (its flowering failure temperature) in season: "
                f"{b['stress_days']:.1f} → {s['stress_days']:.1f}")
    if k == "cool_season":
        return (f"Hottest season month averages {b['hottest_month_mean_c']:.1f} → {s['hottest_month_mean_c']:.1f} °C "
                f"(ok ≤ {s['ok_max_c']:g}, limit > {s['limit_max_c']:g})")
    if k == "frost_free":
        if b.get("note"):
            return b["note"]
        return f"{b['median_days']:.0f} → {s['median_days']:.0f} days (needs {s['crop_min_days']:.0f})"
    if k == "safe_sowing":
        if b["status"] == "n/a":
            return b["note"]
        w = b["window"]
        return (f"Frost is over 9 years in 10 from {_mmdd(b['safe_from'])} → {_mmdd(s['safe_from'])}; "
                f"sowing window {MONTH[w[0] - 1]}–{MONTH[w[1] - 1]}")
    if k == "winter_cold":
        return (f"Average yearly coldest night {b['mean_extreme_min_c']:.1f} → {s['mean_extreme_min_c']:.1f} °C "
                f"(ok ≥ {s['ok_min_c']:g}, limit < {s['limit_min_c']:g}; USDA hardiness-zone variable)")
    if k == "vernalization":
        return (f"Chilling days (mean 0–10 °C, Oct–Mar): {b['chill_days']:.0f} → {s['chill_days']:.0f} "
                f"(ok ≥ {s['ok_days']}, limit < {s['limit_days']})")
    if k == "humid_summer":
        if b["rule"] == "dry_summer":
            return f"June–August rain {b['summer_rain_mm']:.0f} → {s['summer_rain_mm']:.0f} mm (needs a dry summer)"
        if b["rule"] == "humid_heat":
            return (f"Hottest month {b['hottest_month_mean_c']:.1f} → {s['hottest_month_mean_c']:.1f} °C mean with "
                    f"{b['summer_rain_mm']:.0f} mm of June–August rain: stands thin out in hot, humid summers")
        return (f"Coldest night {b['mean_extreme_min_c']:.1f} → {s['mean_extreme_min_c']:.1f} °C and June–August rain "
                f"{b['summer_rain_mm']:.0f} mm: mild, humid climates favour Pierce's disease")
    if k == "bloom_frost":
        return (f"Last spring frost (1 year in 10) {_mmdd(b['last_frost_p90'])} → {_mmdd(s['last_frost_p90'])}; "
                f"bloom Feb–Mar")
    return ""


def _plain_one(k, c, name):
    """What one check means, in everyday words, for one side (base or scenario). No jargon, few numbers."""
    st = c.get("status")
    if k == "gdd":
        return {"ok": f"There are enough warm days for {name} to ripen, with time to spare.",
                "marginal": f"There are only just enough warm days for {name} to ripen: choose an early, short-cycle variety.",
                "limit": f"There are not enough warm days for {name} to ripen before the cold comes back."}.get(st)
    if k == "water":
        loss = c.get("expected_loss_pct")
        irr = " counting the irrigation" if c.get("irrigation_covered_mm") else ""
        return {"ok": f"In a normal year the rain{irr}, plus the water kept in the soil, gives {name} what it needs.",
                "marginal": f"The rain{irr} falls short: expect a harvest about {loss:.0f} % smaller than with enough water, "
                            "unless you irrigate." if loss is not None else None,
                "limit": f"There is far too little rain{irr} for {name}: without irrigation it is not worth sowing."}.get(st)
    if k == "heat":
        n = c.get("stress_days") or 0
        return {"ok": "Very hot days are rare while it flowers: heat is not a problem.",
                "marginal": f"About {n:.0f} very hot days a season (over {c['stress_threshold_c']:g} °C) while it flowers: "
                            "some flowers fail and the harvest can be smaller in hot years."}.get(st)
    if k == "cool_season":
        return {"ok": "Summers are cool enough for this cool-climate crop.",
                "marginal": "Summers are rather warm for this cool-climate crop: yield and quality can drop.",
                "limit": "Summers are too hot here for this cool-climate crop: it would have to be grown in winter instead."}.get(st)
    if k == "frost_free":
        return {"ok": "The time between the last spring frost and the first autumn frost is long enough.",
                "marginal": "The frost-free time is only just long enough: sow as early as frost allows.",
                "limit": "The frost-free time is too short: frost would catch it before harvest.",
                "n/a": "Light frost does not harm this crop much."}.get(st)
    if k == "safe_sowing":
        sf = c.get("safe_from")
        return {"ok": "Frosts are usually over before its sowing time begins." if not sf else
                      f"Frosts are over (9 years in 10) by {_mmdd(sf)}, before its sowing time begins.",
                "marginal": f"Wait until after {_mmdd(sf)} to sow: before that a frost is still possible 1 year in 10.",
                "limit": "Frost risk lasts beyond its whole sowing time.",
                "n/a": "No frost-free sowing date needed (frost-tolerant, winter or perennial crop)."}.get(st)
    if k == "winter_cold":
        return {"ok": "Winters are mild enough for it to survive.",
                "marginal": "Hard winters can damage it or kill it in some years.",
                "limit": "Winters are too cold here: it would not survive."}.get(st)
    if k == "vernalization":
        return {"ok": "Winters are cold enough for it to flower in spring (it needs a cold spell).",
                "marginal": "Winters are a bit mild: choose a variety that needs little cold to flower.",
                "limit": "Winters are too warm: without a cold spell it will not flower."}.get(st)
    if k == "humid_summer":
        if c.get("rule") == "dry_summer":
            return {"ok": "Summers are dry, as it likes.", "marginal": "Summers are rather wet: more fungal disease.",
                    "limit": "Summers are too wet: diseases and rain at harvest would ruin it."}.get(st)
        if c.get("rule") == "humid_heat":
            return {"ok": "Summers are not too hot and humid for it.",
                    "marginal": "Hot, humid summers: the plants thin out in 1-2 years from root diseases."}.get(st)
        return {"ok": "The climate does not favour the bacterial disease that kills vines in warm, humid places.",
                "marginal": "Mild winters and humid summers: risk of Pierce's disease, a bacterium that kills vines.",
                "limit": "Mild winters and humid summers: Pierce's disease would kill the vines (only muscadine grapes "
                         "grow here)."}.get(st)
    if k == "bloom_frost":
        return {"ok": "Frost is usually over before it flowers.",
                "marginal": "Late frosts can hit the flowers in some years.",
                "limit": "Frosts often hit the flowers: the harvest would be lost often."}.get(st)
    return None


def plain(k, b, s, name):
    """Plain-language meaning of one check; mentions today's situation when the scenario changes it."""
    now, scen = _plain_one(k, b, name), _plain_one(k, s, name)
    if scen and b.get("status") != s.get("status") and now:
        return f"In this scenario {scen[0].lower()}{scen[1:]} (Today {now[0].lower()}{now[1:]})"
    return scen or now or ""


def crop_effect(crop, df_base, et0_base, df_scen, et0_scen, ff_base, ff_scen, irrigation_pct,
                lsf_base=None, lsf_scen=None):
    # Same calculation on the real series (base) and on the perturbed series (scenario).
    sb = season_climate(df_base, et0_base, crop)
    ss = season_climate(df_scen, et0_scen, crop)
    if sb is None or ss is None:
        return None
    site_b = site_climate(df_base)
    site_s = site_b if df_scen is df_base else site_climate(df_scen)
    base = checks(sb, site_b, crop, ff_base, last_frost_p90=lsf_base)
    scen = checks(ss, site_s, crop, ff_scen, irrigation_pct, last_frost_p90=lsf_scen)
    rows = []
    for k in CHECK_ORDER:
        if k not in base or (base[k]["status"] == "n/a" and k not in ("frost_free", "safe_sowing")):
            continue
        try:
            detail = _detail(k, base[k], scen[k])
        except (TypeError, ValueError, KeyError):      # a missing number must never break the page
            detail = "Not enough data for the numbers of this check."
        try:
            meaning = plain(k, base[k], scen[k], crop["name_en"].lower())
        except (TypeError, ValueError, KeyError):
            meaning = ""
        rows.append({"key": k, "question": QUESTIONS[k], "base": base[k]["status"], "scenario": scen[k]["status"],
                     "plain": meaning, "detail": detail})
    months = crop_season(crop)
    return {
        "crop_id": crop["id"], "crop": crop["name_en"],
        "season": {"months": months,
                   "sowing": [crop["sowing_start_month"], crop["sowing_end_month"]],
                   "harvest": [crop["harvest_start_month"], crop["harvest_end_month"]],
                   "frost_free_window_only": frost_sensitive(crop)},
        "baseline": base, "scenario": scen, "rows": rows,
        "explanation": _explain(crop, base, scen),
        "rules": {k: RULES[k] for k in CHECK_ORDER if k in base},
        "corrections": crop.get("corrections", []),
        "assumptions": [
            "Crop requirements: team catalogue (backend/catalog/crops_us.csv) plus sourced parameters and documented "
            "corrections in backend/catalog/crop_params.json (FAO-56, FAO-33, Hatfield et al. 2011, USDA zones).",
            "Requirements are minimums for the earliest commercial cultivars, checked against 10 US producing regions "
            "(scripts/validate_crops.py).",
            "Season = catalogue sowing-start to harvest-end months (or the growth season); frost-sensitive annuals only "
            "count the days between that year's last spring frost and first hard freeze. Averaged over every season "
            "of the 10-year series.",
            "Climate is NASA POWER over a ~50 km MERRA-2 cell: local frost hollows, valley heat and extremes are smoothed.",
            "Screening checks only: the yield loss shown is the FAO-33 water response, not a yield forecast.",
        ],
        "data_type": "derived + hypothetical",
    }


def _explain(crop, b, s):
    name = crop["name_en"].lower()
    out = []
    g0, g1 = b["gdd"], s["gdd"]
    if g0["pct_of_required"] is not None:
        out.append(f"Heat accumulation for {name}: {g0['available']:.0f} → {g1['available']:.0f} growing degree-days "
                   f"in its season ({g1['pct_of_required']:.0f} % of the {g1['required']:.0f} it needs).")
    w0, w1 = b["water"], s["water"]
    if w0.get("expected_loss_pct") is not None:
        txt = (f"Water: rain and stored soil water cover {w0['cover_pct']:.0f} % of its need now and {w1['cover_pct']:.0f} % "
               f"in the scenario (need {w0['crop_need_mm']:.0f} → {w1['crop_need_mm']:.0f} mm); FAO-33 expected loss "
               f"{w0['expected_loss_pct']:.0f} % → {w1['expected_loss_pct']:.0f} %")
        if w1["irrigation_covered_mm"]:
            txt += f", including {w1['irrigation_covered_mm']:.0f} mm of hypothetical irrigation"
        out.append(txt + ".")
    if "heat" in b:
        h0, h1 = b["heat"], s["heat"]
        out.append(f"Days at or above its flowering failure temperature ({h1['stress_threshold_c']:g} °C): "
                   f"{h0['stress_days']:.1f} → {h1['stress_days']:.1f} per season.")
    if "cool_season" in b:
        out.append(f"Hottest season month: {b['cool_season']['hottest_month_mean_c']:.1f} → "
                   f"{s['cool_season']['hottest_month_mean_c']:.1f} °C mean.")
    f0, f1 = b["frost_free"], s["frost_free"]
    if f0.get("margin_days") is not None:
        out.append(f"Frost-free season {f0['median_days']:.0f} → {f1['median_days']:.0f} days "
                   f"(it needs at least {f1['crop_min_days']:.0f}).")
    if "winter_cold" in b:
        out.append(f"Average yearly coldest night {b['winter_cold']['mean_extreme_min_c']:.1f} → "
                   f"{s['winter_cold']['mean_extreme_min_c']:.1f} °C.")
    return out
