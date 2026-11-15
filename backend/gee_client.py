"""Earth Engine initialisation (once per process).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

Easiest setup: `python run.py --setup` (signs in once in the browser, finds or creates the Cloud
project and writes EE_PROJECT_ID to .env). Manual: `earthengine authenticate`, then set
EE_PROJECT_ID, or store the project in the credentials with `earthengine set_project <id>`: with
EE_PROJECT_ID empty we fall back to that stored project. Production: a service account with
roles/earthengine.writer and roles/serviceusage.serviceUsageConsumer via
GOOGLE_APPLICATION_CREDENTIALS; no code change. Credentials are never logged.
Without Earth Engine the app still runs: NASA POWER climate, USDA SSURGO soil and USDA CropScape
crop history need no login (see sources/soil_sda.py and sources/cdl_cropscape.py).
"""
import threading
import time

from . import config

_lock = threading.Lock()
_ready = False
_failed = {"at": 0.0, "reason": ""}
RETRY_AFTER_S = 60          # after a failure, do not retry ee.Initialize on every module call


class GeeUnavailable(RuntimeError):
    code = "GEE_UNAVAILABLE"


def _initialize(ee):
    """ee.Initialize with EE_PROJECT_ID, else with the project stored in the user's EE credentials."""
    if config.EE_PROJECT_ID:
        ee.Initialize(project=config.EE_PROJECT_ID)
        return
    from ee import oauth
    try:
        stored = oauth.get_credentials_arguments().get("quota_project_id")
    except OSError:
        stored = None
    if not (stored or oauth.get_appdefault_project()):
        raise GeeUnavailable("Earth Engine is not configured: run `python run.py --setup` once "
                             "(or set EE_PROJECT_ID in .env).")
    ee.Initialize()


def get_ee():
    """Return the initialised `ee` module or raise GeeUnavailable.

    Several threads call this at the same time (analyze.py runs modules in parallel). The lock plus
    the second `if _ready` check ("double-checked locking") makes sure ee.Initialize runs only once.
    """
    global _ready
    if _ready:
        import ee
        return ee
    with _lock:
        if _ready:
            import ee
            return ee
        if _failed["reason"] and time.monotonic() - _failed["at"] < RETRY_AFTER_S:
            raise GeeUnavailable(_failed["reason"])
        try:
            import ee
            _initialize(ee)
        except GeeUnavailable as e:
            _failed.update(at=time.monotonic(), reason=str(e))
            raise
        except Exception as e:  # do not leak credential paths or tokens
            reason = (f"Earth Engine initialisation failed ({type(e).__name__}); "
                      "run `python run.py --setup` to sign in and choose the project.")
            _failed.update(at=time.monotonic(), reason=reason)
            raise GeeUnavailable(reason) from None
        _ready = True
        _failed.update(at=0.0, reason="")
        return ee


def status():
    """{'ready': bool, 'reason': str} without raising (used by /api/status)."""
    try:
        get_ee()
        return {"ready": True, "reason": ""}
    except GeeUnavailable as e:
        return {"ready": False, "reason": str(e)}


def ee_geometry(ee, parcel):
    """Convert our GeoJSON parcel into an Earth Engine geometry (WGS84 lon/lat, straight edges)."""
    return ee.Geometry(parcel.geojson, proj="EPSG:4326", geodesic=False)
