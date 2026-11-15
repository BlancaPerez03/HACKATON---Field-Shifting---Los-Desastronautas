# Field Shift: módulo 5, mapa interactivo y simulador de escenarios (Space Apps 2026)

Modelo: Opus 5.5 en esfuerzo medio. Motivo: integra frontend, backend y Earth Engine con decisiones de honestidad
científica (escala, tipo de dato, qué se puede recalcular) bajo un plazo cerrado. Subagente: Haiku 5.5 solo para
mapear el repositorio. Sube a esfuerzo alto únicamente si un bloque falla dos veces.

## 0. Plazo y regla de prioridad

- **El envío cierra el domingo 15 de noviembre de 2026 a las 23:59, hora local.** El domingo por la tarde queda
  libre para el vídeo de 30 segundos o las diapositivas.
- Antes de empezar, mira la hora. Trabaja por prioridades (§11): termina P0 entero antes de tocar P1, y P1 antes de
  P2. Si quedan menos de 6 horas hasta el domingo a las 14:00, haz solo P0 y dilo.
- Para después de cada bloque e imprime un estado corto para el equipo. No esperes aprobación salvo bloqueo real.

## 1. Qué hay que construir

Un visor 2D con las parcelas, cuatro capas ambientales y un simulador de escenarios con tres controles (lluvia,
temperatura, riego). Mover un control recalcula los indicadores del escenario **con las mismas fórmulas del
backend**, sin recargar la página, y pinta sobre la parcela **zonas de riesgo** derivadas del relieve. La
comparación antes/después es siempre visible.

El valor ante el jurado (Validity y Relevance): **el simulador no inventa números.** Recalcula lo que sí se puede
recalcular a partir de las series diarias de NASA POWER y del relieve de NASADEM, y dice en pantalla qué es
observado, qué es reanálisis o modelo, qué es derivado y qué es hipotético.

## 2. Lo que ya existe (verificado el 14-11-2026)

Lee primero, en este orden: `CLAUDE.md`, `README.md`, este prompt, `DOSSIER-field-shift.md` (§5.3 contrato, §5.6
teselas, §6 indicadores derivados, §8 fuentes) y `PROMPT-field-shift-backend.md`. Después comprueba en el código
cada punto de esta lista; no des nada por existente porque figure en un Markdown.

- **Backend Python 3.11+, FastAPI** en `backend/`. Endpoint `POST /api/parcel/analyze`, contrato v1 (dossier §5.3).
  Cada indicador lleva `source.ids`, `nasa`, `data_type`, `resolution_m`, `scale_note`, `method`, `thresholds`,
  `confidence`, `confidence_reason` y `warnings` con códigos estables. Caché por hash de geometría y fechas.
- **`backend/derived.py`** contiene funciones puras ya probadas (25 tests): `daily_et0` (Penman-Monteith FAO-56 con
  Hargreaves de respaldo), `frost_dates`, `monthly_day_counts`, `water_balance`, `precip_extremes`, `bare_months`,
  `vulnerability`, `slope_factor`, `erodibility_factor`, `erosivity_factor`, `cover_factor` y `erosion_index`.
  **El simulador las reutiliza; no las reescribas en JavaScript.**
- **NASA POWER funciona con datos reales** (API v2.10.3; dos parcelas de demo en 5 a 8 s). Las series diarias quedan
  en la caché de disco `.cache/power/` (clave: celda MERRA-2 + fechas + parámetros).
- **Módulos de Earth Engine** (`landsat.py`, `smap.py`, `terrain.py`, `soil.py`, `croptype.py`): escritos; comprueba
  si ya funcionan con `EE_PROJECT_ID`. Las teselas (`getMapId`) **no están implementadas**.
- **Parcelas de demo**: `backend/demo_parcels.geojson`, dos rectángulos aproximados en EE. UU. (oeste de Ames, Iowa,
  y Ashland Bottoms, Kansas). No son lindes reales; trátalas como **ejemplos aproximados** y etiquétalas así.
- **No hay puntuación de rotaciones en este backend.** Busca en el repositorio si el módulo de rotaciones del equipo
  existe y expone puntuaciones. Si no existe, el simulador **no muestra puntuaciones** (§6.4).
- **Frontend:** desconocido. Puede no existir. Averígualo en la auditoría.
- **Entorno del equipo: Windows, PowerShell, VS Code.** Usa `python` (no `python3`) y `.venv\Scripts\Activate.ps1`
  en todas las instrucciones que des.

## 3. Fase A: auditoría (máximo 20 minutos)

Lanza el subagente Haiku 5.5, solo lectura, sin tocar archivos. Respuesta en 30 líneas como máximo:

- framework frontend, versión de Node (`node --version`) si hay, gestor de paquetes, librería de mapas, estado
  global, estilos, componentes de mapa y de selección de parcelas existentes;
- rutas del backend, si existe `layers.json`, `simulate()`, `modules/simulate` o un módulo de rotaciones con
  puntuaciones;
- dónde se sirven los estáticos.

Con eso, decide el stack y escríbelo en una línea:

1. **Si hay frontend con librería de mapas:** úsalos. No añadas otra librería de mapas ni de UI.
2. **Si hay frontend sin mapa:** añade MapLibre GL JS (ráster, vector, `canvas`/`image` sources y terreno en una
   sola librería).
3. **Si no hay frontend:** crea `frontend/` como página estática (HTML, CSS y módulos JS, sin paso de build) servida
   por FastAPI con `StaticFiles`, y MapLibre GL JS en versión fijada. Si hay Node y el equipo lo prefiere, Vite +
   TypeScript vale igual. No metas React solo para esto.

Imprime: qué reutilizas, qué archivos crearás o tocarás, y el stack elegido con su motivo.

## 4. Visor 2D (P0)

### 4.1 Mapa y parcelas

- **Una sola instancia del mapa** durante toda la sesión. Mover controles, cambiar fecha o capas nunca la recrea.
  Centro, zoom y selección se conservan.
- Mapa base sin claves privadas en el frontend. Verifica sus condiciones de uso y pon su atribución. Si usas
  imagen satélite como base, indícalo en la atribución; no es un dato de análisis.
- Pan, zoom (ratón, gestos, botones), botón "encuadrar selección", escala métrica.
- Parcelas como polígonos GeoJSON: selección simple y múltiple (clic y Mayús+clic, o casillas en una lista), estado
  resaltado, nombre, superficie (`request.area_ha`) y estado de datos (`served_from`: live, cache o demo_cache).
- Las parcelas de demo llevan la etiqueta "ejemplo aproximado". No inventes lindes reales.

### 4.2 Herramientas de cursor y uso (P0 las dos primeras, P1 el resto)

1. **Inspector bajo el cursor (P0):** al pasar el ratón (o tocar en móvil), un panel fijo muestra el valor de cada
   capa visible en ese punto, con unidad, fecha, fuente, `data_type` y `scale_note`. Para capas de zona dice "valor
   de la zona de ~N km", nunca "valor en este punto".
2. **Cursor contextual (P0):** puntero en parcelas seleccionables, mira de precisión sobre capas con inspector,
   cursor de dibujo en modo dibujo.
3. **Dibujar o importar parcela (P1):** dibujar un polígono o soltar un archivo GeoJSON llama a
   `POST /api/parcel/analyze`, muestra el progreso por módulo y añade la parcela a la lista. Respeta las validaciones
   del backend (geometría válida, ≤ 2.000 vértices, ≤ 1.000 ha) y muestra sus códigos de error en lenguaje claro.
4. **Escenarios predefinidos (P1):** botones que solo colocan los deslizadores, p. ej. "Seco moderado" (−15 %,
   +1,0 °C) y "Seco y cálido" (−25 %, +2,5 °C). Son ajustes de controles, no proyecciones; dilo en su tooltip.
5. **Estado en la URL (P1):** parcelas seleccionadas, capas, opacidades, fecha y controles en los parámetros de la
   URL, para compartir una vista exacta y para grabar el vídeo.
6. **Exportar (P2):** descargar el resultado del escenario en JSON (con `provenance`) y una captura PNG del mapa
   con el aviso fijo y la leyenda incluidos.
7. **Teclado y accesibilidad (P0 en los controles):** deslizadores operables con flechas y Re Pág/Av Pág, foco
   visible, `aria-valuetext` con unidad ("−20 % de lluvia"), contraste AA, ningún dato solo por color.

### 4.3 Cuatro capas ambientales

Cada capa respeta su resolución real. **Nunca conviertas un dato de zona o de punto en un mapa de parcela.** Los
píxeles gruesos se pintan gruesos (remuestreo `nearest`, sin suavizado).

| # | Capa | Fuente | Tipo (`data_type`) | Resolución real | Representación honesta | Temporalidad |
|---|---|---|---|---|---|---|
| 1 | NDVI | Landsat 8/9 C2 L2 | satellite | 30 m | Teselas de la mediana mensual enmascarada (`getMapId`) | Meses con observaciones válidas |
| 2 | Humedad radicular | SMAP L4 `sm_rootzone` | model (asimila satélite) | ~9-11 km | Teselas de la media mensual con píxeles visibles de ~11 km, o el píxel como polígono | Meses disponibles (la copia de GEE va con retraso) |
| 3 | Precipitación | NASA POWER `PRECTOTCORR` | reanalysis | 0,5° × 0,625° | **La celda MERRA-2 como polígono** (~50 × 60 km), coloreada con el total mensual. Sin teselas | Meses del periodo analizado |
| 4 | Pendiente | NASADEM | satellite (radar) | 30 m | Teselas de pendiente en grados | Estática: sin selector de fecha |

Opcional P2 para la capa 3: totales mensuales de GPM IMERG V07 como teselas reales de 0,1° (`satellite_gauge_merged`,
provisional desde 2025-10), etiquetados como contraste.

Cada capa muestra en su ficha: id, nombre, descripción, fuente con su ID de catálogo, `nasa`, tipo, resolución,
unidad, `scale_note`, periodo, fechas disponibles, leyenda, opacidad y avisos (p. ej. `NDVI_NOT_FERTILITY`,
`ZONE_SCALE_DATA`, `DATA_LAG`, `PARCEL_SMALLER_THAN_PIXEL`).

### 4.4 `layers.json` y teselas

- `layers.json` guarda **solo metadatos estables**: id, fuente, tipo, resolución, unidad, estilo, rango de la
  leyenda y paleta, avisos, modalidad (`real` o `demo`) y cómo se representa (`tiles`, `zone_polygon`,
  `parcel_fill`).
- Las URLs de teselas **no van en `layers.json`**: caducan en "unas horas". Añade al backend
  `GET /api/parcel/layers?hash=<geometry_hash>&layer=<id>&month=<YYYY-MM>`, que devuelve `tile_url`,
  `expires_at_estimate` y la leyenda. El frontend la vuelve a pedir si una tesela falla o si la URL ha caducado.
- Las fechas disponibles salen de la respuesta de `analyze` (meses con `valid_observations > 0` en NDVI, meses con
  dato en SMAP y POWER), no de un calendario fijo.

### 4.5 Panel de capas

- Activar y desactivar cada capa por separado; opacidad de 0 a 100 % aplicada con `setPaintProperty`, sin volver a
  pedir datos.
- Leyenda desplegable con unidad, rango y paleta, y una etiqueta de tipo: **Observado**, **Reanálisis**,
  **Modelo** o **Derivado**.
- Estados por capa: cargando, sin datos en esa fecha, error, caducada (con reintento). Un fallo en una capa no
  bloquea el mapa ni el simulador.

### 4.6 Selector temporal

- Selector de mes por capa temporal, limitado a los meses con dato; los meses sin dato aparecen deshabilitados con
  su motivo.
- La pendiente no tiene selector.
- Distingue en pantalla **"Fecha de observación"** (las capas) de **"Escenario hipotético"** (el simulador). Los
  deslizadores no cambian la fecha de las capas observadas.

## 5. Simulador (P0)

### 5.1 Principio: el método del delta sobre las series reales

El escenario no es una predicción ni una proyección climática. Es la serie histórica de la parcela (10 años de
POWER diario) **perturbada de forma uniforme**, con las fórmulas del backend aplicadas de nuevo. Así cada número
modificado tiene el mismo método, la misma fuente y la misma trazabilidad que el original.

- **Lluvia, de −30 % a 0 %, paso 1 %, inicio 0 %:** P'(día) = P(día) × (1 + ΔP). Se recalculan el balance
  P − ET0 mensual, los meses con déficit, el déficit anual medio, R95p, R20mm, Rx1day y, con ellos, el factor de
  erosividad.
- **Temperatura, de 0 a +3,0 °C, paso 0,1 °C, inicio 0 °C:** se suma ΔT a `T2M`, `T2M_MAX` y `T2M_MIN` de cada
  día. Se recalculan los días de calor (Tmax ≥ umbral), los días con Tmin ≤ 0 °C y ≤ 2 °C, las fechas de helada
  P10/P50/P90 y la ET0 (y con ella el balance).
  - Supuesto que hay que declarar en la respuesta: **el punto de rocío se mantiene**, así que el déficit de presión
    de vapor aumenta. Es la opción conservadora; si el equipo prefiere mantener la humedad relativa, es un
    parámetro.
  - Desplazar toda la serie conserva su variabilidad. No es una proyección validada y no cambia la frecuencia de
    las olas de calor más allá de lo que implica el desplazamiento. Dilo.
- **Riego, disponibilidad hipotética de 0 a 100 %, paso 5 %:** no hay modelo físico ni datos medidos, así que no
  es un volumen.
  - Regla: en cada mes con P' − ET0' < 0, la fracción elegida del déficit se considera cubierta. El déficit
    restante es déficit × (1 − disponibilidad). Al 100 % el déficit queda en cero y nada mejora más allá de eso.
  - El riego **no** cambia el calor, las heladas ni la erosión, y no se modela la eficiencia ni la lámina aplicada.
  - Por defecto la parcela es **de secano y el control está desactivado**, con una casilla "Suponer riego
    disponible (hipótesis)". La etiqueta dice "Disponibilidad hipotética de riego (% del déficit cubierto), DEMO".

Los tres controles actúan sobre **el mismo escenario**: una sola llamada con los tres parámetros, nunca puntuaciones
sumadas por separado.

### 5.2 Dónde se calcula

- Añade `backend/simulate.py`, puro, sin red. Lee las series diarias de POWER desde la caché de disco (o desde el
  demo cache), aplica los deltas y llama a las funciones de `derived.py`. La salida con los tres controles a cero
  debe ser **idéntica** a los indicadores de `analyze`; compruébalo.
- Expón `POST /api/parcel/simulate` con
  `{"geometry_hash", "start_date", "end_date", "delta_precip_pct", "delta_temp_c", "irrigation_availability_pct", "irrigation_enabled"}`.
  No consulta NASA ni Earth Engine: solo la caché. Si la caché no tiene la parcela, devuelve 409 con
  `{"code": "BASELINE_NOT_CACHED"}` y el frontend llama antes a `analyze`.
- Memoiza en el servidor por parámetros redondeados al paso de cada control.
- `scripts/build_demo_cache.py` debe guardar también las series diarias que necesita `simulate` y la rejilla de
  relieve de §5.5, para que la demo funcione sin red ni cuota.

### 5.3 Contrato de `simulate` (versión `sim-1`)

```json
{
  "version": "sim-1",
  "mode": "real | demo",
  "scenario": {"delta_precip_pct": -20, "delta_temp_c": 2.0, "irrigation_enabled": true,
               "irrigation_availability_pct": 60},
  "assumptions": ["Uniform delta applied to the 2016-2025 POWER daily series", "Dew point held constant", "..."],
  "baseline": {"water_balance": {}, "heat": {}, "frost": {}, "precip_extremes": {}, "erosion_index": {}},
  "scenario_result": {"water_balance": {}, "heat": {}, "frost": {}, "precip_extremes": {}, "erosion_index": {}},
  "deltas": [{"indicator": "mean_annual_deficit_mm", "baseline": -365.2, "scenario": -512.8, "change": -147.6,
              "unit": "mm", "direction": "worse"}],
  "risk_zones": {"grid_ref": "<hash>", "classes": {}, "summary": {}},
  "explanation": ["..."],
  "unchanged": ["NDVI history", "Soil properties", "Slope"],
  "warnings": [{"code": "HYPOTHETICAL_SCENARIO", "message": "Hypothetical scenario, not a prediction."}],
  "data_gaps": [],
  "provenance": {"sources": ["NASA POWER", "NASA/NASADEM_HGT/001"], "rules_version": "sim-1",
                 "ai_assistance": "..."},
  "timing_ms": {"server": 0}
}
```

Para varias parcelas seleccionadas: un resultado por parcela, nunca una media que mezcle celdas POWER distintas.

### 5.4 Indicadores y "puntuaciones"

- Muestra los indicadores que el motor sí recalcula: déficit anual medio, meses con déficit, días de calor por mes,
  días de helada, fechas de helada, ET0 anual, Rx1day, R95p y el índice relativo de erosión (bajo, medio o alto con
  su desglose).
- **Puntuaciones:** si la auditoría encuentra un módulo de rotaciones con puntuación documentada, pásale los
  indicadores modificados y muestra su puntuación base y modificada con su escala. Si no existe, **no hay
  puntuación**: el panel compara indicadores. No crees una puntuación nueva para que el simulador parezca más
  completo.
- Cuando falte un dato (p. ej. sin Earth Engine no hay pendiente), el indicador sale como `null` con su motivo.
  Recuerda: el índice de erosión no da nivel con menos de 3 de sus 4 factores.
- Prohibido: rendimientos, probabilidades, porcentajes de éxito, pérdidas económicas.

### 5.5 Zonas de riesgo sobre el terreno (simulación ligera)

Dentro de la parcela solo hay variación espacial real donde hay datos de 30 m: el relieve (NASADEM). Las zonas de
riesgo combinan **variables por píxel** (relieve) con **factores de parcela o de zona** que cambian con el
escenario. Lo que es de zona se dice; no se fabrica variación dentro de la parcela.

**Datos estáticos, una sola vez por parcela (Earth Engine, P0 si Earth Engine funciona):**
`GET /api/parcel/terrain-grid?hash=` devuelve una rejilla compacta recortada a la parcela a 30 m (≤ 1.000 ha son
unos 11.000 píxeles): `bbox`, `rows`, `cols`, `nodata`, y por píxel `slope_deg` y `tpi_m` (elevación menos la media
focal en un radio de 150 m, configurable). Se cachea en disco y en el demo cache.

**Recombinación por escenario (en `simulate.py`, sin Earth Engine; o en el cliente con las mismas reglas
exportadas como JSON):**

1. **Riesgo de erosión por escorrentía:** en cada píxel, `erosion_index` usando `slope_factor(pendiente del píxel)`
   y los factores de parcela del escenario (erosividad con la lluvia modificada, erosionabilidad de OpenLandMap y
   cobertura de los meses desnudos). Las clases bajo/medio/alto son las mismas de `derived.py`. Dentro de la
   parcela solo varía por la pendiente; la leyenda lo dice. Texto fijo: "Relative screening index; not a soil-loss
   estimate".
2. **Posible acumulación de aire frío:** píxeles con `tpi_m` ≤ −1 m (configurable) y pendiente baja, solo si el
   escenario conserva días con Tmin ≤ 0 °C. La intensidad depende del número de días de helada del escenario.
   Aviso fijo: la helada sale del aire a 2 m en una celda de ~50 km; el relieve solo indica dónde podría ser peor.
   Si se usa, cita la heurística de TPI como regla propia de cribado, no como modelo validado.
3. **Estrés hídrico:** es un dato de zona (POWER, y SMAP como contexto). Se muestra como borde o rayado de toda la
   parcela con el déficit del escenario, nunca como zonas internas.

Render: una fuente `canvas` o `image` de MapLibre ajustada al `bbox`, redibujada en el cliente al mover los
deslizadores, con opacidad propia, leyenda, etiqueta **"Derivado + hipotético"** y el aviso de §7. Alternancia
"Base / Escenario" o deslizador de cortinilla para comparar (P1).

Opcional P2: vista 3D ligera del terreno (fuente `raster-dem` con exageración vertical y sombreado) solo si existe
una fuente de teselas de elevación gratuita, sin clave y con condiciones de uso verificadas. Es visualización, no
análisis.

### 5.6 Interacción y carreras

1. El valor visible del control se actualiza al instante (evento `input`).
2. Debounce de unos 80 ms y una petición con **los tres** parámetros.
3. Cada petición lleva un número de secuencia y un `AbortController`. Solo se aplica la respuesta de la última; las
   anteriores se descartan.
4. Cambiar de parcela durante un cálculo cancela el cálculo pendiente.
5. **Restablecer escenario** pone los tres controles a cero y el riego en desactivado, sin tocar la selección, las
   capas, la fecha ni el encuadre.
6. Los resultados base nunca se sobrescriben: viven en un estado aparte.

Separa el estado en cuatro partes: mapa, selección, capas y escenario.

### 5.7 Explicación

Plantillas deterministas, en el idioma de la interfaz, generadas a partir de los `deltas` y con sus cifras. Sin
llamadas a un LLM. Cada frase debe poder trazarse a un delta calculado. Ejemplos de forma:

- "Con −20 % de lluvia y +2,0 °C, el déficit hídrico anual medio pasa de 365 mm a 513 mm (+148 mm)."
- "Los días con máxima ≥ 35 °C pasan de 4 a 11 al año de media."
- "La disponibilidad hipotética de riego del 60 % cubre 308 mm del déficit; no se modela la eficiencia."
- "Sin cambios: historial de NDVI, suelo y pendiente."

Si un delta es nulo o falta, la frase no se genera.

## 6. Comparación antes/después (P0)

- Dos columnas, **Base** y **Escenario**, con valor, diferencia y sentido (mejora o empeora), en cifras y texto
  además de color. Barras con la escala siempre visible.
- Bloque "Qué cambió" (explicación) y bloque "Qué no cambia".
- El mapa sigue visible: en escritorio el panel es lateral; en móvil es una hoja inferior plegable que no tapa la
  parcela seleccionada.
- Para la capa de zonas de riesgo, alternancia Base/Escenario sobre el propio mapa (P1).

## 7. Aviso fijo obligatorio

Visible siempre en el panel del simulador, también en móvil, en la vista de comparación y en el PNG exportado,
exactamente con este texto:

> Escenario hipotético, no es una predicción

No puede ir en un tooltip ni desaparecer al mover los controles. Si la interfaz está en inglés, se mantiene este
texto y se añade debajo "Hypothetical scenario, not a prediction". Además, cada número lleva su etiqueta de tipo:
Observado, Reanálisis, Modelo, Derivado o Hipotético.

## 8. Modos de datos y mocks

- **Modo real:** backend con caché.
- **Modo demo:** el demo cache de `build_demo_cache.py`, con **datos reales precalculados**. Es lo que se usa en el
  vídeo.
- **Mock:** solo si no hay backend ni demo cache. Es un `layers.json` y un `simulate()` en el cliente con el mismo
  contrato, valores marcados **"DEMO / VALORES FICTICIOS"** en pantalla y en `mode`. Sin URLs inventadas: las capas
  sin datos se pintan como relleno de la parcela con su leyenda.
- Un único adaptador (`dataSource.real | demo | mock`) aísla esto de los componentes. Un indicador en la cabecera
  muestra el modo activo. No sustituyas por mocks nada que ya funcione con datos reales.

## 9. Rendimiento

**Criterio:** con la parcela ya analizada, desde que se mueve un control hasta que se pintan los valores y las
zonas nuevas pasan **menos de 1 s**. Objetivo práctico: menos de 300 ms en local.

- Mide en el cliente con `performance.now()`: desde el evento `input` hasta el `requestAnimationFrame` posterior al
  pintado. En el servidor, cabecera `Server-Timing`.
- Prueba 20 movimientos seguidos con los tres controles, en modo real con caché y en modo demo. Informa de p50, p95,
  equipo, navegador y modo.
- Si se supera 1 s: memoiza, reduce el redibujado del `canvas`, pasa a cliente la recombinación de zonas o recorta
  el payload. No consultes NASA ni Earth Engine al mover controles.

## 10. Casos límite que deben funcionar

Cero, una o varias parcelas; parcela sin cultivo ni temporada (solo resultados ambientales); secano o riego no
especificado; capa sin datos en la fecha; tesela caducada; fallo de un módulo o de la API; movimientos rápidos de
controles; cambio de parcela durante un cálculo; parcela fuera de la cobertura de NASADEM (aviso `OUT_OF_COVERAGE` y
GLO-30, `nasa: false`); parcela menor que un píxel (`PARCEL_SMALLER_THAN_PIXEL`); sin Earth Engine (el simulador de
clima funciona; las zonas de riesgo salen con su motivo en `data_gaps`); escritorio y móvil (360 px de ancho).

## 11. Orden de trabajo

**P0, el producto mínimo para el vídeo:**

1. Auditoría y stack (§3).
2. `simulate.py` y `POST /api/parcel/simulate` sobre las series de POWER, con la comprobación base = `analyze`.
3. Mapa, parcelas, inspector bajo el cursor y panel de capas con las cuatro capas (las que no tengan teselas se
   representan como zona o relleno honesto).
4. Panel del simulador con los tres controles, restablecer, comparación, explicación y aviso fijo.
5. Rejilla de relieve y zonas de riesgo de erosión y de aire frío, si Earth Engine funciona.
6. Demo cache actualizado con series diarias y rejilla.

**P1:** teselas de NDVI, pendiente y SMAP con regeneración; selector temporal completo; dibujar o importar parcela;
escenarios predefinidos; estado en la URL; cortinilla Base/Escenario.

**P2:** IMERG como contraste; exportar JSON y PNG; vista 3D del terreno.

## 12. Restricciones

1. No reconstruyas Field Shift ni borres módulos. No toques `derived.py` salvo para añadir funciones puras nuevas;
   si cambias una existente, sus 25 tests deben seguir pasando.
2. No alteres los datos históricos: el escenario vive aparte.
3. No presentes un dato de zona como medida de la parcela ni el escenario como predicción.
4. No inventes puntuaciones, rendimientos ni probabilidades.
5. Sin credenciales en el frontend, el repositorio ni los logs.
6. Ninguna dependencia nueva sin necesidad. Como máximo, MapLibre GL JS.
7. Cada archivo nuevo escrito con IA lleva en la primera línea la cabecera "AI-assisted" del proyecto; las
   respuestas de `simulate` llevan `provenance.ai_assistance`; el README amplía "Use of AI tools" y la tabla de
   fuentes con el mapa base y cualquier fuente nueva y su licencia.
8. Commits solo cuando el equipo lo pida, en una rama de trabajo, nunca en la rama principal.

## 13. Pruebas, solo al final (decisión del propietario)

- Tests unitarios de `simulate.py`, en `tests/`:
  - con los tres controles a cero el resultado es idéntico al de `analyze`;
  - ΔT mayor da igual o más días de calor, igual o menos días de helada y más ET0;
  - ΔP negativo da igual o más déficit;
  - riego al 0 % no cambia nada y al 100 % deja el déficit en cero, sin tocar calor ni heladas;
  - la recombinación de zonas de riesgo con una rejilla pequeña de ejemplo.
- Prueba de humo: `python -m scripts.smoke --direct` sigue pasando, y un script nuevo llama a `simulate` con
  (−20 %, +2,0 °C, riego 60 %) sobre cada parcela de demo e imprime los deltas reales recortados.
- La medición de rendimiento de §9.
- Una revisión manual corta en escritorio y en móvil (herramientas de desarrollo, 360 px), con capturas.

## 14. Hecho cuando

- [ ] Mapa 2D navegable con una sola instancia, encuadre y escala.
- [ ] Parcelas seleccionables (una o varias) con nombre, superficie y estado de datos.
- [ ] Inspector bajo el cursor con valor, unidad, fuente, tipo y escala.
- [ ] Cuatro capas activables con leyenda, opacidad 0-100 %, ficha de fuente, resolución y tipo, y representación
      fiel a su escala.
- [ ] Selector temporal solo con fechas disponibles; la pendiente sin fecha.
- [ ] Lluvia de −30 a 0 %, temperatura de 0 a +3 °C y riego hipotético de 0 a 100 % con su supuesto explícito,
      combinados en una sola llamada y con restablecimiento.
- [ ] `simulate` recalcula con las fórmulas de `derived.py`; con controles a cero coincide con `analyze`.
- [ ] Zonas de riesgo de erosión y de aire frío que cambian con el escenario y dicen qué es de píxel y qué es de
      zona (o, sin Earth Engine, su motivo en `data_gaps`).
- [ ] Comparación Base/Escenario con cifras, diferencias, explicación y "qué no cambia".
- [ ] "Escenario hipotético, no es una predicción" visible siempre.
- [ ] Menos de 1 s por interacción, medido y documentado.
- [ ] Modo real, demo o mock visible y aislado en un adaptador.
- [ ] `analyze`, los 25 tests de fórmulas y la prueba de humo siguen funcionando.

## 15. Informe final

1. Funciones hechas y archivos creados o modificados.
2. Stack y librería de mapas, con el motivo.
3. Contrato real de `simulate` y de `terrain-grid`, y supuestos del método del delta.
4. Las cuatro capas: fuente, resolución, tipo, representación y si son reales, demo o mock.
5. Qué está conectado a cálculos reales y qué es ficticio.
6. Rendimiento medido (p50, p95, entorno) y pruebas ejecutadas con su salida.
7. Limitaciones, pendientes y lo que queda sin verificar.
8. Instrucciones exactas en PowerShell para arrancar el backend, abrir el visor y regenerar el demo cache.
