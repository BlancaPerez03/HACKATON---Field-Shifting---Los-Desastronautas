"""Soil properties 0-30 cm from OpenLandMap (250 m, static 1950-2018, CC-BY-SA 4.0).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Catalog scales (verified 2026-11-14): pH stored x10; organic carbon stored in units of 5 g/kg;
clay and sand in % (kg/kg); water content at 33 kPa (field capacity) in % volumetric; texture
class codes 1-12 (USDA). Bands b0, b10, b30 = depths 0, 10, 30 cm.
0-30 cm mean = trapezoid over depths: (5*b0 + 15*b10 + 10*b30) / 30.
"""
from .. import config
from ..contract import indicator, r, scale_note_for, warn
from ..gee_client import GeeUnavailable, ee_geometry, get_ee

TEXTURE_CLASSES = {1: "clay", 2: "silty clay", 3: "sandy clay", 4: "clay loam",
                   5: "silty clay loam", 6: "sandy clay loam", 7: "loam", 8: "silt loam",
                   9: "sandy loam", 10: "silt", 11: "loamy sand", 12: "sand"}
SCALE = {"ph": 0.1, "oc": 5.0, "clay": 1.0, "sand": 1.0, "fc": 1.0}


def depth_weighted(b0, b10, b30):
    """Pure trapezoidal 0-30 cm mean."""
    if None in (b0, b10, b30):
        return None
    return (5 * b0 + 15 * b10 + 10 * b30) / 30


def run(parcel, start=None, end=None):
    try:
        ee = get_ee()
    except GeeUnavailable:
        # No Earth Engine: USDA SSURGO through Soil Data Access (no login). Same output fields.
        from . import soil_sda
        return soil_sda.run(parcel, start, end)
    geom = ee_geometry(ee, parcel)
    pt = geom.centroid(1)
    # For each property: weighted 0-30 cm average of the 3 depth bands, then multiply by the catalog
    # scale (pH is stored x10, organic carbon in units of 5 g/kg).
    imgs = []
    for k in ("ph", "oc", "clay", "sand", "fc"):
        im = ee.Image(config.OLM[k])
        imgs.append(im.select("b0").multiply(5).add(im.select("b10").multiply(15))
                    .add(im.select("b30").multiply(10)).divide(30).multiply(SCALE[k]).rename(k))
    tex = ee.Image(config.OLM["texture"]).select("b10").rename("texture")
    cont = ee.Image.cat(imgs)
    res = ee.Dictionary({
        "parcel": cont.reduceRegion(ee.Reducer.mean(), geom, scale=250, maxPixels=1e8),
        "centroid": cont.addBands(tex).reduceRegion(ee.Reducer.first(), pt, scale=250),
        "texture_mode": tex.reduceRegion(ee.Reducer.mode(), geom, scale=250, maxPixels=1e8),
    }).getInfo()
    parcel_vals, cen = res.get("parcel") or {}, res.get("centroid") or {}
    # A tiny parcel may not contain the centre of any 250 m pixel -> the parcel mean is empty and we
    # fall back to the pixel under the centroid.
    used_centroid = parcel_vals.get("ph") is None
    vals = cen if used_centroid else parcel_vals
    tcode = (res.get("texture_mode") or {}).get("texture") or cen.get("texture")
    warnings = [warn("MODEL_SOIL_ESTIMATE")]
    sn = scale_note_for(parcel.area_ha, 250)
    if sn == "sub_parcel_mixed":
        warnings.append(warn("PARCEL_SMALLER_THAN_PIXEL"))
    clay, sand = vals.get("clay"), vals.get("sand")
    return indicator(
        ids=[config.OLM[k] for k in ("ph", "texture", "clay", "sand", "oc", "fc")],
        provider="OpenLandMap (EnvirometriX / OpenGeoHub)", nasa=False, citation_key="openlandmap",
        data_type="model", resolution_m=250, scale_note=sn, unit="see each field",
        method="Depth-weighted 0-30 cm mean (trapezoid over 0, 10, 30 cm) averaged over the parcel at 250 m; "
               "centroid pixel if the parcel contains no pixel centre. Texture: modal USDA class at 10 cm.",
        confidence="low",
        confidence_reason="Global machine-learning estimate at 250 m from 1950-2018 profiles; not a lab analysis.",
        warnings=warnings,
        licence="CC-BY-SA 4.0 (share-alike applies to redistributed derived layers)",
        sampled_at="centroid" if used_centroid else "parcel",
        ph_h2o=r(vals.get("ph"), 2),
        organic_carbon_g_kg=r(vals.get("oc"), 1),
        clay_pct=r(clay, 1), sand_pct=r(sand, 1),
        silt_pct=r(100 - clay - sand, 1) if clay is not None and sand is not None else None,
        field_capacity_33kpa_pct_vol=r(vals.get("fc"), 1),
        texture_class={"code": int(tcode) if tcode is not None else None,
                       "name": TEXTURE_CLASSES.get(int(tcode)) if tcode is not None else None},
    )
