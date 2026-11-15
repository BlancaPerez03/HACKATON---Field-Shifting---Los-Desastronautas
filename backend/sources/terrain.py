"""Elevation and slope: NASADEM (60N-56S) or Copernicus GLO-30 2024 outside it.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Catalog (verified 2026-11-14): NASA/NASADEM_HGT/001 band `elevation` (m, EGM96), 30 m.
COPERNICUS/DEM/GLO30_2024_1 band `DEM` (the old COPERNICUS/DEM/GLO30 is deprecated).
ee.Terrain.slope returns degrees and leaves edge pixels empty, so slope is computed on the
unclipped DEM and only then reduced over the parcel.
"""
from .. import config
from ..contract import indicator, r, scale_note_for, warn
from ..gee_client import ee_geometry, get_ee


def run(parcel, start=None, end=None):
    ee = get_ee()
    geom = ee_geometry(ee, parcel)
    lat = parcel.centroid[1]
    warnings = []
    if -56 <= lat <= 60:
        dem = ee.Image(config.NASADEM).select("elevation")
        ids, provider, nasa, cite = [config.NASADEM], "NASA JPL (SRTM reprocessed)", True, "nasadem"
    else:
        c = ee.ImageCollection(config.COP_DEM).select("DEM")
        dem = c.mosaic().setDefaultProjection(c.first().projection()).rename("elevation")
        ids, provider, nasa, cite = [config.COP_DEM], "ESA Copernicus", False, "copernicus_dem"
        warnings.append(warn("SOURCE_DEPRECATED_FALLBACK",
                             "Outside SRTM/NASADEM coverage (60N-56S); Copernicus GLO-30 used."))
    slope = ee.Terrain.slope(dem).rename("slope")
    # combine(...) computes several statistics in one pass over the pixels (mean, min/max, 90th percentile).
    reducer = (ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)
               .combine(ee.Reducer.percentile([90]), sharedInputs=True))
    stats = dem.addBands(slope).reduceRegion(reducer, geom, scale=30, maxPixels=1e8).getInfo()
    sn = scale_note_for(parcel.area_ha, 30)
    if sn == "sub_parcel_mixed":
        warnings.append(warn("PARCEL_SMALLER_THAN_PIXEL"))
    return indicator(
        ids=ids, provider=provider, nasa=nasa, citation_key=cite, data_type="satellite",
        resolution_m=30, scale_note=sn, unit="elevation m (EGM96); slope degrees",
        method="Slope with ee.Terrain.slope on the unclipped DEM (4-neighbour), then mean/min/max/p90 over the parcel at 30 m.",
        confidence="high" if sn == "parcel" else "medium",
        confidence_reason="30 m DEM from radar interferometry (2000); field levelling since then is not captured.",
        warnings=warnings,
        elevation_m={"mean": r(stats.get("elevation_mean"), 1), "min": r(stats.get("elevation_min"), 1),
                     "max": r(stats.get("elevation_max"), 1)},
        slope_deg={"mean": r(stats.get("slope_mean"), 2), "max": r(stats.get("slope_max"), 2),
                   "p90": r(stats.get("slope_p90"), 2)},
    )
