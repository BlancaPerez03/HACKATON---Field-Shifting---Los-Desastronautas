"""Configuration: dataset IDs, thresholds and limits. Change values here, never inside the code.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Every threshold carries a `kind`:
  - "standard": a recognised definition (FAO-56, ETCCDI climate-extremes indices).
  - "hypothesis": a reasonable team choice that a local agronomist must validate.
"""
import os
from pathlib import Path

# How to read this file:
# - Every other module imports `config` instead of hard-coding numbers, so a value changed here
#   changes the whole program.
# - Values that can differ per machine (project id, limits, folders) come from environment
#   variables with a sensible default, e.g. os.environ.get("FS_MAX_AREA_HA", 1000).

try:  # optional: load .env during local development (the file holds EE_PROJECT_ID, never committed)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

CONTRACT_VERSION = "1"                      # bump it if the JSON response format changes (it is part of the cache key)
ROOT = Path(__file__).resolve().parents[1]  # project folder (c:\climate); parents[1] = one level above backend/
CACHE_DIR = Path(os.environ.get("FS_CACHE_DIR") or ROOT / "data" / "cache")   # empty value in .env = default
DEMO_DIR = Path(__file__).resolve().parent / "demo_cache"

# --- Earth Engine -------------------------------------------------------------------------------
# Optional. `python run.py --setup` fills it in .env. Empty = use the project stored in the user's
# Earth Engine credentials, if any; otherwise the app runs with the no-login sources only.
EE_PROJECT_ID = os.environ.get("EE_PROJECT_ID") or None

# --- Request limits -----------------------------------------------------------------------------
POINT_BUFFER_M = float(os.environ.get("FS_POINT_BUFFER_M", 50))
MAX_AREA_HA = float(os.environ.get("FS_MAX_AREA_HA", 1000))
MAX_VERTICES = int(os.environ.get("FS_MAX_VERTICES", 2000))
DEFAULT_YEARS = int(os.environ.get("FS_DEFAULT_YEARS", 10))     # last N complete years
MAX_YEARS = int(os.environ.get("FS_MAX_YEARS", 25))
# Maximum seconds each data source may take before analyze.py gives up on it and reports a data gap.
MODULE_TIMEOUT_S = {
    "agroclimate_power": 120,
    "landsat": 180,
    "soil_moisture_smap": 180,
    "terrain": 60,
    "soil_openlandmap": 60,
    "crop_type": 90,        # the no-login CropScape fallback can need ~30-70 s
}

# --- Thresholds ---------------------------------------------------------------------------------
THRESHOLDS = {
    "frost_tmin_c": {"value": 0.0, "kind": "standard",
                     "note": "Air frost day: Tmin <= 0 degC (2 m air temperature)."},
    "ground_frost_tmin_c": {"value": 2.0, "kind": "hypothesis",
                            "note": "Tmin <= 2 degC as a proxy for ground/radiation frost."},
    "heat_tmax_c": {"value": 35.0, "kind": "hypothesis",
                    "note": "Heat-stress day. Crop- and stage-dependent (flowering matters most)."},
    "wet_day_mm": {"value": 1.0, "kind": "standard", "note": "Wet day: P >= 1 mm (ETCCDI)."},
    "very_heavy_precip_mm": {"value": 20.0, "kind": "standard",
                             "note": "R20mm: days with P >= 20 mm (ETCCDI)."},
    "r95_percentile": {"value": 95, "kind": "standard",
                       "note": "R95p: wet-day 95th percentile of the reference period (ETCCDI)."},
    "ndvi_bare": {"value": 0.25, "kind": "hypothesis",
                  "note": "Median NDVI below this value = bare or low cover."},
    "ndti_residue": {"value": 0.10, "kind": "hypothesis",
                     "note": "When NDVI is low, NDTI at or above this suggests crop residue; "
                             "below it suggests bare soil. Locally variable."},
    "ndvi_anomaly_z": {"value": -1.0, "kind": "hypothesis",
                       "note": "NDVI z-score at or below this flags a low-vigour month."},
    "deficit_percentile": {"value": 20, "kind": "hypothesis",
                           "note": "Monthly P - ET0 below its own 20th percentile = water deficit."},
    "landsat_min_valid_frac": {"value": 0.5, "kind": "hypothesis",
                               "note": "A Landsat scene counts as a valid observation when at least "
                                       "this fraction of parcel pixels is clear."},
    "gwetroot_min_std": {"value": 0.01, "kind": "hypothesis",
                         "note": "GWETROOT is hidden if its daily standard deviation is below this."},
}


def T(name):
    """Shortcut to read a threshold value: T("heat_tmax_c") -> 35.0."""
    return THRESHOLDS[name]["value"]


# --- Datasets (verified on the GEE catalog / POWER API on 2026-11-14) ---------------------------
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# AG community: radiation in MJ/m2/day. Max 20 parameters per request.
POWER_PARAMS = ["T2M_MAX", "T2M_MIN", "T2M", "T2MDEW", "RH2M", "PRECTOTCORR",
                "ALLSKY_SFC_SW_DWN", "WS2M", "PS", "GWETROOT", "FROST_DAYS"]
# Units we expect; anything else is converted (if known) or dropped with a warning.
# We check units at run time because a silent unit change (e.g. kWh instead of MJ) would corrupt ET0.
POWER_EXPECTED_UNITS = {
    "T2M_MAX": "C", "T2M_MIN": "C", "T2M": "C", "T2MDEW": "C", "RH2M": "%",
    "PRECTOTCORR": "mm/day", "ALLSKY_SFC_SW_DWN": "MJ/m^2/day", "WS2M": "m/s", "PS": "kPa",
    "GWETROOT": "1", "FROST_DAYS": "Days",
}

LANDSAT_L8 = "LANDSAT/LC08/C02/T1_L2"
LANDSAT_L9 = "LANDSAT/LC09/C02/T1_L2"
SMAP_L4 = "NASA/SMAP/SPL4SMGP/008"
NASADEM = "NASA/NASADEM_HGT/001"
COP_DEM = "COPERNICUS/DEM/GLO30_2024_1"      # outside 60N-56S; the old GLO30 ID is deprecated
OLM = {
    "ph": "OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02",              # pH x 10
    "texture": "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02",      # class 1-12
    "clay": "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",    # % (kg/kg)
    "sand": "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",    # % (kg/kg)
    "oc": "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02",        # x 5 g/kg
    "fc": "OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01",    # % volumetric
}
CDL = "USDA/NASS/CDL"        # band `cropland`, 1997-2024, CONUS
CDL_LAST_YEAR = 2024
