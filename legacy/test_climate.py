"""Pruebas sin red. Ejecutar: python -m pytest tests -q (desde la carpeta del módulo)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from et0 import et0_pm, extraterrestrial_radiation  # noqa: E402
from indicators import add_derived, frost_dates, monthly_climatology, trends  # noqa: E402
from power import parse_power  # noqa: E402


def test_ra_fao56_example8():
    # FAO-56 Ejemplo 8: 20°S, 3 de septiembre (día 246) -> Ra = 32.2 MJ/m²/día
    assert abs(extraterrestrial_radiation(-20, 246) - 32.2) < 0.1


def test_et0_fao56_example18():
    # FAO-56 Ejemplo 18: Uccle (Bruselas), 6 de julio -> ET0 = 3.9 mm/día
    et0 = et0_pm(tmax=21.5, tmin=12.3, rs=22.07, u2=2.078, lat_deg=50.8,
                 doy=187, elevation_m=100, ea=1.409)
    assert abs(float(et0) - 3.9) < 0.1


def _synthetic(years=(2001, 2015), seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[1]}-12-31", freq="D")
    doy = idx.dayofyear.values
    season = np.cos(2 * np.pi * (doy - 200) / 365)          # 1 en julio, -1 en enero
    tmax = 24 + 11 * season + rng.normal(0, 2, len(idx))
    tmin = 9 + 9 * season + rng.normal(0, 2, len(idx))
    rain = np.where((season < 0) & (rng.random(len(idx)) < 0.2),
                    rng.gamma(1.2, 8, len(idx)), 0.0)
    return pd.DataFrame({
        "T2M_MAX": tmax, "T2M_MIN": tmin, "T2M": (tmax + tmin) / 2,
        "T2MDEW": tmin - 3, "RH2M": 50 - 15 * season,
        "PRECTOTCORR": rain, "ALLSKY_SFC_SW_DWN": 18 + 10 * season, "WS2M": 2.0,
    }, index=idx)


def test_parse_power_replaces_fill():
    payload = {"properties": {"parameter": {
        "T2M_MAX": {"20200101": 12.0, "20200102": -999.0}}}}
    df = parse_power(payload)
    assert np.isnan(df.loc["2020-01-02", "T2M_MAX"])


def test_monthly_climatology_shape_and_physics():
    d = add_derived(_synthetic(), lat=36.34, elevation_m=90)
    rows = monthly_climatology(d)
    assert [r["month"] for r in rows] == list(range(1, 13))
    jan, jul = rows[0], rows[6]
    assert jul["et0Mm"] > jan["et0Mm"]                     # verano evapora más
    assert jul["heatDays"] > jan["heatDays"]
    assert jan["frostDays"] >= jul["frostDays"]
    assert jul["waterBalanceMm"] < 0                       # déficit en verano
    for r in rows:
        for k in ("precipMm", "tMaxC", "tMinC", "frostDays", "heatDays", "et0Mm"):
            assert r[k] is not None


def test_missing_inputs_give_nan_not_invented():
    df = _synthetic()
    df.loc["2005-07-01":"2005-07-31", "ALLSKY_SFC_SW_DWN"] = np.nan
    d = add_derived(df, 36.34, 90)
    assert d.loc["2005-07-15", "ET0"] != d.loc["2005-07-15", "ET0"]   # NaN


def test_frost_dates_and_trends():
    d = add_derived(_synthetic(), 36.34, 90)
    fd = frost_dates(d)
    assert fd["lastSpringFrostDoyMedian"] is None or fd["lastSpringFrostDoyMedian"] < 200
    tr, yearly = trends(d)
    assert tr["tMaxC"]["years"] == 15


def test_sowing_windows_blocks_cold_soil():
    from forecast import sowing_windows
    days = ["2026-03-01", "2026-03-02"]
    data = {"daily": {"time": days, "temperature_2m_min": [6, 6],
                      "temperature_2m_max": [20, 22], "precipitation_sum": [0, 0],
                      "et0_fao_evapotranspiration": [2, 2]},
            "hourly": {"time": [f"{days[0]}T{h:02d}:00" for h in range(24)]
                       + [f"{days[1]}T{h:02d}:00" for h in range(24)],
                       "soil_temperature_6cm": [8.0] * 24 + [12.0] * 24}}
    sw = sowing_windows(data)["days"]["tomate_industria"]
    assert sw[0]["suitable"] is False and sw[1]["suitable"] is True
