"""Contraste de lluvia: GPM IMERG (Earth Engine) frente a NASA POWER.

Opcional. Si no hay cuenta de Earth Engine, el resto del módulo funciona igual.

Preparación (una vez):
    pip install earthengine-api
    earthengine authenticate
    # proyecto de Google Cloud registrado para Earth Engine:
    export EE_PROJECT=tu-proyecto

IMERG mensual V07: ~0.1° (~10 km), desde 2000. Banda "precipitation" en mm/h (media del mes).
"""
import os

import pandas as pd

from config import GEE_IMERG_MONTHLY


def imerg_monthly(lat, lon, start_year, end_year, buffer_m=5000):
    import ee  # import local: solo falla quien use esta función sin la librería

    ee.Initialize(project=os.environ.get("EE_PROJECT"))
    region = ee.Geometry.Point([lon, lat]).buffer(buffer_m)
    col = (ee.ImageCollection(GEE_IMERG_MONTHLY)
           .filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01")
           .select("precipitation"))

    def to_feature(img):
        val = img.reduceRegion(ee.Reducer.mean(), region, scale=10000).get("precipitation")
        return ee.Feature(None, {"date": img.date().format("YYYY-MM"), "mmh": val})

    feats = col.map(to_feature).getInfo()["features"]
    df = pd.DataFrame([f["properties"] for f in feats]).dropna()
    df["date"] = pd.to_datetime(df["date"])
    hours = df["date"].dt.days_in_month * 24
    df["precipMm"] = df["mmh"] * hours
    return df.set_index("date")["precipMm"]


def compare_with_power(power_daily, imerg_month):
    """Climatología mensual de ambas fuentes y diferencia relativa."""
    p = power_daily["PRECTOTCORR"].resample("MS").sum(min_count=20)
    both = pd.DataFrame({"power": p, "imerg": imerg_month}).dropna()
    clim = both.groupby(both.index.month).mean()
    rows = []
    for m, r in clim.iterrows():
        diff = None if r["imerg"] == 0 else round((r["power"] - r["imerg"]) / r["imerg"] * 100)
        rows.append({"month": int(m), "powerMm": round(r["power"], 1),
                     "imergMm": round(r["imerg"], 1), "diffPct": diff})
    return {
        "source": f"GPM IMERG ({GEE_IMERG_MONTHLY}) vía Google Earth Engine",
        "months": rows,
        "note": "Dos estimaciones independientes de la lluvia. Si discrepan mucho en un mes, "
                "la incertidumbre de ese mes es alta y el motor debe bajar la confianza.",
    }
