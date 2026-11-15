# Conversación: mapa selector de campos (Field Shift)

Fecha: 14 de noviembre de 2026
Proyecto: Field Shift backend (NASA Space Apps Challenge 2026)

---

## 1. Usuario

> tengo esto quiero hacer un mapa donde me pueda mover y seleccionar un lugar en el mapa y quiero que resaltes los campos de cultivo que quiero investigar

*(Pegó la lista de recursos de datos del reto. Texto completo abajo.)*

<details>
<summary>Texto pegado: recursos de datos del reto</summary>

Soil Moisture Active Passive (SMAP): SMAP provides global measurements of surface soil moisture and freeze/thaw state, collected every 2–3 days. Soil‑moisture information helps identify drought stress, water availability, infiltration potential, and early crop‑stress signals. These data are valuable for evaluating rotation crops that could improve water efficiency, soil conditions, or drought resilience.

Global Precipitation Measurement (GPM) & IMERG: The GPM mission and its IMERG product provide global precipitation rate and accumulation estimates. These help assess rainfall reliability, extreme‑storm frequency, erosion risk, water input to soils, and long‑term trends in field moisture. IMERG is valuable for comparing rotation strategies under different precipitation scenarios. (Worldview IMERG layers can be downloaded directly as high‑resolution images.)

Landsat and MODIS/VIIRS: Reflectance, NDVI, Vegetation Indices: Landsat (30‑meter resolution) and MODIS/VIIRS (250–1000 m) provide corrected reflectance, NDVI, vegetation indices, and indicators of plant stress, bare ground, and seasonal change. These datasets allow participants to map crop vigor, track seasonal transitions, detect high‑stress periods, and compare rotation options visually.

NASA POWER: Agroclimatology & Meteorological Data: NASA POWER provides accessible solar, meteorological, and climatology datasets used widely in agriculture. The datasets include temperature, humidity, radiation, and derived indicators that help estimate crop water use, growing‑season conditions, frost risk, and climate suitability for potential rotation crops.

Shuttle Radar Topography Mission (SRTM): Elevation & Terrain Models: The Shuttle Radar Topography Mission (SRTM) provides global elevation data suitable for analyzing slope, runoff, erosion risk, water flow, and terrain‑driven stress conditions. Terrain patterns help determine which rotation crops may improve infiltration, reduce erosion, or stabilize soil on slopes.

ECOSTRESS: ECOSTRESS measures land‑surface temperature (LST) and evapotranspiration (ET) at high spatial resolution. This helps detect hotspots of plant stress, heat exposure, shallow‑root vulnerability, and crop‑water demand. It is particularly useful for identifying when current crops may be becoming more vulnerable and for mapping field‑level microclimate differences.

USDA Ag Data Commons: Open Access Agricultural Datasets: USDA's Ag Data Commons provides open‑access agricultural datasets covering soils, crops, climate, land management, phenology, water quality, and ecological conditions. These datasets offer valuable ground‑based and agricultural context that can complement NASA's satellite observations. Participants may use Ag Data Commons to incorporate local crop information, soil‑property measurements, management practices, and field‑level agricultural research into their models. These data can help SI tools align NASA's environmental indicators with practical farm‑level constraints and crop‑rotation realities.

Web Soil Survey (WSS): The WSS, maintained by USDA's Natural Resources Conservation Service (NRCS), provides official U.S. soil data, including detailed soil maps, soil properties, drainage classifications, erosion risk, hydrologic ratings, and suitability for different land uses. Participants may use WSS to identify field‑specific soil characteristics—such as organic matter, texture, infiltration, and compaction risk—which can improve SI‑driven rotation recommendations. Integrating NASA Earth observations with WSS data may help teams build stronger, locally accurate interpretations of soil health and crop suitability.

Cropland Data Layer (CDL): CropScape: The USDA CDL provides annual, high‑resolution (30‑meter) cropland classifications for the United States, identifying specific crop types such as corn, soybeans, cotton, wheat, alfalfa, and more. These data can help participants examine existing crop rotations, track changes across seasons, identify bare fields, evaluate crop suitability, and compare local cropping patterns with NASA‑observed environmental conditions. The CDL can also support SI models by supplying labeled land‑cover inputs tied to real agricultural production.

PRISM Climate Data: Oregon State University: PRISM provides high‑quality climate datasets for the United States, including daily, monthly, and 30‑year climate normals for precipitation, temperature, dewpoint, frost/freeze dates, and more. Because PRISM incorporates topographic effects, it offers highly accurate climate context for local farms. Participants may use PRISM to assess long‑term climate trends, align rotation strategies with local temperature and rainfall history, and validate environmental stress indicators derived from NASA satellites.

USDA NRCS SSURGO/STATSGO2: Soil Data: SSURGO (field‑scale) and STATSGO2 (regional‑scale) provide detailed soil attributes such as texture, organic matter, drainage class, hydrologic soil group, erosion‑risk factors, restrictive layers, and water‑holding capacity. These data complement NASA observations by enabling accurate, location‑specific assessments of soil health, erosion potential, infiltration dynamics, and crop suitability. Integrating SSURGO with NASA datasets can help SI models produce more grounded and agronomically meaningful rotation suggestions.

National Agriculture Imagery Program (NAIP): NAIP provides high‑resolution (typically 1‑meter) aerial imagery captured during the U.S. growing season. These images allow participants to map field boundaries, detect bare soil periods, observe crop development, monitor land‑management changes, and assess vegetation cover at fine spatial scales. NAIP imagery can serve as a powerful input for training SI models that require closer‑than‑satellite detail or for validating crop and soil‑condition patterns detected from NASA Earth observations.

USGS National Land Cover Database (NLCD): NLCD offers land‑cover and land‑use classifications at 30‑meter resolution across multiple decades. This dataset helps identify farmland, pasture, forested areas, water bodies, wetlands, and development zones near agricultural fields. Participants may use NLCD to contextualize landscape features that influence microclimates, water availability, erosion risk, and pest dynamics. NLCD also supports long‑term analysis of land‑cover change and its relationship to farm vulnerability.

NLDAS/GLDAS: Land Data Assimilation Systems: NLDAS and GLDAS combine satellite and ground‑based meteorological observations to generate gridded datasets of temperature, precipitation, soil moisture, evapotranspiration proxies, radiation, and other surface variables at sub‑daily resolution. These datasets help participants study drought onset, moisture deficits, growing‑season transitions, and environmental stress conditions. When combined with NASA's mission‑based datasets, NLDAS/GLDAS can enhance SI models by providing continuous time‑series climate features. (search "NLDAS" or "GLDAS" within Earthdata Search.)

FAO Global Agro-Ecological Zones (GAEZ): GAEZ provides global agro‑climatic suitability layers for dozens of crops, along with soil constraints, water availability indicators, yield potentials, and land‑productivity assessments. These resources can help participants evaluate whether proposed rotation crops align with local climate and soil conditions, and compare multiple rotation scenarios from a global agronomic perspective.

CoCoRaHS: Community Rain/Snow Observations: CoCoRaHS offers crowd‑sourced daily precipitation measurements across North America. Participants may use this dataset to validate satellite rainfall estimates (such as IMERG), detect hyper‑local extreme rain events affecting specific fields, and refine model accuracy for water‑stress or irrigation‑timing predictions.

USGS National Water Information Systems (NWIS): NWIS provides long‑term records of groundwater levels, streamflow, river stages, and water‑quality measurements. These data can help participants assess water availability for irrigation, identify hydrologic stress, understand downstream erosion risks, and compare NASA‑observed moisture conditions with in‑situ observations.

USDA AMS Market News: USDA Market News publishes commodity prices, demand trends, and market conditions for crops and livestock. Participants may use these data to help determine whether proposed rotation crops have viable markets locally or regionally—an important farmer‑driven constraint when evaluating rotation strategies.

USDA NASS QuickStats: QuickStats provides county‑level and state‑level agricultural statistics, including yields, planted acreage, production history, and crop frequency. These data can help participants calibrate their models against historical performance, compare rotation possibilities, and explore long‑term agricultural trends.

OpenET: Evapotranspiration for Water Management: OpenET delivers field‑scale evapotranspiration estimates using satellite‑driven models for western U.S. states. Participants may use this dataset to evaluate crop water demand, irrigation timing, water‑use efficiency, and identify fields under thermal or moisture stress. OpenET offers valuable ground‑truth ET information that complements ECOSTRESS and NASA POWER.

USFS LANDFIRE: Vegetation & Fuel Layers: LANDFIRE provides vegetation type, vegetation condition, fuel models, and landscape characteristics across the United States. These data may be used to understand local ecosystems, perennial cover, tree‑crop interactions, and landscape features that affect microclimates, water flow, erosion, and biodiversity relevant to rotational planning.

Global Ecosystem Dynamics Investigation (GEDI): GEDI provides high‑resolution laser‑based measurements of forest structure, including canopy height, leaf area index, and above‑ground biomass. Participants may use GEDI Level‑4 biomass products to understand vegetation density, canopy stress, and long‑term ecosystem changes around agricultural landscapes. While GEDI is most effective in areas with taller vegetation, its biomass and canopy metrics can help identify shifts in surrounding land cover, detect environmental stress impacts, and complement rotation‑crop analysis by providing structural context that pairs well with SMAP, Landsat, and MODIS vegetation indicators.

**Space Agency Partner Resources: ESA (European Space Agency)**

Copernicus Sentinel-2: ESA: Sentinel‑2 provides freely accessible 10–20‑meter multispectral imagery at high revisit frequency. With bands specifically designed for vegetation analysis (red‑edge, NIR, SWIR), participants may use Sentinel‑2 for NDVI/EVI, bare‑soil mapping, crop stress detection, and fine‑scale monitoring during growing seasons. Its higher spatial resolution complements Landsat and MODIS for field‑level assessments.

ERA5: ECMWF Reanalysis: ERA5 is a global reanalysis dataset that provides hourly climate variables such as temperature, precipitation, wind, humidity, soil temperature, and radiation. Participants may use ERA5 to fill gaps where local weather stations are sparse, analyze long‑term climate trends, build temporal features for SI models, and contextualize NASA Earth observations with continuous climate time series.

</details>

> quiero que me hagas un codigo para agregar a otro codigo mayor donde con los datos que te he dado hagas un mapa donde pueda moverme y seleccionar un terreno en eeuu para que tu me des su tamañno y su geolocalizacion no tienes que analizar nada de lo que hay dentro del campo solo la localizacion

### Lo que hizo Claude

1. Revisó el repositorio: `backend/api.py`, `backend/geometry.py`, `backend/demo_parcels.geojson`, `backend/config.py` (límite `MAX_AREA_HA = 1000`) y el mapa existente `frontend/index.html` (Leaflet + leaflet.draw, solo dibujo a mano).
2. Escribió un módulo independiente y reutilizable, `frontend/field-picker.js`, y una página de ejemplo, `frontend/field-picker-demo.html`.
3. Añadió la configuración `frontend-static` a `.claude/launch.json` (servidor estático `python -m http.server 5500` sobre `frontend/`).
4. Primera prueba: usaba OpenStreetMap (Overpass) para encontrar los campos, pero tardaba unos 36 s y en Iowa casi no hay campos dibujados ("No mapped fields here").
5. Buscó una fuente mejor y encontró **USDA NASS Crop Sequence Boundaries (CSB) 2017-2024** como servicio ArcGIS público:
   `https://pdi.scinet.usda.gov/hosting/rest/services/Hosted/Crop_Sequence_Boundaries_2024/FeatureServer/0`
   Lo comprobó desde el navegador: admite CORS, responde en unos 0,3 s y tiene los campos `csbid, csbacres, cnty, statefips, cdl2017…cdl2024`.
6. Cambió el módulo para usar CSB como fuente principal (EE. UU. continental) y dejó OSM como respaldo.
7. Lo probó en el navegador:
   - Con zoom 15 en Boone County (Iowa) aparecieron unos 90 campos resaltados en amarillo.
   - Al hacer clic en un campo: **43,85 ha / 108,36 ac**, perímetro 4.222 m, centro 42.006172, -93.769478, lugar "Boone County, Iowa". USDA da 108,3 ac para ese campo, así que el área cuadra.
   - En modo **Draw**, 4 esquinas y doble clic: 11,45 ha, correcto.
   - En la consola solo apareció un 404, probablemente del favicon.

### Respuesta de Claude

He creado un mapa en un archivo aparte, `frontend/field-picker.js`, que puedes meter en otro código. Lo he probado en el navegador con campos reales de Boone County (Iowa) y funciona. No analiza nada de lo que hay dentro del campo, solo su forma y su ubicación.

**Cómo funciona**
- **Moverse:** arrastras y haces zoom sobre la imagen de satélite, y tienes un buscador de lugares de EE. UU.
- **Campos resaltados:** a partir del zoom 14 los campos de cultivo aparecen con borde amarillo. Los saco de la capa USDA Crop Sequence Boundaries, que tiene los linderos de las parcelas de todo EE. UU. continental y responde en unos 0,3 s.
- **Seleccionar:** haces clic en un campo y se marca en naranja. Fuera de EE. UU. continental se usa OpenStreetMap, pero en Iowa casi no tiene campos dibujados.
- **Dibujar:** si un campo no aparece o su borde está mal, con el botón **Draw** marcas las esquinas a mano. Terminas con doble clic, Backspace borra la última esquina y Esc cancela.
- **Lo que te devuelve:**
  - superficie en m², hectáreas y acres
  - perímetro
  - centro en latitud y longitud
  - límites del rectángulo que lo contiene
  - condado y estado
  - el polígono en GeoJSON

**Comprobación:** en el campo que probé calculé 108,36 acres y la ficha de USDA dice 108,3, así que el cálculo del área cuadra. Los bordes de USDA salen escalonados porque siguen los píxeles de 30 m de Landsat; el panel lo avisa.

**Para meterlo en tu código:**
```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="field-picker.js"></script>
<script>
  const picker = FieldPicker.create(document.getElementById("map"), {
    onSelect(info) { console.log(info.area.ha, info.centroid, info.geometry); },
    onPlace(info)  { console.log(info.place); }  // condado y estado llegan un momento después
  });
</script>
```
Puedes enviar `info.geometry` tal cual a `/api/parcel/analyze`. Hay un ejemplo completo en `frontend/field-picker-demo.html`, y añadí la configuración `frontend-static` a `.claude/launch.json` para abrirlo en el puerto 5500.

No lo he conectado a `frontend/index.html`, que ya tenía otro mapa con dibujo a mano, y no he hecho commit.

Fuente: [USDA Crop Sequence Boundaries 2024 (ArcGIS REST)](https://pdi.scinet.usda.gov/hosting/rest/services/Hosted/Crop_Sequence_Boundaries_2024/FeatureServer/info/iteminfo)

---

## 2. Usuario

> dime que me tengo que descargar para pasarlo al otro codigo

### Respuesta de Claude

Solo necesitas un archivo: `frontend/field-picker.js`. No hay que instalar nada con npm ni con pip.

**Qué copiar al otro proyecto**
1. **`field-picker.js`** es obligatorio. Ponlo en la misma carpeta que el HTML donde vaya el mapa, o ajusta la ruta del `<script src>`.
2. **`field-picker-demo.html`** es opcional; sirve solo como ejemplo de uso.

**Leaflet (la librería del mapa)** no hace falta descargarlo, porque se carga desde internet. Pega esto en el `<head>` de tu HTML:
```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="field-picker.js"></script>
```

Si tu otro proyecto usa npm (React, Vue, Vite…), instala Leaflet así y cárgalo antes de `field-picker.js`:
```bash
npm install leaflet@1.9.4
```

**Además:**
- No necesita claves de API ni cuentas: los campos de USDA, el satélite de Esri, OpenStreetMap y el geocodificador son públicos.
- Sí necesita conexión a internet, porque los campos y las imágenes se piden en el momento.
- El contenedor del mapa debe tener una altura, por ejemplo `<div id="map" style="height:600px"></div>`. Si no la tiene, el mapa no se ve.
- Ábrelo desde un servidor (`http://…`) y no con doble clic sobre el archivo, para que el buscador funcione bien.

---

## 3. Usuario

> y pasame la conversacion entera como md

### Respuesta de Claude

Este archivo.

---

## Anexo: referencia rápida de `FieldPicker`

**Opciones de `FieldPicker.create(elemento, opciones)`** (valores por defecto):

| Opción | Por defecto | Qué hace |
|---|---|---|
| `center` | `[41.99, -93.69]` | Centro inicial (lat, lon) |
| `zoom` | `13` | Zoom inicial |
| `basemap` | `"satellite"` | `"satellite"` o `"streets"` |
| `highlightFields` | `true` | Resalta los campos que hay en pantalla |
| `highlightMinZoom` | `14` | Zoom mínimo para resaltar |
| `showCdl` | `false` | Capa de tipos de cultivo USDA CDL |
| `cdlYear` | `2024` | Año de la CDL |
| `reverseGeocode` | `true` | Condado y estado vía Nominatim |
| `showSearch` | `true` | Buscador de lugares de EE. UU. |
| `showPanel` | `true` | Panel con los resultados |
| `maxAreaHa` | `1000` | Avisa si se supera (límite del backend) |
| `onSelect`, `onPlace`, `onClear` | `null` | Callbacks |

**Métodos:** `getSelection()`, `clear()`, `setMode("click" | "draw")`, `selectGeoJSON(gj)`, `flyTo(lat, lon, zoom)`, `showCdl(true|false)`, `destroy()`, `map` (el mapa Leaflet).

**Objeto `info`:**
```json
{
  "geometry": { "type": "Polygon", "coordinates": [[[-93.766701, 42.007907], "..."]] },
  "area": { "m2": 438500, "ha": 43.85, "acres": 108.36 },
  "perimeter_m": 4222,
  "centroid": { "lat": 42.006172, "lon": -93.769478 },
  "bbox": { "south": 42.00297, "west": -93.77649, "north": 42.00881, "east": -93.76041 },
  "place": { "state": "Iowa", "county": "Boone County", "country_code": "US" },
  "in_us": true,
  "source": "usda_csb",
  "source_id": "csb/191724003011103",
  "warnings": ["USDA CSB edges follow 30 m Landsat pixels, so they look stepped; area is approximate."]
}
```

**Archivos creados o modificados:**
- `frontend/field-picker.js` (nuevo): el módulo.
- `frontend/field-picker-demo.html` (nuevo): el ejemplo.
- `.claude/launch.json` (modificado): se añadió `frontend-static` en el puerto 5500.
