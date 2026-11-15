"""Geometry validation, point buffering, area and cache hashing.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
No projection library: parcels are at most 1,000 ha, so a local equirectangular projection around
the centroid is accurate to well under 1 % for area and buffering.
"""
import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import mapping, shape
from shapely.validation import explain_validity

from . import config

R_EARTH = 6371008.8


class GeometryError(ValueError):
    """Raised for bad input. `code` is a stable string the frontend can translate (e.g. GEOMETRY_TOO_LARGE);
    api.py turns it into an HTTP 422 response."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Parcel:
    """The cleaned-up parcel that every other module receives (instead of raw user GeoJSON)."""
    geojson: dict                 # normalised Polygon/MultiPolygon, WGS84 [lon, lat]
    input_type: str
    area_ha: float
    centroid: tuple               # (lon, lat)
    hemisphere: str
    warnings: list = field(default_factory=list)


def _to_local(lon0, lat0):
    """Vectorised forward/inverse local equirectangular transforms for shapely.transform.

    Degrees are not metres, so we cannot buffer or measure area directly in lon/lat. Around the
    centroid we convert to metres: x = delta_lon (rad) * R * cos(lat0), y = delta_lat (rad) * R.
    The cos(lat0) factor is there because meridians get closer towards the poles.
    """
    k = math.cos(math.radians(lat0))

    def fwd_xy(c):
        return np.column_stack((np.radians(c[:, 0] - lon0) * R_EARTH * k,
                                np.radians(c[:, 1] - lat0) * R_EARTH))

    def inv_xy(c):
        return np.column_stack((lon0 + np.degrees(c[:, 0] / (R_EARTH * k)),
                                lat0 + np.degrees(c[:, 1] / R_EARTH)))

    return (lambda g: shapely.transform(g, fwd_xy)), (lambda g: shapely.transform(g, inv_xy))


def _count_vertices(geom):
    # A MultiPolygon has .geoms (a list of polygons); a single Polygon does not, so we wrap it in a list.
    polys = getattr(geom, "geoms", [geom])
    return sum(len(p.exterior.coords) + sum(len(i.coords) for i in p.interiors) for p in polys)


def prepare(geojson):
    """Validate a GeoJSON Point/Polygon/MultiPolygon/Feature and return a Parcel."""
    if not isinstance(geojson, dict):
        raise GeometryError("GEOMETRY_INVALID", "Geometry must be a GeoJSON object.")
    if geojson.get("type") == "FeatureCollection":
        feats = geojson.get("features") or []
        if len(feats) != 1:
            raise GeometryError("GEOMETRY_UNSUPPORTED_TYPE",
                                "A FeatureCollection must contain exactly one parcel feature.")
        geojson = feats[0]
    if geojson.get("type") == "Feature":
        geojson = geojson.get("geometry") or {}
    gtype = geojson.get("type")
    if gtype not in ("Point", "Polygon", "MultiPolygon"):
        raise GeometryError("GEOMETRY_UNSUPPORTED_TYPE",
                            f"Unsupported geometry type {gtype!r}; use Point, Polygon or MultiPolygon.")
    try:
        geom = shape(geojson)
    except Exception as e:
        raise GeometryError("GEOMETRY_INVALID", f"Cannot parse geometry: {e}")
    if geom.is_empty:
        raise GeometryError("GEOMETRY_INVALID", "Geometry is empty.")
    minx, miny, maxx, maxy = geom.bounds
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise GeometryError("GEOMETRY_OUT_OF_RANGE",
                            "Coordinates must be WGS84 [lon, lat] within valid ranges.")

    warnings = []
    c = geom.centroid
    fwd, inv = _to_local(c.x, c.y)   # fwd: degrees -> metres, inv: metres -> degrees
    if gtype == "Point":
        # A point has no area, so we draw a 50 m circle in metres and convert it back to degrees.
        local = fwd(geom).buffer(config.POINT_BUFFER_M, quad_segs=8)
        geom = inv(local)
        warnings.append({"code": "POINT_BUFFERED",
                         "message": f"Point input buffered to {config.POINT_BUFFER_M:g} m."})
    else:
        if _count_vertices(geom) > config.MAX_VERTICES:
            raise GeometryError("GEOMETRY_TOO_MANY_VERTICES",
                                f"More than {config.MAX_VERTICES} vertices; simplify the parcel.")
        if not geom.is_valid:
            raise GeometryError("GEOMETRY_INVALID",
                                f"Invalid geometry (e.g. self-intersection): {explain_validity(geom)}")
        local = fwd(geom)

    area_ha = local.area / 10_000
    if area_ha > config.MAX_AREA_HA:
        raise GeometryError("GEOMETRY_TOO_LARGE",
                            f"Parcel is {area_ha:.0f} ha; the limit is {config.MAX_AREA_HA:g} ha.")
    if area_ha <= 0:
        raise GeometryError("GEOMETRY_INVALID", "Parcel has zero area.")

    lon, lat = geom.centroid.x, geom.centroid.y
    return Parcel(
        geojson=_round(mapping(geom)),
        input_type=gtype,
        area_ha=round(area_ha, 2),
        centroid=(round(lon, 6), round(lat, 6)),
        hemisphere="north" if lat >= 0 else "south",
        warnings=warnings,
    )


def _round(obj, nd=6):
    # Recursively round every coordinate to 6 decimals (~0.1 m). Two clicks on the "same" field then
    # give the same numbers, so they also give the same cache key.
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    return obj


def cache_key(parcel, start_date, end_date):
    """SHA-256 of the normalised geometry + dates + contract version.

    sort_keys and compact separators make the JSON text deterministic, so identical requests
    always hash to the same 64-character key (used as a file name in the caches).
    """
    payload = json.dumps({"g": parcel.geojson, "s": start_date, "e": end_date,
                          "v": config.CONTRACT_VERSION}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
