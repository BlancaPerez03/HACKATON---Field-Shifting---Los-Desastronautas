"""SMAP L4 root-zone soil moisture: monthly means, climatology and anomalies.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Catalog (verified 2026-11-14): NASA/SMAP/SPL4SMGP/008, band `sm_rootzone` (0-100 cm), volume
fraction 0-0.9, 3-hourly, 2015-03-31 ->, pixel 11 km in the band table (~9 km EASE-Grid 2.0).
SMAP L4 assimilates satellite brightness temperature into a land model -> data_type "model".
The value is read at the parcel centroid: the parcel is far smaller than one cell.
"""
from collections import defaultdict
from datetime import date

import numpy as np

from .. import config
from ..contract import indicator, r, warn
from ..gee_client import ee_geometry, get_ee

SMAP_START = "2015-04-01"


def anomalies(monthly):
    """Pure: [{"month": "YYYY-MM", "value"}] -> (climatology list, {YYYY-MM: anomaly})."""
    per = defaultdict(list)
    for x in monthly:
        if x["value"] is not None:
            per[int(x["month"][5:7])].append(x["value"])
    clim = {m: (float(np.mean(v)), len(v)) for m, v in per.items()}
    anom = {x["month"]: r(x["value"] - clim[int(x["month"][5:7])][0], 4)
            for x in monthly if x["value"] is not None}
    clim_list = [{"month": m, "mean": r(clim[m][0], 4), "years": clim[m][1]} for m in sorted(clim)]
    return clim_list, anom


def _pixel_footprint(ee, col, pt):
    """GeoJSON polygon of the SMAP grid cell that contains the centroid (None if it fails)."""
    try:
        proj = ee.Image(col.first()).projection()
        info = proj.getInfo()
        # The affine transform says where pixel (0, 0) is (ox, oy) and how big a pixel is (sx, sy).
        # We convert the centroid to the SMAP projection, find its column/row with integer division,
        # and rebuild that pixel's square, then convert it back to lon/lat for the map.
        sx, _, ox, _, sy, oy = info["transform"]
        x, y = pt.transform(proj, 1).coordinates().getInfo()
        col_i, row_i = (x - ox) // sx, (y - oy) // sy
        x0, y0 = ox + col_i * sx, oy + row_i * sy
        xs, ys = sorted([x0, x0 + sx]), sorted([y0, y0 + sy])
        rect = ee.Geometry.Rectangle([xs[0], ys[0], xs[1], ys[1]], proj, False)
        return rect.transform("EPSG:4326", 1).getInfo()
    except Exception:
        return None


def run(parcel, start, end):
    ee = get_ee()
    pt = ee_geometry(ee, parcel).centroid(1)
    s = max(start, SMAP_START)
    y0, m0 = int(s[:4]), int(s[5:7])
    n = (int(end[:4]) - y0) * 12 + int(end[5:7]) - m0 + 1
    col = ee.ImageCollection(config.SMAP_L4).select("sm_rootzone")
    origin = ee.Date(f"{y0}-{m0:02d}-01")

    # Server-side loop over months: for month i, average all 3-hourly images of that month and read
    # the value at the parcel centroid. ee.List.sequence(...).map() runs inside Google's servers.
    def month_value(i):
        d0 = origin.advance(i, "month")
        img = col.filterDate(d0, d0.advance(1, "month")).mean()
        v = img.reduceRegion(ee.Reducer.first(), pt, scale=11000).get("sm_rootzone")
        return ee.Feature(None, {"month": d0.format("YYYY-MM"), "value": v})

    feats = ee.FeatureCollection(ee.List.sequence(0, n - 1).map(month_value)).getInfo()["features"]
    footprint = _pixel_footprint(ee, col, pt)
    monthly = [{"month": f["properties"]["month"], "value": r(f["properties"].get("value"), 4)}
               for f in feats]
    clim, anom = anomalies(monthly)
    warnings = [warn("ZONE_SCALE_DATA")]
    if start < SMAP_START:
        warnings.append(warn("OUT_OF_COVERAGE", f"SMAP L4 starts 2015-03-31; months before {SMAP_START} omitted."))
    years = min((c["years"] for c in clim), default=0)
    return indicator(
        ids=[config.SMAP_L4], provider="NASA GMAO / NSIDC", nasa=True, citation_key="smap_l4",
        data_type="model", resolution_m=11000, scale_note="zone",
        unit="m3/m3 (volume fraction), root zone 0-100 cm",
        method="Monthly mean of 3-hourly sm_rootzone at the parcel centroid; climatology = mean per calendar "
               "month over the request period; anomaly = month minus its climatology. Instrument outages "
               "(2019-06-19..07-23, 2022-08-06..09-20) are model-only.",
        confidence="medium" if years >= 5 else "low",
        confidence_reason=f"{years}+ years per calendar month; one ~9-11 km cell describes the zone.",
        warnings=warnings, monthly=monthly, climatology=clim,
        anomaly=[{"month": k, "value": v} for k, v in anom.items()],
        pixel_footprint=footprint,
        generated_on=date.today().isoformat(),
    )
