"""Descarga de datos diarios de NASA POWER con caché local fechada.

API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
No requiere clave. Resolución de la rejilla meteorológica ~0.5° x 0.625° (MERRA-2), unos 50 km:
representa la comarca, no la parcela.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config import POWER_PARAMS, POWER_URL

FILL = -999.0


def _request(lat, lon, start, end, retries=3):
    params = {
        "parameters": ",".join(POWER_PARAMS),
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": f"{start}0101",
        "end": f"{end}1231",
        "format": "JSON",
        "time-standard": "LST",
    }
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(POWER_URL, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"NASA POWER no responde: {last}")


def fetch_power(lat, lon, start, end, cache_dir="data/raw", refresh=False):
    """Devuelve (DataFrame diario, metadatos). Usa la caché si la API falla."""
    cache = Path(cache_dir) / f"power_{lat}_{lon}_{start}_{end}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)

    payload, from_cache = None, False
    if refresh or not cache.exists():
        try:
            payload = _request(lat, lon, start, end)
            payload["_downloadedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cache.write_text(json.dumps(payload))
        except RuntimeError as e:
            if not cache.exists():
                raise
            print(f"AVISO: {e}. Uso la caché {cache}")
    if payload is None:
        payload = json.loads(cache.read_text())
        from_cache = True

    return parse_power(payload), {
        "downloadedAt": payload.get("_downloadedAt"),
        "fromCache": from_cache,
        "elevation_m": _elevation(payload),
        "cacheFile": str(cache),
    }


def _elevation(payload):
    try:
        return float(payload["geometry"]["coordinates"][2])
    except (KeyError, IndexError, TypeError):
        return None


def parse_power(payload):
    """Convierte la respuesta JSON de POWER en un DataFrame diario con NaN en los huecos."""
    p = payload["properties"]["parameter"]
    df = pd.DataFrame(p)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(FILL, np.nan).astype(float).sort_index()
    return df
