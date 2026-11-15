"""Unit tests of the pure formulas (no network). Run: python -m pytest tests -q

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

How pytest works: every function whose name starts with test_ is run; an `assert` that is False
makes the test fail. @pytest.mark.parametrize runs the same test with several inputs.
Where possible, expected values come from published worked examples (FAO-56) or hand
calculations, not from our own code, so a test can really catch a wrong formula.
"""
import numpy as np
import pandas as pd
import pytest

from backend import derived
from backend.et0 import et0_hargreaves, et0_pm, extraterrestrial_radiation
from backend.geometry import GeometryError, prepare
from backend.sources.landsat import aggregate, qa_pixel_clear, qa_radsat_ok, sr_reflectance
from backend.sources.soil import depth_weighted


# --- ET0 ------------------------------------------------------------------------------------
def test_ra_fao56_example8():
    assert abs(extraterrestrial_radiation(-20, 246) - 32.2) < 0.1     # FAO-56 Example 8


def test_et0_pm_fao56_example18():
    et0 = et0_pm(tmax=21.5, tmin=12.3, rs=22.07, u2=2.078, lat_deg=50.8, doy=187,
                 elevation_m=100, ea=1.409)
    assert abs(float(et0) - 3.9) < 0.1                               # FAO-56 Example 18


def test_et0_hargreaves_hand_calculation():
    # Ra(20S, doy 246) = 32.2; 0.0023 * 0.408*32.2 * (22.5+17.8) * sqrt(15) = 4.72
    assert abs(float(et0_hargreaves(30, 15, -20, 246)) - 4.72) < 0.05


# --- Frost dates ----------------------------------------------------------------------------
def _tmin(years=(2010, 2019), frost_spring="03-10", frost_autumn="11-20"):
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[1]}-12-31", freq="D")
    s = pd.Series(10.0, index=idx)
    for y in range(years[0], years[1] + 1):
        s[f"{y}-01-01":f"{y}-{frost_spring}"] = -1.0
        s[f"{y}-{frost_autumn}":f"{y}-12-31"] = -1.0
    return s


def test_frost_dates_north():
    fd = derived.frost_dates(_tmin(), "north", 0.0)
    assert fd["last_spring_frost"]["p50"] == "03-10"
    assert fd["first_autumn_frost"]["p50"] == "11-20"
    assert fd["last_spring_frost"]["years_with_frost"] == 10


def test_frost_dates_south_uses_midyear_season():
    idx = pd.date_range("2010-01-01", "2014-12-31", freq="D")
    s = pd.Series(15.0, index=idx)
    for y in range(2010, 2015):
        s[f"{y}-05-15":f"{y}-09-20"] = -2.0            # austral winter
    fd = derived.frost_dates(s, "south", 0.0)
    assert fd["first_autumn_frost"]["p50"] == "05-15"
    assert fd["last_spring_frost"]["p50"] == "09-20"


def test_frost_threshold_is_inclusive():
    s = _tmin()
    s[s < 0] = 0.0                                     # exactly 0 degC counts as frost
    assert derived.frost_dates(s, "north", 0.0)["last_spring_frost"]["years_with_frost"] == 10


# --- Landsat QA mask ------------------------------------------------------------------------
@pytest.mark.parametrize("qa,clear", [(21824, True),        # typical clear land (bit 6 set)
                                      (1, False),            # fill
                                      (1 << 1, False), (1 << 2, False), (1 << 3, False),
                                      (1 << 4, False), (1 << 5, False),
                                      (1 << 6, True), (1 << 7, True)])   # clear / water bits
def test_qa_pixel_bits_0_to_5(qa, clear):
    assert qa_pixel_clear(qa) is clear


def test_qa_radsat_and_reflectance_scale():
    assert qa_radsat_ok(0) and qa_radsat_ok(1 << 0)          # band 1 saturation is irrelevant
    assert not qa_radsat_ok(1 << 3) and not qa_radsat_ok(1 << 11)
    assert abs(sr_reflectance(10000) - 0.075) < 1e-9
    assert sr_reflectance(1) is None                          # negative reflectance discarded


def test_landsat_aggregate_counts_valid():
    scenes = [{"month": "2020-05", "ndvi": 0.6, "ndti": 0.1, "valid": 0.9},
              {"month": "2020-05", "ndvi": 0.2, "ndti": 0.1, "valid": 0.3},   # rejected
              {"month": "2020-05", "ndvi": 0.7, "ndti": 0.1, "valid": 0.8}]
    monthly, clim = aggregate(scenes, 0.5)
    m = monthly["ndvi"][0]
    assert m["valid_observations"] == 2 and m["scenes"] == 3 and abs(m["median"] - 0.65) < 1e-9
    assert clim["ndvi"][4]["years_2obs"] == 1


# --- Extremes -------------------------------------------------------------------------------
def test_r95p_r20_rx1day():
    idx = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    p = pd.Series(0.0, index=idx)
    p.iloc[::10] = np.tile(np.arange(1, 21, dtype=float), 4)[: len(p.iloc[::10])]   # 1..20 mm
    p["2000-06-01"] = 50.0
    ext = derived.precip_extremes(p, wet_mm=1, heavy_mm=20, pct=95)
    wet = p[p >= 1]
    assert ext["r95_threshold_mm"] == round(float(np.percentile(wet, 95)), 1)
    y2000 = ext["per_year"][0]
    assert y2000["rx1day_mm"] == 50.0
    assert y2000["r20mm_days"] == int((p["2000"] >= 20).sum())
    assert y2000["r95p_days"] == int((p["2000"] > np.percentile(wet, 95)).sum())


# --- Erosion index --------------------------------------------------------------------------
def test_erosion_index_levels_and_note():
    bare = {"months": [{"month": m, "class": "bare"} for m in (1, 2, 12)]}
    hi = derived.erosion_index(15, 80, 250, 15, 20, 4, bare, [1, 2, 12])
    lo = derived.erosion_index(0.5, 12, 25, 30, 40, 30,
                               {"months": [{"month": 1, "class": "residue"}]}, [1, 2, 12])
    assert hi["value"] == "high" and lo["value"] == "low"
    assert "not a soil-loss estimate" in hi["note"]
    assert set(hi["factors"]) == {"slope_LS", "erosivity_R", "erodibility_K", "cover_C"}


def test_erosion_index_missing_factors():
    e = derived.erosion_index(slope_p90_deg=5, rx1day_mm=40, clay_pct=20, sand_pct=30, oc_g_kg=8)
    assert e["confidence"] == "low" and e["factors"]["cover_C"] is None
    assert derived.erosion_index(slope_p90_deg=5, rx1day_mm=40) is None     # < 3 factors


def test_soil_depth_weighting():
    assert depth_weighted(10, 10, 10) == 10
    assert abs(depth_weighted(30, 0, 0) - 5) < 1e-9


# --- Vulnerability --------------------------------------------------------------------------
def test_vulnerability_ignores_dormant_months_and_needs_abnormal_heat():
    clim = [{"month": m, "median": 0.8 if m == 7 else 0.15, "mean": 0.8 if m == 7 else 0.15,
             "std": 0.05, "years": 10} for m in range(1, 13)]
    ndvi = [{"month": f"{y}-{m:02d}", "median": (0.6 if y in (2020, 2021) else 0.82) if m == 7 else 0.05}
            for y in range(2016, 2026) for m in (1, 7)]
    climate = [{"month": f"{y}-07", "heat_days": 10 if y in (2020, 2021) else 3, "deficit": False}
               for y in range(2016, 2026)]
    v = derived.vulnerability(ndvi, clim, climate)
    assert v["value"] == [7]                                  # January (dormant) never evaluated
    assert all(m["month"] == 7 for m in v["months"])
    climate_flat = [dict(c, heat_days=5) for c in climate]    # heat every year = not abnormal
    assert derived.vulnerability(ndvi, clim, climate_flat)["value"] == []


# --- Geometry -------------------------------------------------------------------------------
def test_point_buffer_and_area():
    p = prepare({"type": "Point", "coordinates": [-120.11, 36.34]})
    assert abs(p.area_ha - 0.785) < 0.01                       # pi * 50^2 m2
    assert p.warnings[0]["code"] == "POINT_BUFFERED"


def test_feature_collection_with_one_feature_accepted():
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
          "geometry": {"type": "Polygon", "coordinates": [[[-93.7748, 42.0148], [-93.7748, 42.0079],
                       [-93.7652, 42.0079], [-93.7652, 42.0148], [-93.7748, 42.0148]]]}}]}
    assert abs(prepare(fc).area_ha - 60.9) < 0.2


def test_terrain_inside_mask_uses_pixel_centres():
    from backend.sources.terrain_grid import ARCSEC, inside_mask
    # polygon covering only the western column of a 2 x 2 arc-second box; pixels outside must be 0, never nodata
    west = {"type": "Polygon", "coordinates": [[[0, 0], [1.2 * ARCSEC, 0], [1.2 * ARCSEC, 2 * ARCSEC],
                                                [0, 2 * ARCSEC], [0, 0]]]}
    assert inside_mask(west, 0, 2 * ARCSEC, 2, 2) == [1, 0, 1, 0]


def test_self_intersection_and_size_rejected():
    bow = {"type": "Polygon", "coordinates": [[[0, 0], [1e-3, 1e-3], [1e-3, 0], [0, 1e-3], [0, 0]]]}
    with pytest.raises(GeometryError) as e:
        prepare(bow)
    assert e.value.code == "GEOMETRY_INVALID"
    big = {"type": "Polygon", "coordinates": [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1], [0, 0]]]}
    with pytest.raises(GeometryError) as e:
        prepare(big)
    assert e.value.code == "GEOMETRY_TOO_LARGE"
