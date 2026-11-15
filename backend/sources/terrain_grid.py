"""Per-pixel terrain grid for the risk zones: slope (deg) and TPI (m) on the native NASADEM grid.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

NASADEM is a 1 arc-second grid (~31 m N-S; E-W shrinks with latitude, ~23 m at 42 N). The grid
is sampled at 1 arc-second in EPSG:4326, aligned to whole arc-seconds, so the bbox returned is
the exact pixel-edge box. Slope is computed on the unclipped DEM (no edge artefacts).
TPI = elevation - focal mean of elevation within `radius_m` (circle): negative values are
hollows where cold air can pool. One getInfo per parcel; the result is cached on disk.
"""
import math

import numpy as np
import shapely
from shapely.geometry import shape

from .. import config
from ..gee_client import get_ee

ARCSEC = 1 / 3600
NODATA = -9999


def inside_mask(geojson, x0, y1, rows, cols):
    """1 where the pixel centre lies inside the parcel polygon, else 0 (exact, computed locally)."""
    geom = shape(geojson)
    # Pixel centres: column c is at x0 + (c + 0.5) pixels; rows go downwards from the north edge y1.
    xs = x0 + (np.arange(cols) + 0.5) * ARCSEC
    ys = y1 - (np.arange(rows) + 0.5) * ARCSEC
    gx, gy = np.meshgrid(xs, ys)
    return shapely.contains_xy(geom, gx.ravel(), gy.ravel()).astype(int).tolist()


def fetch(parcel, radius_m=150):
    ee = get_ee()
    lat = parcel.centroid[1]
    if not -56 <= lat <= 60:
        raise RuntimeError("OUT_OF_COVERAGE: terrain grid uses NASADEM (60N-56S) only.")
    coords = parcel.geojson["coordinates"]
    flat = [pt for ring in (coords if parcel.geojson["type"] == "Polygon" else [r for p in coords for r in p])
            for pt in ring]
    minx, maxx = min(p[0] for p in flat), max(p[0] for p in flat)
    miny, maxy = min(p[1] for p in flat), max(p[1] for p in flat)
    # Snap the parcel's bounding box outwards to whole arc-seconds so our grid lines up exactly with
    # NASADEM's native pixels (no resampling between two grids).
    x0, y1 = math.floor(minx / ARCSEC) * ARCSEC, math.ceil(maxy / ARCSEC) * ARCSEC
    cols = math.ceil((maxx - x0) / ARCSEC)
    rows = math.ceil((y1 - miny) / ARCSEC)
    x1, y0 = x0 + cols * ARCSEC, y1 - rows * ARCSEC

    dem = ee.Image(config.NASADEM).select("elevation")
    slope = ee.Terrain.slope(dem).rename("slope_deg")
    # TPI = my height minus the average height around me. Negative = I am lower than my neighbours.
    tpi = dem.subtract(dem.focalMean(radius_m, "circle", "meters")).rename("tpi_m")
    stack = slope.addBands(tpi).toFloat().reproject(
        crs="EPSG:4326", crsTransform=[ARCSEC, 0, x0, 0, -ARCSEC, y1])
    region = ee.Geometry.Rectangle([x0, y0, x1, y1], "EPSG:4326", False)
    arr = stack.sampleRectangle(region=region, defaultValue=NODATA).getInfo()["properties"]

    def flatten(band, nd):
        return [round(v, nd) if v != NODATA else None for row in arr[band] for v in row]

    s, t = flatten("slope_deg", 2), flatten("tpi_m", 2)
    rows_out, cols_out = len(arr["slope_deg"]), len(arr["slope_deg"][0])
    m = inside_mask(parcel.geojson, x0, y1, rows_out, cols_out)
    return {
        "bbox": [x0, y1 - rows_out * ARCSEC, x0 + cols_out * ARCSEC, y1],
        "rows": rows_out, "cols": cols_out, "nodata": None,
        "slope_deg": s, "tpi_m": t, "in_parcel": m,
        "tpi_radius_m": radius_m,
        "pixel_size": f"1 arc-second (~31 m N-S, ~{31 * math.cos(math.radians(lat)):.0f} m E-W here)",
        "source": {"ids": [config.NASADEM], "nasa": True, "data_type": "satellite", "resolution_m": 30},
        "method": "ee.Terrain.slope on the unclipped NASADEM; TPI = elevation minus its circular focal mean "
                  f"({radius_m} m). Sampled on the native 1 arc-second grid (nearest, no smoothing).",
    }
