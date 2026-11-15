"""Reference evapotranspiration (FAO-56). NASA POWER has no ET0 product, so it is computed here.

AI-assisted: Penman-Monteith ported from the team's climate module (validated against FAO-56
Example 18); Hargreaves-Samani added with an AI coding assistant (Claude); reviewed by the team.
Reference: Allen et al. (1998), FAO Irrigation and Drainage Paper 56.
"""
import numpy as np

# ET0 = how much water a reference grass field would evaporate + transpire per day (mm/day).
# A real crop uses ET0 x Kc (its crop coefficient). NASA POWER does not provide ET0, so we compute it.
# All functions accept numpy arrays, so one call computes 10 years of daily values at once
# (vectorised maths instead of a slow Python loop).


def sat_vp(t):
    """Saturation vapour pressure (kPa). FAO-56 eq. 11."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(lat_deg, doy):
    """Ra in MJ/m2/day. FAO-56 eqs. 21-25.

    Ra is the solar energy at the top of the atmosphere. It only depends on latitude and day of
    the year (Earth-Sun distance dr, solar declination delta, sunset hour angle ws).
    """
    phi = np.radians(lat_deg)
    doy = np.asarray(doy, float)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def et0_hargreaves(tmax, tmin, lat_deg, doy, tmean=None):
    """Hargreaves-Samani ET0 (mm/day). FAO-56 eq. 52; needs no radiation or wind.

    Simpler and less accurate than Penman-Monteith: it uses the daily temperature range as a proxy
    for sunshine. We use it as a fallback (days without radiation) and as a cross-check.
    0.408 converts MJ/m2/day into mm/day of evaporated water.
    """
    tmax, tmin = np.asarray(tmax, float), np.asarray(tmin, float)
    tmean = (tmax + tmin) / 2 if tmean is None else np.asarray(tmean, float)
    ra = extraterrestrial_radiation(lat_deg, doy)
    out = 0.0023 * (0.408 * ra) * (tmean + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None))
    return np.maximum(out, 0.0)


def et0_pm(tmax, tmin, rs, u2, lat_deg, doy, elevation_m,
           ea=None, tdew=None, rh_mean=None, pressure_kpa=None):
    """FAO-56 Penman-Monteith daily ET0 (mm/day).

    Actual vapour pressure, in FAO-56 order of preference: given ea > dew point (eq. 14) >
    mean RH (eq. 19). Pressure: measured `pressure_kpa` if given, else eq. 7 from elevation.
    Accepts scalars or numpy/pandas arrays. G = 0 at daily step.
    """
    tmax, tmin = np.asarray(tmax, float), np.asarray(tmin, float)
    tmean = (tmax + tmin) / 2
    if pressure_kpa is None:
        p = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26               # eq. 7
    else:
        p = np.asarray(pressure_kpa, float)
    gamma = 0.000665 * p                                                     # eq. 8
    delta = 4098 * sat_vp(tmean) / (tmean + 237.3) ** 2                       # eq. 13
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2                                   # eq. 12

    if ea is None:
        if tdew is not None:
            ea = sat_vp(np.asarray(tdew, float))
        elif rh_mean is not None:
            ea = np.asarray(rh_mean, float) / 100 * es
        else:
            raise ValueError("Humidity missing: pass ea, tdew or rh_mean")
    ea = np.minimum(np.asarray(ea, float), es)

    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * elevation_m) * ra                                   # eq. 37
    rs = np.asarray(rs, float)
    rns = 0.77 * rs                                                          # eq. 38, albedo 0.23
    sigma = 4.903e-9
    ratio = np.clip(rs / rso, 0.25, 1.0)
    rnl = sigma * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) \
        * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * ratio - 0.35)                # eq. 39
    rn = rns - rnl                                                           # eq. 40

    # Final FAO-56 equation 6: an energy term (net radiation rn) plus an aerodynamic term
    # (wind u2 times the vapour pressure deficit es - ea, i.e. how "thirsty" the air is).
    u2 = np.asarray(u2, float)
    num = 0.408 * delta * rn + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)
