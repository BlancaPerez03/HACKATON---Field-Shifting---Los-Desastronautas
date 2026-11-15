"""NASA POWER client (daily, point, AG community) and the agroclimate indicator.

AI-assisted: generated with an AI coding assistant (Claude), based on the team's climate module;
reviewed by the team.

API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- No key. A point returns the source's native resolution: MERRA-2 0.5 deg x 0.625 deg for
  meteorology, CERES 1 deg for solar. The cache is keyed by the MERRA-2 cell, so nearby parcels
  in the same cell do not repeat the request (POWER asks clients not to).
- Max 20 parameters per request. Fill value -999. Units are read from the response.
"""
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from .. import config, derived
from ..contract import indicator, r, warn

# If POWER ever returns radiation in kWh/m2/day instead of MJ/m2/day we multiply by 3.6.
UNIT_CONVERSIONS = {("ALLSKY_SFC_SW_DWN", "kW-hr/m^2/day"): 3.6}
# HTTP codes worth retrying: 429 = "too many requests", 5xx = temporary server problems.
RETRY_STATUS = {429, 500, 502, 503, 504}


class PowerError(RuntimeError):
    pass


def merra_cell(lat, lon):
    """Index of the MERRA-2 grid cell (0.5 deg lat x 0.625 deg lon) containing the point.

    Two parcels in the same cell get exactly the same POWER data, so we use (i, j) as the cache key
    and download each cell only once.
    """
    return int(round((lat + 90) / 0.5)), int(round((lon + 180) / 0.625))


def _request(lat, lon, start, end, retries=5):
    params = {"parameters": ",".join(config.POWER_PARAMS[:20]), "community": "AG",
              "latitude": round(lat, 4), "longitude": round(lon, 4),
              "start": start.replace("-", ""), "end": end.replace("-", ""),
              "format": "JSON", "time-standard": "LST"}
    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(config.POWER_URL, params=params, timeout=150)
            if resp.status_code in RETRY_STATUS:
                # Exponential backoff: wait 2, 4, 8, 16... seconds (or what the server asks in
                # its Retry-After header) before trying again, capped at 60 s.
                wait = float(resp.headers.get("Retry-After", 2 ** attempt * 2))
                last = f"HTTP {resp.status_code}"
                time.sleep(min(wait, 60))
                continue
            if resp.status_code >= 400:
                raise PowerError(f"POWER HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except requests.RequestException as e:
            last = str(e)
            time.sleep(2 ** attempt)
    raise PowerError(f"NASA POWER did not respond after {retries} attempts: {last}")


def cache_name(lat, lon, start, end):
    i, j = merra_cell(lat, lon)
    return f"cell_{i}_{j}_{start}_{end}.json"


def cell_bounds(lat, lon):
    """[west, south, east, north] of the MERRA-2 cell (0.5 deg x 0.625 deg) containing the point."""
    i, j = merra_cell(lat, lon)
    clat, clon = -90 + 0.5 * i, -180 + 0.625 * j
    return [clon - 0.3125, clat - 0.25, clon + 0.3125, clat + 0.25]


def fetch(lat, lon, start, end, refresh=False):
    """Return (daily DataFrame, meta). Dates are 'YYYY-MM-DD'."""
    i, j = merra_cell(lat, lon)
    cache = config.CACHE_DIR / "power" / cache_name(lat, lon, start, end)
    cache.parent.mkdir(parents=True, exist_ok=True)
    from_cache = cache.exists() and not refresh
    if from_cache:
        payload = json.loads(cache.read_text())
    else:
        payload = _request(lat, lon, start, end)
        payload["_downloaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cache.write_text(json.dumps(payload))
    df, units, unit_warnings = parse(payload)
    try:
        elev = float(payload["geometry"]["coordinates"][2])
    except (KeyError, IndexError, TypeError, ValueError):
        elev = None
    meta = {
        "downloaded_at": payload.get("_downloaded_at"),
        "from_cache": from_cache,
        "api_version": payload.get("header", {}).get("api", {}).get("version"),
        "sources": payload.get("header", {}).get("sources"),
        "grid_elevation_m": elev,
        "units": units,
        "unit_warnings": unit_warnings,
        "merra2_cell": [i, j],
    }
    return df, meta


def parse(payload):
    """POWER JSON -> (daily DataFrame with NaN gaps, units dict, warnings)."""
    # POWER marks missing days with -999. We replace that with NaN so pandas ignores those days
    # in sums and means instead of adding -999.
    fill = payload.get("header", {}).get("fill_value", -999.0)
    p = payload["properties"]["parameter"]   # {"T2M_MAX": {"20240101": 3.2, ...}, ...}
    df = pd.DataFrame(p)                     # one column per parameter, one row per day
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(fill, np.nan).astype(float).sort_index()
    units, warns = {}, []
    meta = payload.get("parameters", {})
    for col in list(df.columns):
        got = meta.get(col, {}).get("units")
        want = config.POWER_EXPECTED_UNITS.get(col)
        if got is None or want is None or got == want:
            units[col] = got or want
            continue
        factor = UNIT_CONVERSIONS.get((col, got))
        if factor:
            df[col] = df[col] * factor
            units[col] = want
        else:
            df = df.drop(columns=col)
            warns.append(f"{col}: unexpected unit {got!r} (expected {want!r}); dropped.")
    return df, units, warns


def run(parcel, start, end):
    """Build the `agroclimate_power` indicator for a parcel."""
    lon, lat = parcel.centroid
    df, meta = fetch(lat, lon, start, end)                 # 1) download (or read cache)
    elev = meta["grid_elevation_m"] if meta["grid_elevation_m"] is not None else 0.0
    clim = derived.climate_summary(df, lat, elev, parcel.hemisphere)   # 2) all climate indicators
    # 3) wrap everything with the traceability fields (source, data type, scale, warnings)

    warnings = [warn("ZONE_SCALE_DATA"), warn("FROST_AIR_TEMP_PROXY"), warn("EXTREMES_SMOOTHED")]
    if clim["et0"]["hargreaves_days"] > 0:
        warnings.append(warn("SOLAR_DATA_LAG",
                             f"{clim['et0']['hargreaves_days']} days lack radiation/wind/humidity; "
                             "Hargreaves ET0 was used for those days."))
    if clim["soil_wetness_index"] is None:
        warnings.append(warn("WETNESS_INDEX_FLAT"))
    else:
        warnings.append(warn("WETNESS_INDEX_NOT_VOLUMETRIC"))
    for w in meta["unit_warnings"]:
        warnings.append(warn("OUT_OF_COVERAGE", w))

    years = clim["years_complete"]
    conf = "high" if years >= 10 else "medium" if years >= 5 else "low"
    return indicator(
        ids=["NASA POWER Daily API, AG community"],
        provider="NASA LaRC POWER (MERRA-2 meteorology, CERES SYN1deg solar)",
        nasa=True, citation_key="nasa_power",
        data_type="reanalysis", resolution_m=55000, scale_note="zone",
        unit="see `units`",
        method=("Daily point request at the parcel centroid (native MERRA-2 cell). Derived: frost dates "
                "by agricultural year and hemisphere, frost/heat day counts, FAO-56 Penman-Monteith ET0 "
                "(Hargreaves-Samani where inputs are missing), monthly P - ET0, ETCCDI R95p/R20mm/Rx1day."),
        thresholds={k: config.THRESHOLDS[k] for k in
                    ("frost_tmin_c", "ground_frost_tmin_c", "heat_tmax_c", "wet_day_mm",
                     "very_heavy_precip_mm", "r95_percentile")},
        confidence=conf,
        confidence_reason=f"{years} complete years of daily data; values describe a ~50 x 60 km cell.",
        warnings=warnings,
        units=meta["units"],
        power_api_version=meta["api_version"],
        downloaded_at=meta["downloaded_at"],
        data_citation=(f"The data was obtained from the POWER Project's Daily "
                       f"{meta['api_version'] or '2.x.x'} version on "
                       f"{(meta['downloaded_at'] or '')[:10].replace('-', '/')}."),
        grid_elevation_m=r(meta["grid_elevation_m"], 1),
        merra2_cell_bounds=cell_bounds(lat, lon),
        missing_days={c: int(df[c].isna().sum()) for c in df.columns},
        **clim,
    )
