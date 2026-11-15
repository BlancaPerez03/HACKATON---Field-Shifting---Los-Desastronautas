"""Indicadores climáticos a partir de la serie diaria de POWER.

Todos los valores mensuales son climatologías: media del periodo de cada mes.
Ej.: precipMm de enero = media, entre años, de la lluvia total de enero.
"""
import numpy as np
import pandas as pd

from config import THRESHOLDS
from et0 import et0_pm


def T(name):
    return THRESHOLDS[name]["value"]


def add_derived(df, lat, elevation_m):
    """Añade ET0, días de helada/calor/lluvia intensa y grados-día a la serie diaria."""
    out = df.copy()
    out["ET0"] = et0_pm(
        out["T2M_MAX"], out["T2M_MIN"], out["ALLSKY_SFC_SW_DWN"], out["WS2M"],
        lat, out.index.dayofyear, elevation_m,
        tdew=out["T2MDEW"] if "T2MDEW" in out else None,
        rh_mean=out["RH2M"] if "T2MDEW" not in out else None,
    )
    # Si falta algún insumo de ET0 ese día, queda NaN (no inventamos).
    needed = ["T2M_MAX", "T2M_MIN", "ALLSKY_SFC_SW_DWN", "WS2M"]
    out.loc[out[needed].isna().any(axis=1), "ET0"] = np.nan

    out["frost"] = (out["T2M_MIN"] < T("frost_tmin_c")).astype(float)
    out["heat"] = (out["T2M_MAX"] >= T("heat_tmax_c")).astype(float)
    out["heavy"] = (out["PRECTOTCORR"] >= T("very_heavy_precip_mm")).astype(float)
    out["wet"] = (out["PRECTOTCORR"] >= T("wet_day_mm")).astype(float)
    for c, src in [("frost", "T2M_MIN"), ("heat", "T2M_MAX"),
                   ("heavy", "PRECTOTCORR"), ("wet", "PRECTOTCORR")]:
        out.loc[out[src].isna(), c] = np.nan

    tmax_c = out["T2M_MAX"].clip(upper=T("gdd_cap_c"))
    tmin_c = out["T2M_MIN"].clip(upper=T("gdd_cap_c"))
    out["GDD"] = ((tmax_c + tmin_c) / 2 - T("gdd_base_c")).clip(lower=0)
    return out


def monthly_climatology(d):
    """Tabla de 12 meses con el formato del contrato climate.json (+ campos extra)."""
    sums = d[["PRECTOTCORR", "ET0", "frost", "heat", "heavy", "wet", "GDD"]] \
        .resample("MS").sum(min_count=20)            # mes con <20 días válidos -> NaN
    means = d[["T2M_MAX", "T2M_MIN", "RH2M", "ALLSKY_SFC_SW_DWN"]].resample("MS").mean()
    m = sums.join(means)
    m["month"] = m.index.month
    m["balance"] = m["PRECTOTCORR"] - m["ET0"]
    clim = m.groupby("month")

    mean, p10, p90 = clim.mean(), clim.quantile(0.10), clim.quantile(0.90)
    rows = []
    for mo in range(1, 13):
        r = mean.loc[mo]
        rows.append({
            "month": mo,
            "precipMm": _r(r["PRECTOTCORR"]),
            "tMaxC": _r(r["T2M_MAX"]),
            "tMinC": _r(r["T2M_MIN"]),
            "frostDays": _r(r["frost"]),
            "heatDays": _r(r["heat"]),
            "et0Mm": _r(r["ET0"]),
            # --- extras (no rompen el contrato) ---
            "waterBalanceMm": _r(r["balance"]),
            "precipP10Mm": _r(p10.loc[mo, "PRECTOTCORR"]),
            "precipP90Mm": _r(p90.loc[mo, "PRECTOTCORR"]),
            "heavyRainDays": _r(r["heavy"], 2),
            "wetDays": _r(r["wet"]),
            "gdd": _r(r["GDD"], 0),
            "rhPct": _r(r["RH2M"], 0),
            "solarMJm2": _r(r["ALLSKY_SFC_SW_DWN"]),
            "yearsWithData": int(clim["PRECTOTCORR"].count().loc[mo]),
        })
    return rows


def frost_dates(d):
    """Última helada de primavera y primera de otoño (hemisferio norte), por año.

    Devuelve día del año mediano y percentil 90 (más tardía / más temprana con 1 año de cada 10).
    """
    frost = d["T2M_MIN"] < T("frost_tmin_c")
    last_spring, first_fall, years_no_frost = [], [], 0
    for y, g in frost.groupby(frost.index.year):
        spring = g[(g.index.month <= 7) & g]
        fall = g[(g.index.month >= 8) & g]
        if spring.empty:
            years_no_frost += 1
        else:
            last_spring.append(spring.index[-1].dayofyear)
        if not fall.empty:
            first_fall.append(fall.index[0].dayofyear)

    def stat(v, q):
        return int(np.percentile(v, q)) if v else None

    return {
        "lastSpringFrostDoyMedian": stat(last_spring, 50),
        "lastSpringFrostDoyP90": stat(last_spring, 90),     # 9 de cada 10 años ya no hiela
        "firstFallFrostDoyMedian": stat(first_fall, 50),
        "firstFallFrostDoyP10": stat(first_fall, 10),       # 1 de cada 10 años hiela antes
        "yearsWithoutSpringFrost": years_no_frost,
        "note": "Calculado con Tmin de POWER (~50 km). Las heladas por inversión en "
                "zonas bajas de la finca pueden ser más frecuentes: validar con estación CIMIS.",
    }


def trends(d):
    """Tendencia lineal por década (mínimos cuadrados) de variables anuales."""
    yearly = pd.DataFrame({
        "precipMm": d["PRECTOTCORR"].resample("YS").sum(min_count=330),
        "et0Mm": d["ET0"].resample("YS").sum(min_count=330),
        "tMaxC": d["T2M_MAX"].resample("YS").mean(),
        "tMinC": d["T2M_MIN"].resample("YS").mean(),
        "heatDays": d["heat"].resample("YS").sum(min_count=330),
        "frostDays": d["frost"].resample("YS").sum(min_count=330),
    })
    out = {}
    for c in yearly:
        s = yearly[c].dropna()
        if len(s) < 10:
            out[c] = None
            continue
        x = s.index.year.values.astype(float)
        slope = np.polyfit(x, s.values, 1)[0]
        out[c] = {"perDecade": _r(slope * 10, 2), "years": len(s),
                  "annualMean": _r(s.mean())}
    out["note"] = ("Tendencia descriptiva del periodo, sin test de significación ni "
                   "proyección futura. No es una predicción.")
    return out, yearly


def dry_years(yearly):
    """Años de lluvia por debajo del percentil 20: sirven como 'año seco típico' en el simulador."""
    s = yearly["precipMm"].dropna()
    thr = s.quantile(0.2)
    return {"p20AnnualPrecipMm": _r(thr),
            "years": [int(y.year) for y in s[s <= thr].index]}


def _r(x, nd=1):
    if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x):
        return None
    v = round(float(x), nd)
    return int(v) if nd == 0 else v
