"""Monthly NDVI and NDTI from Landsat 8 and 9 Collection 2 Level 2 (30 m).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Catalog (verified 2026-11-14): LANDSAT/LC08/C02/T1_L2 (2013-03-18 ->), LANDSAT/LC09/C02/T1_L2
(2021-10-31 ->). SR = DN * 0.0000275 - 0.2; reflectance outside [0, 1] is discarded.
QA_PIXEL bits 0-5 (fill, dilated cloud, cirrus, cloud, shadow, snow) -> masked.
QA_RADSAT bits 3-6 (saturation of bands 4-7) and bit 11 (terrain occlusion) -> masked.
NDVI = (B5 - B4) / (B5 + B4); NDTI = (B6 - B7) / (B6 + B7).
One getInfo per request: per-scene parcel means are reduced on the server, months are aggregated
here by pure functions.
"""
from collections import defaultdict

import numpy as np

from .. import config
from ..contract import indicator, r, scale_note_for, warn
from ..gee_client import ee_geometry, get_ee

QA_PIXEL_MASK = 0b111111                                  # bits 0-5
QA_RADSAT_MASK = (1 << 3) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 11)
SR_SCALE, SR_OFFSET = 0.0000275, -0.2


def qa_pixel_clear(qa):
    """Pure-Python twin of the server mask (for tests): True if bits 0-5 are all 0."""
    return (int(qa) & QA_PIXEL_MASK) == 0


def qa_radsat_ok(radsat):
    return (int(radsat) & QA_RADSAT_MASK) == 0


def sr_reflectance(dn):
    v = dn * SR_SCALE + SR_OFFSET
    return v if 0 <= v <= 1 else None


def _scene_features(ee, geom, start, end):
    """Server-side Earth Engine code: one small result (parcel means) per Landsat scene.

    Nothing runs on our computer here: we build a description of the computation and the final
    .getInfo() sends it to Google, which runs it and returns a list of features.
    """
    def prep(img):
        # Runs on every image of the collection (col.map(prep)).
        sr = img.select(["SR_B4", "SR_B5", "SR_B6", "SR_B7"]).multiply(SR_SCALE).add(SR_OFFSET)
        # QA_PIXEL is a bit field: each bit is a yes/no flag (cloud, shadow, snow...).
        # bitwiseAnd(0b111111) keeps bits 0-5; if the result is 0, none of those flags is on.
        clear = img.select("QA_PIXEL").bitwiseAnd(QA_PIXEL_MASK).eq(0)
        unsat = img.select("QA_RADSAT").bitwiseAnd(QA_RADSAT_MASK).eq(0)
        in_range = sr.gte(0).And(sr.lte(1)).reduce(ee.Reducer.min())
        ok = clear.And(unsat).And(in_range)
        ndvi = sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi")
        ndti = sr.normalizedDifference(["SR_B6", "SR_B7"]).rename("ndti")
        # "valid" is 1 for usable pixels and 0 otherwise; its parcel mean = fraction of clear pixels.
        valid = ok.unmask(0).rename("valid")
        stack = ndvi.addBands(ndti).updateMask(ok).addBands(valid)
        stats = stack.reduceRegion(ee.Reducer.mean(), geom, scale=30, maxPixels=1e8)
        return ee.Feature(None, {"t": img.get("system:time_start"),
                                 "sensor": img.get("SPACECRAFT_ID"),
                                 "ndvi": stats.get("ndvi"), "ndti": stats.get("ndti"),
                                 "valid": stats.get("valid")})

    col = (ee.ImageCollection(config.LANDSAT_L8).merge(ee.ImageCollection(config.LANDSAT_L9))
           .filterBounds(geom).filterDate(start, end))
    return ee.FeatureCollection(col.map(prep)).getInfo()["features"]


def aggregate(scenes, min_valid_frac=None):
    """Pure aggregation of per-scene parcel means into monthly medians and a climatology.

    scenes: [{"month": "YYYY-MM", "ndvi", "ndti", "valid": fraction 0-1}]
    """
    thr = config.T("landsat_min_valid_frac") if min_valid_frac is None else min_valid_frac
    # defaultdict(list) creates an empty list automatically the first time a month key is used.
    by_month = defaultdict(list)
    all_months = defaultdict(int)
    for s in scenes:
        all_months[s["month"]] += 1
        if s.get("valid") is not None and s["valid"] >= thr and s.get("ndvi") is not None:
            by_month[s["month"]].append(s)
    out = {"ndvi": [], "ndti": []}
    for mo in sorted(all_months):
        good = by_month.get(mo, [])
        pct = np.mean([s["valid"] for s in good]) * 100 if good else 0.0
        for band in ("ndvi", "ndti"):
            vals = [s[band] for s in good if s.get(band) is not None]
            out[band].append({"month": mo, "median": r(np.median(vals), 3) if vals else None,
                              "valid_observations": len(vals), "scenes": all_months[mo],
                              "valid_pixel_pct": r(pct, 0)})
    clim = {}
    for band, rows in out.items():
        per = defaultdict(list)
        per2 = defaultdict(int)
        for x in rows:
            if x["median"] is not None:
                per[int(x["month"][5:7])].append(x["median"])
                if x["valid_observations"] >= 2:
                    per2[int(x["month"][5:7])] += 1
        clim[band] = [{"month": m, "median": r(np.median(per[m]), 3) if per[m] else None,
                       "mean": r(np.mean(per[m]), 3) if per[m] else None,
                       "std": r(np.std(per[m], ddof=1), 3) if len(per[m]) > 1 else None,
                       "years": len(per[m]), "years_2obs": per2[m]} for m in range(1, 13)]
    return out, clim


def run(parcel, start, end):
    """Returns {"ndvi": indicator, "ndti": indicator}."""
    ee = get_ee()
    geom = ee_geometry(ee, parcel)
    feats = _scene_features(ee, geom, start, end)
    import datetime as _dt
    scenes, sensors = [], set()
    for f in feats:
        p = f["properties"]
        sensors.add(p.get("sensor"))
        month = _dt.datetime.fromtimestamp(p["t"] / 1000, _dt.UTC).strftime("%Y-%m")
        scenes.append({"month": month, "ndvi": p.get("ndvi"), "ndti": p.get("ndti"),
                       "valid": p.get("valid")})
    monthly, clim = aggregate(scenes)

    total = len(scenes)
    valid = sum(x["valid_observations"] for x in monthly["ndvi"])
    common = []
    if total and valid / total < 0.4:
        common.append(warn("HIGH_CLOUD", f"Only {valid} of {total} scenes passed the mask."))
    thin = [c["month"] for c in clim["ndvi"] if c["years_2obs"] < 3]
    if thin:
        common.append(warn("LOW_VALID_OBS", f"Months with < 3 years of >= 2 valid scenes: {thin}."))
    if len(sensors) > 1:
        common.append(warn("MIXED_SENSORS"))
    sn = scale_note_for(parcel.area_ha, 30)
    if sn == "sub_parcel_mixed":
        common.append(warn("PARCEL_SMALLER_THAN_PIXEL"))
    short = [c["month"] for c in clim["ndvi"] if c["years"] < 5]
    if short:
        common.append(warn("SHORT_CLIMATOLOGY", f"Months with < 5 years: {short}."))
    conf = "high" if not thin else "medium" if len(thin) <= 3 else "low"
    base = dict(ids=[config.LANDSAT_L8, config.LANDSAT_L9], provider="NASA/USGS", nasa=True,
                citation_key="landsat_c2l2", data_type="satellite", resolution_m=30, scale_note=sn,
                unit="dimensionless (-1 to 1)",
                thresholds={"min_valid_pixel_frac": config.THRESHOLDS["landsat_min_valid_frac"]},
                confidence=conf,
                confidence_reason=f"{valid} valid scenes of {total}; {len(thin)} months with thin coverage.")
    return {
        "ndvi": indicator(**base, method="Monthly median of per-scene parcel-mean NDVI (B5, B4), cloud-masked "
                                         "with QA_PIXEL bits 0-5 and QA_RADSAT; scenes need >= 50 % clear pixels.",
                          warnings=common + [warn("NDVI_NOT_FERTILITY")],
                          monthly=monthly["ndvi"], climatology=clim["ndvi"]),
        "ndti": indicator(**base, method="NDTI = (SWIR1 - SWIR2) / (SWIR1 + SWIR2) from B6, B7, same mask. Only "
                                         "meaningful when NDVI is low (residue vs bare soil).",
                          warnings=common, monthly=monthly["ndti"], climatology=clim["ndti"]),
    }
