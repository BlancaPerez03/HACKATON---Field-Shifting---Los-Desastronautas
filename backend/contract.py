"""Helpers for the JSON contract (dossier section 5.3): indicators, warnings, citations.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
"""
import math

# Allowed values for "data_type" and "scale_note". indicator() asserts against them, so a typo
# in a source module fails loudly during development instead of reaching the frontend.
DATA_TYPES = {"satellite", "satellite_gauge_merged", "reanalysis", "model", "derived",
              "user_input", "in_situ", "soil_survey"}
SCALE_NOTES = {"parcel", "sub_parcel_mixed", "zone"}

# Default English text for every warning code. The code is the stable part (the frontend can
# translate or group it); the message is for humans.
WARNING_TEXT = {
    "LOW_VALID_OBS": "Few valid cloud-free observations; treat monthly values with caution.",
    "HIGH_CLOUD": "Many scenes were rejected by the cloud mask.",
    "PARCEL_SMALLER_THAN_PIXEL": "The parcel is smaller than one pixel of this dataset; the value mixes "
                                 "the parcel with its surroundings.",
    "OUT_OF_COVERAGE": "The parcel is outside the dataset's coverage.",
    "MIXED_SENSORS": "Landsat 8 and Landsat 9 are combined (same band set, small cross-sensor differences).",
    "POINT_BUFFERED": "Point input buffered.",
    "ZONE_SCALE_DATA": "This dataset describes the surrounding zone (tens of km), not the parcel.",
    "PROVISIONAL_DATA": "Part of the period uses provisional data.",
    "MODEL_SOIL_ESTIMATE": "Soil values are a 250 m global model estimate, not a laboratory analysis. "
                           "Farmer-provided soil tests take priority.",
    "NDVI_NOT_FERTILITY": "NDVI indicates green vegetation vigor, not soil fertility or yield.",
    "FROST_AIR_TEMP_PROXY": "Frost is estimated from 2 m air temperature over a ~50 km cell; radiation "
                            "frost in valley bottoms can be more frequent.",
    "SOLAR_DATA_LAG": "Recent solar radiation is missing (CERES latency); Hargreaves ET0 used for those days.",
    "WETNESS_INDEX_NOT_VOLUMETRIC": "GWETROOT is a 0-1 relative wetness index from the MERRA-2 model, "
                                    "not volumetric soil moisture.",
    "WETNESS_INDEX_FLAT": "GWETROOT barely varies at this location and is hidden; use SMAP instead.",
    "EXTREMES_SMOOTHED": "Reanalysis smooths local rainfall extremes; true point extremes are likely higher.",
    "SHORT_CLIMATOLOGY": "Fewer than 5 years of valid data for some months.",
    "MIXED_LAND_COVER": "The parcel mixes several land-cover classes in most years; check the boundary "
                        "follows a single field. Parcel-mean NDVI and bare months are then unreliable.",
    "SOURCE_DEPRECATED_FALLBACK": "Primary source unavailable here; a fallback source was used.",
}


def warn(code, message=None):
    """Build a warning dict; pass `message` to override the default text with specific numbers."""
    return {"code": code, "message": message or WARNING_TEXT[code]}


def indicator(*, ids, provider, nasa, citation_key, data_type, resolution_m, scale_note, unit,
              method, thresholds=None, confidence="medium", confidence_reason="", warnings=None,
              **data):
    """Build one indicator with the traceability fields every indicator must have.

    The `*` in the signature forces keyword arguments, so callers cannot mix up the order.
    `**data` collects the indicator-specific values (monthly series, slope, pH...) and they are
    merged at the end of the dict.
    """
    assert data_type in DATA_TYPES, data_type
    assert scale_note in SCALE_NOTES, scale_note
    out = {
        "source": {"ids": ids, "provider": provider, "nasa": nasa, "citation_key": citation_key},
        "data_type": data_type,
        "resolution_m": resolution_m,
        "scale_note": scale_note,
        "unit": unit,
        "method": method,
        "thresholds": thresholds or {},
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "warnings": warnings or [],
    }
    out.update(data)
    return out


def scale_note_for(area_ha, resolution_m, zone=False):
    """'parcel' if the parcel is at least one pixel big, else 'sub_parcel_mixed'.
    area_ha * 10,000 converts hectares to m2; resolution_m ** 2 is the area of one pixel."""
    if zone:
        return "zone"
    return "parcel" if area_ha * 10_000 >= resolution_m ** 2 else "sub_parcel_mixed"


def r(x, nd=2):
    """Round for JSON; NaN/None -> None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


AI_ASSISTANCE = ("Parts of this backend were generated with AI coding tools (Claude) and reviewed by "
                 "the team; see README, 'Use of AI tools'. Indicator values come from the cited "
                 "datasets, not from an AI model.")

CITATIONS = {
    "nasa_power": "The data was obtained from the National Aeronautics and Space Administration (NASA) "
                  "Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project "
                  "funded through the NASA Earth Science/Applied Science Program.",
    "landsat_c2l2": "Landsat 8 and Landsat 9 Collection 2 Level-2 Surface Reflectance, courtesy of the "
                    "U.S. Geological Survey (USGS) and NASA.",
    "smap_l4": "Reichle, R. et al. SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil "
               "Moisture Geophysical Data, Version 8. NASA National Snow and Ice Data Center DAAC. "
               "(Accessed via Google Earth Engine, NASA/SMAP/SPL4SMGP/008.)",
    "nasadem": "NASA JPL (2020). NASADEM Merged DEM Global 1 arc second V001. NASA EOSDIS Land "
               "Processes DAAC. doi:10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
    "copernicus_dem": "Copernicus DEM GLO-30 (2024 release), European Space Agency / Copernicus.",
    "openlandmap": "Hengl, T. et al. OpenLandMap soil property maps at 250 m (pH, texture, organic "
                   "carbon, water content at 33 kPa), Zenodo, licence CC-BY-SA 4.0.",
    "usda_cdl": "USDA National Agricultural Statistics Service Cropland Data Layer. Published "
                "crop-specific data layer. USDA-NASS, Washington, DC.",
    "usda_ssurgo": "Soil Survey Staff, Natural Resources Conservation Service, United States Department of "
                   "Agriculture. Soil Survey Geographic (SSURGO) Database. Available online through Soil Data "
                   "Access (sdmdataaccess.sc.egov.usda.gov).",
    "earth_engine": "Gorelick, N. et al. (2017). Google Earth Engine: Planetary-scale geospatial "
                    "analysis for everyone. Remote Sensing of Environment 202, 18-27.",
}
