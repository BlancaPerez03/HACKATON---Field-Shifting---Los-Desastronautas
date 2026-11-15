"""Previsión a 16 días con Open-Meteo para la pregunta "¿cuándo debería sembrar?".

API: https://open-meteo.com/en/docs  (sin clave para uso no comercial).
Es un complemento: NO es dato NASA y se etiqueta como "previsión".
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import OPEN_METEO_URL

DAILY = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
         "et0_fao_evapotranspiration"]
HOURLY = ["soil_temperature_6cm"]

# Requisitos de siembra ORIENTATIVOS (hipótesis). La persona 4 los sustituye
# por los de crops.json cuando estén con fuente.
DEFAULT_SOWING_RULES = {
    "tomate_industria": {"minSoilTempC": 10.0, "minAirTminC": 5.0, "maxRainMm3d": 25.0},
    "trigo":            {"minSoilTempC": 4.0,  "minAirTminC": -5.0, "maxRainMm3d": 25.0},
    "garbanzo":         {"minSoilTempC": 7.0,  "minAirTminC": -2.0, "maxRainMm3d": 25.0},
}


def fetch_forecast(lat, lon, tz, cache_dir="data/raw"):
    cache = Path(cache_dir) / f"openmeteo_{lat}_{lon}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    params = {"latitude": lat, "longitude": lon, "timezone": tz, "forecast_days": 16,
              "daily": ",".join(DAILY), "hourly": ",".join(HOURLY)}
    try:
        r = requests.get(OPEN_METEO_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        data["_downloadedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cache.write_text(json.dumps(data))
        return data, False
    except requests.RequestException as e:
        if cache.exists():
            print(f"AVISO: Open-Meteo no responde ({e}). Uso la caché (previsión antigua).")
            return json.loads(cache.read_text()), True
        return None, False


def sowing_windows(data, rules=DEFAULT_SOWING_RULES):
    """Para cada cultivo, días de los próximos 16 aptos para sembrar según reglas simples."""
    if data is None:
        return None
    d = data["daily"]
    days = d["time"]
    # Media diaria de temperatura del suelo a partir de los valores horarios.
    soil = {}
    for t, v in zip(data["hourly"]["time"], data["hourly"]["soil_temperature_6cm"]):
        if v is not None:
            soil.setdefault(t[:10], []).append(v)
    soil = {k: sum(v) / len(v) for k, v in soil.items()}

    out = {}
    for crop, r in rules.items():
        ok = []
        for i, day in enumerate(days):
            rain3 = sum(x or 0 for x in d["precipitation_sum"][i:i + 3])
            tmin = d["temperature_2m_min"][i]
            st = soil.get(day)
            reasons = []
            if st is None or st < r["minSoilTempC"]:
                reasons.append(f"suelo {st:.1f} °C < {r['minSoilTempC']} °C" if st is not None
                               else "sin dato de temperatura del suelo")
            if tmin is None or tmin < r["minAirTminC"]:
                reasons.append(f"mínima del aire {tmin} °C < {r['minAirTminC']} °C")
            if rain3 > r["maxRainMm3d"]:
                reasons.append(f"lluvia prevista en 3 días {rain3:.0f} mm")
            ok.append({"date": day, "suitable": not reasons, "blockers": reasons,
                       "soilTempC": round(st, 1) if st is not None else None})
        out[crop] = ok
    return {
        "source": "Open-Meteo (previsión, no observación)",
        "downloadedAt": data.get("_downloadedAt"),
        "rulesKind": "hipotesis",
        "days": out,
    }
