"""Crop history from the USDA Cropland Data Layer through the CropScape web service (no login, no key).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Used when Earth Engine is not available. Service: GetCDLValue of
https://nassgeodata.gmu.edu/CropScapeService (George Mason University for USDA NASS). It returns the
CDL class of ONE 30 m pixel, so we sample the centroid and up to 4 interior points per year and
take the majority: a lighter estimate than the full pixel histogram computed with Earth Engine.
Coordinates must be in the CDL projection, NAD83 / Conus Albers (EPSG:5070), computed below
(Snyder 1987, Map Projections - A Working Manual, USGS PP 1395, eq. 14-1 to 14-6; GRS80).
"""
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

from .. import config
from ..contract import indicator, scale_note_for, warn
from .croptype import OutOfCoverage, in_conus
from .soil_sda import sample_points

URL = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLValue"
_A, _F = 6378137.0, 1 / 298.257222101
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)


def _q(phi):
    s = math.sin(phi)
    return (1 - _E2) * (s / (1 - _E2 * s * s) - (1 / (2 * _E)) * math.log((1 - _E * s) / (1 + _E * s)))


def _m(phi):
    s = math.sin(phi)
    return math.cos(phi) / math.sqrt(1 - _E2 * s * s)


_P1, _P2, _P0, _L0 = (math.radians(v) for v in (29.5, 45.5, 23.0, -96.0))
_N = (_m(_P1) ** 2 - _m(_P2) ** 2) / (_q(_P2) - _q(_P1))
_C = _m(_P1) ** 2 + _N * _q(_P1)
_RHO0 = _A * math.sqrt(_C - _N * _q(_P0)) / _N


def to_albers(lon, lat):
    """WGS84/NAD83 lon, lat (degrees) -> EPSG:5070 x, y (metres)."""
    rho = _A * math.sqrt(_C - _N * _q(math.radians(lat))) / _N
    theta = _N * (math.radians(lon) - _L0)
    return rho * math.sin(theta), _RHO0 - rho * math.cos(theta)


def _value(year, lon, lat):
    x, y = to_albers(lon, lat)
    resp = requests.get(URL, params={"year": year, "x": round(x, 1), "y": round(y, 1)}, timeout=12)
    resp.raise_for_status()
    # Body: <Result>{x: ..., y: ..., value: 1, category: "Corn", color: "#FFD400"}</Result>
    m = re.search(r'value:\s*(\d+),\s*category:\s*"([^"]*)"', resp.text)
    return (int(m.group(1)), m.group(2)) if m else None


def run(parcel, start, end):
    lon, lat = parcel.centroid
    if not in_conus(lon, lat):
        raise OutOfCoverage("USDA CDL covers the contiguous USA only.")
    y0, y1 = max(int(start[:4]), 2008), min(int(end[:4]), config.CDL_LAST_YEAR)
    pts = sample_points(parcel.geojson, n=2)          # centroid + 2 interior points: 27 requests for 9 years
    jobs = [(y, x, yy) for y in range(y0, y1 + 1) for (x, yy) in pts]
    with ThreadPoolExecutor(max_workers=10) as pool:
        vals = list(pool.map(lambda j: _safe(*j), jobs))
    rows = []
    for y in range(y0, y1 + 1):
        got = [v for (yy, _, _), v in zip(jobs, vals) if yy == y and v]
        if not got:
            continue
        cnt = Counter(got)
        rows.append({"year": y, "dominant": [{"code": code, "name": name, "fraction": round(n / len(got), 2)}
                                             for (code, name), n in cnt.most_common(3)]})
    if not rows:
        raise OutOfCoverage("CropScape returned no CDL values for this parcel.")
    warnings = [warn("SOURCE_DEPRECATED_FALLBACK", "Earth Engine is not configured: crop history comes from "
                     f"{len(pts)} sample points per year (USDA CropScape, no login) instead of every 30 m pixel.")]
    mixed = sum(1 for y in rows if y["dominant"][0]["fraction"] < 0.6)
    if mixed > len(rows) / 2:
        warnings.append(warn("MIXED_LAND_COVER"))
    return indicator(
        ids=["USDA/NASS/CDL via CropScape GetCDLValue"], provider="USDA NASS (CropScape, George Mason University)",
        nasa=False, citation_key="usda_cdl", data_type="satellite", resolution_m=30,
        scale_note=scale_note_for(parcel.area_ha, 30), unit="crop class",
        method=f"CDL class at {len(pts)} points inside the parcel per year (EPSG:5070); majority = dominant crop.",
        confidence="medium" if len(pts) >= 3 else "low",
        confidence_reason="Point samples of the CDL, whose accuracy varies by crop and state; the farmer must confirm "
                          "the current rotation.",
        warnings=warnings, years=rows, via="web_service",
    )


def _safe(year, lon, lat):
    for _ in range(2):                       # one retry: the service sometimes drops a request
        try:
            return _value(year, lon, lat)
        except (requests.RequestException, ValueError):
            continue
    return None
