"""Genera climate.json para la finca piloto.

Uso:
    python build_climate.py                    # usa caché si existe
    python build_climate.py --refresh          # fuerza descarga de POWER
    python build_climate.py --imerg            # añade contraste IMERG (Earth Engine)
    python build_climate.py --no-forecast      # sin Open-Meteo
    python build_climate.py --out ../../public/data/climate.json
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from config import FARM, PERIOD, THRESHOLDS
from indicators import (add_derived, dry_years, frost_dates, monthly_climatology,
                        trends)
from power import fetch_power


def build(refresh=False, imerg=False, forecast=True, cache_dir="data/raw"):
    lat, lon = FARM["lat"], FARM["lon"]
    df, meta = fetch_power(lat, lon, PERIOD["start"], PERIOD["end"], cache_dir, refresh)

    elev = FARM["elevation_m"] if FARM["elevation_m"] is not None else meta["elevation_m"]
    elev_src = "config (SRTM)" if FARM["elevation_m"] is not None else "NASA POWER (rejilla MERRA-2)"
    if elev is None:
        elev, elev_src = 0.0, "desconocida: se asume 0 m (efecto pequeño en ET0)"

    d = add_derived(df, lat, elev)
    trend, yearly = trends(d)
    missing = {c: int(df[c].isna().sum()) for c in df.columns}

    result = {
        # --- campos del contrato ---
        "source": "NASA POWER (power.larc.nasa.gov), comunidad AG, datos diarios",
        "downloadedAt": meta["downloadedAt"],
        "period": f"{PERIOD['start']}-{PERIOD['end']}",
        "months": monthly_climatology(d),
        # --- extras ---
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataType": "observado (reanálisis/satélite) + calculado",
        "farm": {"name": FARM["name"], "lat": lat, "lon": lon,
                 "elevationM": round(elev, 1), "elevationSource": elev_src},
        "spatialResolution": "~0.5° x 0.625° (~50 km): describe la comarca, no la parcela",
        "fromCache": meta["fromCache"],
        "missingDays": missing,
        "frost": frost_dates(d),
        "trends": trend,
        "dryYears": dry_years(yearly),
        "annual": {
            "precipMm": round(float(yearly["precipMm"].mean()), 0),
            "et0Mm": round(float(yearly["et0Mm"].mean()), 0),
            "waterBalanceMm": round(float((yearly["precipMm"] - yearly["et0Mm"]).mean()), 0),
        },
        "thresholds": THRESHOLDS,
        "methods": {
            "et0Mm": "FAO-56 Penman-Monteith diario; presión de vapor desde punto de rocío; G=0.",
            "waterBalanceMm": "Lluvia - ET0 del mes. Negativo = déficit que debe cubrir el riego "
                              "(para el cultivo real, multiplicar ET0 por su Kc).",
            "climatology": "Media entre años de cada mes; p10/p90 = año seco/húmedo de 1 en 10.",
        },
        "limitations": [
            "Resolución ~50 km: no distingue diferencias dentro de la finca.",
            "La lluvia de POWER es un producto modelado/corregido; contrastar con IMERG o CIMIS.",
            "En Fresno la mayor parte del agua del cultivo viene del riego, no de la lluvia.",
            "Umbrales marcados como 'hipotesis' deben validarse con UC ANR o un técnico local.",
        ],
    }

    if imerg:
        try:
            from gee_imerg import compare_with_power, imerg_monthly
            im = imerg_monthly(lat, lon, PERIOD["start"], PERIOD["end"])
            result["precipCrossCheck"] = compare_with_power(df, im)
        except Exception as e:  # GEE es opcional: nunca rompe la build
            result["precipCrossCheck"] = {"error": f"IMERG no disponible: {e}"}

    if forecast:
        from forecast import fetch_forecast, sowing_windows
        data, stale = fetch_forecast(lat, lon, FARM["timezone"], cache_dir)
        sw = sowing_windows(data)
        if sw:
            sw["stale"] = stale
        result["sowingForecast"] = sw

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--imerg", action="store_true")
    ap.add_argument("--no-forecast", action="store_true")
    ap.add_argument("--out", default="data/climate.json")
    a = ap.parse_args()

    res = build(a.refresh, a.imerg, not a.no_forecast)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"OK -> {out}  (POWER descargado: {res['downloadedAt']}, caché: {res['fromCache']})")


if __name__ == "__main__":
    main()
