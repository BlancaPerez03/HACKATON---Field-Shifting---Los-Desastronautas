# Módulo 1 · Clima de la finca (FarmShift AI)

Genera `climate.json` con la climatología mensual, heladas, tendencias y ventana de siembra
de la finca piloto (Five Points, Fresno County, CA).

## Puesta en marcha

```bash
pip install -r requirements.txt
python -m pytest tests -q          # 7 pruebas, sin red
python build_climate.py            # descarga POWER (25 años, ~1 min) + previsión Open-Meteo
python build_climate.py --imerg    # opcional: contraste con GPM IMERG en Earth Engine
cp data/climate.json ../../public/data/climate.json   # para la app
```

Mientras no tengáis el dato real, el equipo usa `mock/climate.mock.json` (`"isMock": true`).

## Fuentes

| Fuente | Uso en el módulo | Acceso | Resolución | Tipo |
|---|---|---|---|---|
| NASA POWER (diario, comunidad AG) | Temperatura, lluvia, humedad, radiación, viento → todos los indicadores | Sin clave | ~0.5° × 0.625° (~50 km) | Observado (reanálisis + satélite) |
| GPM IMERG mensual V07 (Earth Engine) | Segunda estimación de lluvia para medir incertidumbre | Cuenta GEE + proyecto Cloud | ~0.1° (~10 km) | Observado (satélite) |
| Open-Meteo | Previsión 16 días y temperatura del suelo → "¿cuándo sembrar?" | Sin clave (no comercial) | Modelo meteorológico | Previsión, no NASA |

OpenLandMap, SRTM y FAO ECOCROP **no son de este módulo** (suelo y pendiente: persona 2;
catálogo de cultivos: persona 4). Lo único que necesito de la persona 2 es la altitud SRTM
de la finca, que va en `config.py → FARM["elevation_m"]`.

## Qué calcula y cómo

| Campo | Cálculo | Base |
|---|---|---|
| `precipMm`, `tMaxC`, `tMinC` | Media entre años de cada mes | Directo de POWER |
| `et0Mm` | Penman-Monteith diario, sumado por mes | FAO-56 (validado con su Ejemplo 18) |
| `waterBalanceMm` | Lluvia − ET0 | Negativo = el riego debe cubrir el déficit |
| `frostDays` | Días con Tmin < 0 °C | ETCCDI (FD) |
| `heatDays` | Días con Tmax ≥ 35 °C | **Hipótesis**, validar por cultivo |
| `heavyRainDays` | Días con P ≥ 20 mm | ETCCDI (R20mm) |
| `gdd` | Grados-día base 10 °C, techo 30 °C | **Hipótesis**, ajustar por cultivo |
| `precipP10Mm` / `P90` | Mes seco / húmedo de 1 de cada 10 años | Percentiles |
| `frost` | Fecha mediana y extrema de última/primera helada | Día del año |
| `trends` | Pendiente lineal por década | Descriptivo, no predicción |
| `dryYears` | Años bajo el percentil 20 de lluvia | Base para el simulador (persona 5) |
| `sowingForecast` | Días aptos de los próximos 16 por cultivo | Reglas **orientativas** |

Reglas de honestidad: un mes con menos de 20 días válidos sale como `null`; un día sin algún
insumo de ET0 no se rellena. Todo umbral está en `config.py` con su etiqueta `estandar` o `hipotesis`.

## Checklist de la primera hora

- [ ] `python build_climate.py` descarga POWER sin error.
- [ ] Comprobar 3 valores (p. ej. lluvia de enero, Tmax de julio) contra el visor web de POWER.
- [ ] Confirmar coordenadas con la persona 3 y la altitud SRTM con la persona 2.
- [ ] Si usáis Earth Engine: verificar en el catálogo el ID `NASA/GPM_L3/IMERG_MONTHLY_V07`.
- [ ] Subir `data/climate.json` y la caché `data/raw/` al repositorio (la demo funciona sin red).

## Limitaciones que deben aparecer en la app

- ~50 km de resolución: representa la comarca, no la parcela.
- En Fresno casi toda el agua del cultivo es de riego; la lluvia importa sobre todo en invierno.
- Las heladas por inversión térmica en zonas bajas pueden no verse; contrastar con CIMIS.
