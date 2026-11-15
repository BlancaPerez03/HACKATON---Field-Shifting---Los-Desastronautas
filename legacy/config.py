"""Configuración del módulo de clima (persona 1).

Todo umbral lleva una etiqueta:
  - "estandar": definición reconocida (FAO-56, índices ETCCDI de la OMM).
  - "hipotesis": valor razonable elegido por el equipo; debe validarlo un agrónomo local.
Cambiad aquí los valores, nunca dentro del código.
"""

# Finca piloto: zona del UC West Side Research & Extension Center (Five Points, Fresno County).
# VERIFICAD las coordenadas con el polígono que fije la persona 3 (mapa).
FARM = {
    "name": "Finca piloto Five Points (Fresno County, CA)",
    "lat": 36.34,
    "lon": -120.11,
    # Altitud en metros. Si es None se usa la que devuelve POWER (rejilla MERRA-2, poco precisa).
    # Mejor: la altitud SRTM que calcula la persona 2.
    "elevation_m": None,
    "timezone": "America/Los_Angeles",
}

# Periodo histórico. 2001-2025 = 25 años completos.
PERIOD = {"start": 2001, "end": 2025}

THRESHOLDS = {
    "frost_tmin_c": {"value": 0.0, "kind": "estandar",
                     "note": "Día de helada: Tmin < 0 °C (índice FD de ETCCDI)."},
    "heat_tmax_c": {"value": 35.0, "kind": "hipotesis",
                    "note": "Día de calor extremo para cultivos de verano. Validar por cultivo con UC ANR."},
    "very_heavy_precip_mm": {"value": 20.0, "kind": "estandar",
                             "note": "Día de lluvia muy intensa: P >= 20 mm (índice R20mm de ETCCDI)."},
    "wet_day_mm": {"value": 1.0, "kind": "estandar",
                   "note": "Día con lluvia: P >= 1 mm (ETCCDI)."},
    "gdd_base_c": {"value": 10.0, "kind": "hipotesis",
                   "note": "Base de grados-día. Común para cultivos de verano; la persona 4 ajusta por cultivo."},
    "gdd_cap_c": {"value": 30.0, "kind": "hipotesis",
                  "note": "Techo de grados-día (método de techo horizontal)."},
}

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# Comunidad AG: radiación en MJ/m²/día, lista para FAO-56.
POWER_PARAMS = [
    "T2M_MAX", "T2M_MIN", "T2M",   # °C
    "T2MDEW",                      # punto de rocío, °C (mejor vía para presión de vapor en FAO-56)
    "RH2M",                        # %
    "PRECTOTCORR",                 # mm/día (precipitación corregida)
    "ALLSKY_SFC_SW_DWN",           # MJ/m²/día
    "WS2M",                        # m/s a 2 m
]

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Earth Engine: colección mensual de IMERG V07. VERIFICAD el ID en el catálogo de GEE antes de usarla.
GEE_IMERG_MONTHLY = "NASA/GPM_L3/IMERG_MONTHLY_V07"
