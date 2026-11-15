"""Unit tests of the scenario simulator (no network). Run: python -m pytest tests -q

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
"""
import json

import numpy as np
import pandas as pd
import pytest

from backend import config, simulate as sim


def _power_payload(years=(2014, 2023), seed=1):
    """Synthetic daily series in the NASA POWER JSON layout (continental climate with winter frost)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[1]}-12-31", freq="D")
    season = np.cos(2 * np.pi * (idx.day_of_year.values - 200) / 365)
    tmax = 16 + 16 * season + rng.normal(0, 3, len(idx))
    tmin = 4 + 14 * season + rng.normal(0, 3, len(idx))
    rain = np.where(rng.random(len(idx)) < 0.3, rng.gamma(1.0, 9, len(idx)), 0.0)
    cols = {"T2M_MAX": tmax, "T2M_MIN": tmin, "T2M": (tmax + tmin) / 2, "T2MDEW": tmin - 2,
            "RH2M": 70 - 10 * season, "PRECTOTCORR": rain, "ALLSKY_SFC_SW_DWN": 16 + 9 * season,
            "WS2M": np.full(len(idx), 3.0), "PS": np.full(len(idx), 97.0)}
    keys = idx.strftime("%Y%m%d")
    return {"header": {"fill_value": -999.0}, "geometry": {"coordinates": [-93.7, 42.0, 300.0]},
            "properties": {"parameter": {k: dict(zip(keys, map(float, v))) for k, v in cols.items()}}}


# A pytest fixture prepares data for the tests that ask for it by name (here `key`).
# tmp_path is a fresh temporary folder; monkeypatch temporarily points config.CACHE_DIR there, so
# the tests use a synthetic parcel and never touch the real cache or the internet.
@pytest.fixture
def key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo")
    (tmp_path / "cache" / "power").mkdir(parents=True)
    (tmp_path / "cache" / "baseline").mkdir(parents=True)
    (tmp_path / "cache" / "terrain").mkdir(parents=True)
    (tmp_path / "cache" / "power" / "cell.json").write_text(json.dumps(_power_payload()))
    bundle = {"key": "k1", "centroid": [-93.7, 42.0], "hemisphere": "north", "start": "2014-01-01",
              "end": "2023-12-31", "power_file": "cell.json", "grid_elevation_m": 300.0,
              "erosion_static": {"slope_p90_deg": 4.0, "clay_pct": 25, "sand_pct": 20, "oc_g_kg": 15,
                                 "bare_months": {"months": [{"month": m, "class": "bare"} for m in (1, 2, 3, 12)]}}}
    (tmp_path / "cache" / "baseline" / "k1.json").write_text(json.dumps(bundle))
    grid = {"bbox": [0, 0, 2, 2], "rows": 2, "cols": 2, "slope_deg": [0.5, 20.0, 1.0, 1.0],
            "tpi_m": [-2.0, 0.0, -3.0, 0.0], "in_parcel": [1, 1, 1, 0]}
    (tmp_path / "cache" / "terrain" / "k1.json").write_text(json.dumps(grid))
    sim.clear_simulation_cache()
    yield "k1"                       # the test runs here; code after yield is the clean-up
    sim.clear_simulation_cache()


def test_zero_controls_equal_baseline(key):
    out = sim.simulate(key)
    assert out["baseline"] == out["scenario_result"]
    assert all(d["direction"] == "same" for d in out["deltas"])
    assert out["version"] == "sim-1"
    assert out["warnings"][0]["code"] == "HYPOTHETICAL_SCENARIO"


def test_zero_controls_equal_analyze_formulas(key):
    from backend import derived
    from backend.sources.power import parse
    df, _, _ = parse(_power_payload())
    direct = derived.climate_summary(df, 42.0, 300.0, "north")
    _, _, base, _ = sim._baseline(key)
    for f in ("monthly_climatology", "frost", "et0", "water_balance", "precip_extremes"):
        assert json.dumps(base[f], sort_keys=True) == json.dumps(direct[f], sort_keys=True)


def test_warmer_means_more_heat_less_frost_more_et0(key):
    b = sim.simulate(key)["scenario_result"]
    w = sim.simulate(key, delta_temp_c=2.0)["scenario_result"]
    assert w["heat"]["heat_days_per_year"] >= b["heat"]["heat_days_per_year"]
    assert w["frost"]["frost_days_le0_per_year"] <= b["frost"]["frost_days_le0_per_year"]
    assert w["frost"]["frost_days_le2_per_year"] <= b["frost"]["frost_days_le2_per_year"]
    assert w["water_balance"]["et0_annual_mm"] > b["water_balance"]["et0_annual_mm"]


def test_less_rain_means_more_deficit(key):
    b = sim.simulate(key)["scenario_result"]["water_balance"]
    d = sim.simulate(key, delta_precip_pct=-20)["scenario_result"]["water_balance"]
    assert d["mean_annual_deficit_mm"] >= b["mean_annual_deficit_mm"]
    assert d["annual_mean_precip_mm"] < b["annual_mean_precip_mm"]


def test_irrigation_zero_changes_nothing_and_full_clears_deficit(key):
    off = sim.simulate(key, -20, 1.5)["scenario_result"]
    zero = sim.simulate(key, -20, 1.5, True, 0)["scenario_result"]
    full = sim.simulate(key, -20, 1.5, True, 100)["scenario_result"]
    assert zero == off
    assert full["water_balance"]["remaining_deficit_mm"] == 0
    assert full["water_balance"]["deficit_months"] == []
    assert full["water_balance"]["mean_annual_deficit_mm"] == off["water_balance"]["mean_annual_deficit_mm"]
    for k in ("heat", "frost", "precip_extremes", "erosion_index"):
        assert full[k] == off[k]                      # irrigation never touches heat, frost or erosion


def test_controls_are_clamped(key):
    out = sim.simulate(key, delta_precip_pct=-80, delta_temp_c=9, irrigation_enabled=True,
                       irrigation_availability_pct=250)
    assert out["scenario"] == {"delta_precip_pct": -30, "delta_temp_c": 3, "irrigation_enabled": True,
                               "irrigation_availability_pct": 100}


def test_risk_zones_small_grid(key):
    z = sim.simulate(key)["risk_zones"]
    ero = z["erosion"]["base"]
    assert len(ero) == 4 and ero[3] == "."            # pixel outside the parcel
    assert int(ero[1]) > int(ero[0])                  # 20 deg slope ranks above 0.5 deg
    cold = z["cold_air"]["base"]
    assert cold[0] == "1" and cold[2] == "1"          # hollows (TPI <= -1) with slope <= 2 deg
    assert cold[1] == "0" and cold[3] == "."
    hot = sim.simulate(key, delta_temp_c=3)["risk_zones"]["cold_air"]["intensity"]
    assert hot["scenario"] <= hot["base"]


def test_crop_effect_responds_to_scenario(key):
    base = sim.simulate(key, crop_id="corn_maize")["crop_effect"]
    hot = sim.simulate(key, -25, 3.0, crop_id="corn_maize")["crop_effect"]
    assert base["baseline"] == base["scenario"]                       # zero controls: no change
    assert hot["scenario"]["gdd"]["available"] > hot["baseline"]["gdd"]["available"]
    assert hot["scenario"]["heat"]["stress_days"] >= hot["baseline"]["heat"]["stress_days"]
    assert hot["scenario"]["water"]["crop_need_mm"] > hot["baseline"]["water"]["crop_need_mm"]   # need follows ET0
    assert hot["scenario"]["water"]["season_rain_mm"] < hot["baseline"]["water"]["season_rain_mm"]
    irr = sim.simulate(key, -25, 3.0, True, 100, crop_id="corn_maize")["crop_effect"]["scenario"]["water"]
    assert irr["cover_pct"] >= 100 or irr["shortfall_mm"] == 0


def test_crop_gdd_base_zero_is_not_missing():
    from backend.crop_effects import season_climate
    idx = pd.date_range("2015-01-01", "2016-12-31", freq="D")
    df = pd.DataFrame({"T2M_MAX": 6.0, "T2M_MIN": 2.0, "T2M": 4.0, "PRECTOTCORR": 1.0}, index=idx)
    crop = {"sowing_start_month": 9, "harvest_start_month": 6, "harvest_end_month": 7, "gdd_base_c": 0.0,
            "t_opt_max_c": 20, "heat_fail_c": 34}
    sc = season_climate(df, pd.Series(1.0, index=idx), crop)
    assert sc["gdd"] > 0                     # base 0 degC with Tmean 4 degC accumulates heat
    assert sc["heat_days"] == 0              # 6 degC is never heat stress


def test_gdd_86_50_method_caps_both_ends():
    from backend.crop_effects import gdd_daily
    import numpy as np
    # Tmax 35 -> 30, Tmin 5 -> 10: (30 + 10) / 2 - 10 = 10 (simple method would give (35+5)/2-10 = 10 too)
    assert gdd_daily(np.array([35.0]), np.array([5.0]), np.array([20.0]), 10, "capped_10_30")[0] == 10
    # Hot night: Tmax 40 -> 30, Tmin 25 -> 25: 17.5; simple method on the mean 32.5 would give 22.5
    assert gdd_daily(np.array([40.0]), np.array([25.0]), np.array([32.5]), 10, "capped_10_30")[0] == 17.5
    assert gdd_daily(np.array([40.0]), np.array([25.0]), np.array([32.5]), 10, "simple")[0] == 22.5


def test_frost_sensitive_season_stops_at_frost():
    """A frost-sensitive crop only accumulates heat between the last spring frost and the first hard freeze."""
    from backend.crop_effects import season_climate
    idx = pd.date_range("2015-01-01", "2016-12-31", freq="D")
    tmin = pd.Series(12.0, index=idx)
    tmin[(idx.month == 5) & (idx.day == 20)] = -1.0          # late spring frost
    tmin[(idx.month == 9) & (idx.day == 10)] = -3.0          # early hard freeze
    df = pd.DataFrame({"T2M_MAX": 24.0, "T2M_MIN": tmin, "T2M": 18.0, "PRECTOTCORR": 2.0}, index=idx)
    crop = {"sowing_start_month": 4, "sowing_end_month": 5, "harvest_start_month": 9, "harvest_end_month": 11,
            "gdd_base_c": 10.0, "min_frost_free_days": 100, "perennial": False}
    sc = season_climate(df, pd.Series(1.0, index=idx), crop)
    # May 21 .. Sep 9 = 112 days of 8 degC-day each (Tmean 18 - base 10)
    assert sc["gdd"] == pytest.approx(112 * 8)
    long = season_climate(df, pd.Series(1.0, index=idx), {**crop, "min_frost_free_days": None})
    assert long["gdd"] > sc["gdd"]                           # frost-tolerant crop: whole Apr-Nov window


def test_water_check_fao56_fao33():
    from backend.crop_effects import checks
    site = {"ext_min_c": -20, "vern_days": 50, "summer_rain_mm": 200}
    crop = {"kc_avg": 1.0, "ky": 1.25, "min_frost_free_days": None}
    sc = {"gdd": 1000, "rain_mm": 300, "stored_mm": 100, "et0_mm": 500, "days": 120, "heat_days": None,
          "above_opt_days": None, "frost_days": 0, "hottest_month_t": 22, "seasons": 10}
    w = checks(sc, site, crop, None)["water"]
    assert w["crop_need_mm"] == 500 and w["cover_pct"] == 80
    assert w["expected_loss_pct"] == 25 and w["status"] == "marginal"        # 1.25 x 20 % deficit
    full = checks(sc, site, crop, None, irrigation_pct=100)["water"]
    assert full["cover_pct"] == 100 and full["status"] == "ok"
    dry = checks({**sc, "rain_mm": 50, "stored_mm": 50}, site, {**crop, "ky": 0.7}, None)["water"]
    assert dry["status"] == "limit"                                           # 20 % covered: needs irrigation


def test_winter_and_humidity_rules():
    from backend.crop_effects import checks
    sc = {"gdd": 3000, "rain_mm": 900, "stored_mm": 50, "et0_mm": 700, "days": 200, "heat_days": 0,
          "above_opt_days": 0, "frost_days": 0, "hottest_month_t": 28, "seasons": 10}
    from backend.crops import load_catalog
    cat = {c["id"]: c for c in load_catalog()["crops"]}
    gulf = {"ext_min_c": -4.0, "vern_days": 5, "summer_rain_mm": 500}
    plains = {"ext_min_c": -36.0, "vern_days": 60, "summer_rain_mm": 250}
    assert checks(sc, gulf, cat["winter_wheat"], None)["vernalization"]["status"] == "limit"
    assert checks(sc, plains, cat["winter_wheat"], None)["winter_cold"]["status"] == "marginal"
    assert checks(sc, gulf, cat["sugarcane_perennial"], None)["winter_cold"]["status"] == "ok"
    assert checks(sc, plains, cat["sugarcane_perennial"], None)["winter_cold"]["status"] == "limit"
    assert checks(sc, gulf, cat["grape_perennial"], None)["humid_summer"]["status"] == "limit"   # Pierce's disease
    assert checks(sc, gulf, cat["almond_perennial"], None)["humid_summer"]["status"] == "limit"
    assert checks(sc, gulf, cat["potato"], None)["cool_season"]["status"] == "limit"


def test_safe_sowing_rule():
    from backend.crop_effects import safe_sowing
    corn = {"min_frost_free_days": 120, "sowing_start_month": 4, "sowing_end_month": 5}
    assert safe_sowing(corn, "03-20")["status"] == "ok"          # frost over before April
    assert safe_sowing(corn, "04-26")["status"] == "marginal"    # sow late April / May
    assert safe_sowing(corn, "06-02")["status"] == "limit"
    assert safe_sowing({"min_frost_free_days": None}, "04-26")["status"] == "n/a"


def test_budget_arithmetic_and_breakeven():
    from backend.economics import budget, defaults
    b = budget(area_ha=10, yield_t_ha=10, price_usd_t=200, cost_usd_ha=1500, available_usd=12000,
               irrigation_mm=50, irrigation_cost_usd_mm_ha=2)
    assert b["cost_usd_ha"] == 1600 and b["total_cost_usd"] == 16000
    assert b["revenue_usd"] == 20000 and b["margin_usd"] == 4000
    assert b["breakeven_yield_t_ha"] == 8 and b["breakeven_price_usd_t"] == 160
    assert b["affordable"] is False and b["cash_gap_usd"] == -4000
    assert [w["margin_usd"] for w in b["what_if"]] == [4000, 2000, 0, -2000]
    partial = budget(area_ha=10, yield_t_ha=None, price_usd_t=200, cost_usd_ha=1500)
    assert partial["missing_inputs"] == ["expected yield"] and "margin_usd" not in partial
    d = defaults("corn_maize")                                   # 211 bu/acre, 25.401 kg/bu
    assert abs(d["yield_t_ha"] - 211 * 25.401 / 1000 / 0.40468564224) < 0.01
    assert abs(d["price_usd_t"] - 4.60 / 0.025401) < 0.01


def test_recommendation_rules():
    from backend import recommend as rec
    corn = {"id": "corn_maize", "name_en": "Corn", "n_balance_kg_ha": -140, "perennial": False}
    soy = {"id": "soybean", "name_en": "Soybean", "n_balance_kg_ha": 35, "perennial": False}
    grape = {"id": "grape_perennial", "name_en": "Grape", "n_balance_kg_ha": -20, "perennial": True}
    assert rec.rotation_check(soy, corn)["benefit"] is True             # legume after corn
    assert rec.rotation_check(corn, soy)["benefit"] is True             # corn uses the legume's N
    assert rec.rotation_check(corn, corn)["status"] == "marginal"       # repeat: pest build-up
    assert rec.rotation_check(grape, corn)["status"] == "marginal"      # not a rotation crop
    assert rec.ph_check({"ph_optimum": [6.0, 7.0]}, 6.3)["status"] == "ok"
    assert rec.ph_check({"ph_optimum": [6.0, 7.0]}, 5.7)["status"] == "marginal"
    assert rec.ph_check({"ph_optimum": [6.0, 7.0]}, 5.0)["status"] == "limit"
    c = {"min_frost_free_days": 120, "sowing_start_month": 4, "sowing_end_month": 5}
    assert rec.sowing_dates(c, "04-26") == {"from": "04-27", "to": "05-31", "basis": "day after the 1-in-10-year last spring frost"}
    assert rec.sowing_dates(c, "03-10")["from"] == "04-01"
    assert rec.sowing_dates(c, "06-10")["from"] is None
    wheat = {"min_frost_free_days": None, "sowing_start_month": 9, "sowing_end_month": 10}
    assert rec.sowing_dates(wheat, "04-26") == {"from": "09-01", "to": "10-31", "basis": "catalogue sowing window (winter or perennial crop)"}


def test_recommend_endpoint_logic(key):
    out = sim.recommend(key)
    assert len(out["crops"]) == 15
    groups = [x["group"] for x in out["crops"]]
    order = {"recommended": 0, "possible": 1, "not_recommended": 2}
    assert [order[g] for g in groups] == sorted(order[g] for g in groups)    # grouped in order
    hot = sim.recommend(key, -30, 3.0)
    n_ok = lambda o: sum(x["group"] == "recommended" for x in o["crops"])    # noqa: E731
    assert n_ok(hot) <= n_ok(out)                                             # harsher climate never adds options


def test_no_login_fallback_helpers():
    from backend.sources.soil_sda import usda_texture
    from backend.sources.cdl_cropscape import to_albers
    assert usda_texture(40, 20) == "loam"
    assert usda_texture(90, 5) == "sand"
    assert usda_texture(10, 30) == "silty clay loam"
    assert usda_texture(20, 50) == "clay"
    assert usda_texture(65, 10) == "sandy loam"
    x, y = to_albers(-96.0, 23.0)                       # EPSG:5070 origin
    assert abs(x) < 1e-6 and abs(y) < 1e-6
    x, y = to_albers(-93.77, 42.02)                     # Ames, IA (checked against CropScape: returns Corn/Soybeans)
    assert 150_000 < x < 220_000 and 2_080_000 < y < 2_150_000


def test_catalogue_corrections_are_traceable():
    from backend.crops import load_catalog
    cat = {c["id"]: c for c in load_catalog()["crops"]}
    corn = cat["corn_maize"]
    assert corn["gdd_required"] == 1200 and corn["kc_avg"] == 0.85 and corn["ky"] == 1.25
    fix = next(c for c in corn["corrections"] if c["field"] == "gdd_required")
    assert fix["was"] == 1500 and fix["now"] == 1200 and fix["reason"]
    assert cat["sugar_beet"]["min_frost_free_days"] is None          # frost tolerant
    for c in cat.values():                                            # every crop has the water parameters
        assert c.get("kc_avg") and c.get("ky"), c["id"]


def test_rotation_plan_alternates_nitrogen():
    from backend import recommend as rec
    cat = {"corn": {"id": "corn", "name_en": "Corn", "n_balance_kg_ha": -140},
           "soy": {"id": "soy", "name_en": "Soybean", "n_balance_kg_ha": 35},
           "wheat": {"id": "wheat", "name_en": "Wheat", "n_balance_kg_ha": -90},
           "grape": {"id": "grape", "name_en": "Grape", "n_balance_kg_ha": -20, "perennial": True}}
    it = lambda cid, g="recommended": {"crop_id": cid, "crop": cat[cid]["name_en"], "group": g,  # noqa: E731
                                        "group_without_rotation": g, "grown_here_years": 0}
    items = [it("corn"), it("soy"), it("wheat"), it("grape")]
    p = rec.rotation_plan(items, cat, prev_crop=cat["corn"], prev_year=2024, start_year=2027)
    roles = [y["role"] for y in p["years"]]
    assert roles == ["adds", "uses", "adds", "uses"]                 # after corn: legume first, then alternate
    assert p["years"][0]["crop"] == "Soybean" and p["years"][0]["year"] == 2027
    assert "Grape" not in [y["crop"] for y in p["years"]]            # perennials are not rotated
    assert p["n_saved_kg_ha"] == 70                                  # two legume credits used
    p2 = rec.rotation_plan(items, cat, prev_crop=cat["soy"], prev_year=2024)
    assert p2["years"][0]["role"] == "uses"                          # after a legume: a nitrogen user
    no_leg = rec.rotation_plan([it("corn"), it("wheat")], cat, prev_crop=cat["corn"])
    assert "cover crop" in no_leg["summary"] and no_leg["years"][0]["crop"] == "Wheat"


def test_unknown_crop(key):
    with pytest.raises(sim.UnknownCrop):
        sim.simulate(key, crop_id="banana")


def test_missing_baseline_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "c")
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "d")
    sim.clear_simulation_cache()
    with pytest.raises(sim.BaselineNotCached):
        sim.simulate("missing")
