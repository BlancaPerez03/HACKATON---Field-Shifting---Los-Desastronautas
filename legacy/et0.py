"""Evapotranspiración de referencia FAO-56 Penman-Monteith (paso diario).

Referencia: Allen et al. (1998), FAO Irrigation and Drainage Paper 56, ecuaciones 6-40.
Se valida con el Ejemplo 18 de FAO-56 (tests/test_et0.py).
"""
import numpy as np


def sat_vp(t):
    """Presión de vapor de saturación (kPa). FAO-56 ec. 11."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(lat_deg, doy):
    """Ra en MJ/m²/día. FAO-56 ec. 21-25."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def et0_pm(tmax, tmin, rs, u2, lat_deg, doy, elevation_m,
           ea=None, tdew=None, rh_mean=None):
    """ET0 diaria (mm/día).

    Presión de vapor real, por orden de preferencia FAO-56:
      ea dado > desde punto de rocío (ec. 14) > desde HR media (ec. 19).
    Acepta escalares o arrays de numpy/pandas.
    """
    tmax, tmin = np.asarray(tmax, float), np.asarray(tmin, float)
    tmean = (tmax + tmin) / 2
    p = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26          # ec. 7
    gamma = 0.000665 * p                                             # ec. 8
    delta = 4098 * sat_vp(tmean) / (tmean + 237.3) ** 2               # ec. 13
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2                           # ec. 12

    if ea is None:
        if tdew is not None:
            ea = sat_vp(np.asarray(tdew, float))
        elif rh_mean is not None:
            ea = np.asarray(rh_mean, float) / 100 * es
        else:
            raise ValueError("Falta humedad: pasa ea, tdew o rh_mean")
    ea = np.minimum(np.asarray(ea, float), es)

    ra = extraterrestrial_radiation(lat_deg, np.asarray(doy))
    rso = (0.75 + 2e-5 * elevation_m) * ra                           # ec. 37
    rns = 0.77 * np.asarray(rs, float)                               # ec. 38 (albedo 0.23)
    sigma = 4.903e-9
    ratio = np.clip(np.asarray(rs, float) / rso, 0.25, 1.0)
    rnl = sigma * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) \
        * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * ratio - 0.35)        # ec. 39
    rn = rns - rnl                                                   # ec. 40; G = 0 a escala diaria

    u2 = np.asarray(u2, float)
    num = 0.408 * delta * rn + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)
