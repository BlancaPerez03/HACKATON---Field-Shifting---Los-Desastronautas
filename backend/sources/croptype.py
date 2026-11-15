"""Historical crop type from the USDA Cropland Data Layer (CONUS, 30 m, 1997-2024).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Region chosen by the team: USA (pilot farm in Fresno County, CA). Outside CONUS this module
reports OUT_OF_COVERAGE; EUCROPMAP / WorldCereal would be the EU / global alternatives.
"""
from .. import config
from ..contract import indicator, scale_note_for, warn
from ..gee_client import GeeUnavailable, ee_geometry, get_ee

CONUS_BBOX = (-125.0, 24.0, -66.5, 49.5)


class OutOfCoverage(RuntimeError):
    code = "OUT_OF_COVERAGE"


def in_conus(lon, lat):
    w, s, e, n = CONUS_BBOX
    return w <= lon <= e and s <= lat <= n


def class_names(values, names):
    """CDL stores class codes and names as comma-separated strings (verified 2026-11-14)."""
    split = lambda x: x.split(",") if isinstance(x, str) else list(x or [])  # noqa: E731
    out = {}
    for v, n in zip(split(values), split(names)):
        try:
            out[int(float(v))] = n.strip()
        except ValueError:
            continue
    return out


def run(parcel, start, end):
    lon, lat = parcel.centroid
    if not in_conus(lon, lat):
        raise OutOfCoverage("USDA CDL covers the contiguous USA only.")
    try:
        ee = get_ee()
    except GeeUnavailable:
        # No Earth Engine: sample the CDL through the CropScape web service (no login).
        from . import cdl_cropscape
        return cdl_cropscape.run(parcel, start, end)
    geom = ee_geometry(ee, parcel)
    y0 = max(int(start[:4]), 2008)
    y1 = min(int(end[:4]), config.CDL_LAST_YEAR)
    col = ee.ImageCollection(config.CDL).filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01").select("cropland")

    def per_year(img):
        # frequencyHistogram counts pixels per class code inside the parcel, e.g. {"1": 640, "5": 180}
        # (1 = Corn, 5 = Soybeans). Later we turn the counts into fractions.
        h = img.reduceRegion(ee.Reducer.frequencyHistogram(), geom, scale=30, maxPixels=1e8).get("cropland")
        return ee.Feature(None, {"year": img.date().get("year"), "hist": h})

    first = ee.Image(col.first())
    fc = ee.FeatureCollection(col.map(per_year))
    res = ee.Dictionary({
        "years": fc.aggregate_array("year"),
        "hists": fc.aggregate_array("hist"),
        "names": first.get("cropland_class_names"),
        "values": first.get("cropland_class_values"),
    }).getInfo()
    names = class_names(res.get("values"), res.get("names"))
    rows = []
    for y, h in zip(res["years"], res["hists"]):
        h = h or {}
        tot = sum(h.values()) or 1
        top = sorted(h.items(), key=lambda kv: -kv[1])[:3]
        rows.append({"year": int(y), "dominant": [
            {"code": int(k), "name": names.get(int(k)), "fraction": round(v / tot, 2)} for k, v in top]})
    sn = scale_note_for(parcel.area_ha, 30)
    warnings = [] if sn == "parcel" else [warn("PARCEL_SMALLER_THAN_PIXEL")]
    # If in most years no crop covers 60 % of the parcel, the boundary probably spans several fields.
    mixed = sum(1 for y in rows if y["dominant"] and y["dominant"][0]["fraction"] < 0.6)
    if rows and mixed > len(rows) / 2:
        warnings.append(warn("MIXED_LAND_COVER"))
    return indicator(
        ids=[config.CDL], provider="USDA NASS", nasa=False, citation_key="usda_cdl",
        data_type="satellite", resolution_m=30, scale_note=sn, unit="crop class",
        method="Pixel-count histogram of the `cropland` band over the parcel per year; top 3 classes.",
        confidence="medium",
        confidence_reason="CDL accuracy varies by crop and state; the farmer must confirm the current rotation.",
        warnings=warnings,
        years=rows,
    )
