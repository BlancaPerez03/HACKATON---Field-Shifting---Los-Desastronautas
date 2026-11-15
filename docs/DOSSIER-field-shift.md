# Field Shift: dossier de la capa de datos

NASA Space Apps Challenge 2026, reto "Field Shift: Adapting Farms with NASA Data".
Dossier escrito el sábado 14 de noviembre de 2026. Reúne todo lo que se ha leído, verificado, observado y juzgado
para el backend de datos (Google Earth Engine, NASA POWER y fuentes complementarias), además de la revisión crítica
del prompt anterior del equipo y de la lista de recursos de la captura.

Lo lee el equipo y lo lee la sesión que ejecute `PROMPT-field-shift-backend.md`. Los dos documentos están en
`/Users/alejandrolalaguna/Desktop/field-shift/`.

---

## 0. Lo más importante, en doce líneas

1. **El hackathon es este fin de semana.** Va del sábado 14 al domingo 15 de noviembre de 2026, y el envío cierra
   el domingo 15 a las 23:59 hora local. Hay que recortar el plan de seis fases del prompt anterior a un producto
   mínimo que se pueda enseñar.
2. Comparar al menos tres rotaciones, incluida la actual, es una sugerencia ("may"), no un requisito. Aun así es el
   núcleo de lo que el jurado esperará ver.
3. Para optar a premio global, el proyecto tiene que usar al menos un dato o recurso de NASA. El criterio Relevance
   pide además que los datos de NASA sean un componente central, no un añadido.
4. Las reglas de IA (la web la llama "Super Intelligence", SI) piden declarar dónde y cómo se usó la IA. En código y
   datos, la declaración va en texto descriptivo y en metadatos. **El prompt tiene que incluirlo.**
5. NASA POWER no da evapotranspiración de referencia (ET0): hay que calcularla. GWETROOT es un índice de humedad
   entre 0 y 1, no humedad volumétrica. Y un punto devuelve la resolución nativa de la fuente (0,5° × 0,625° en
   meteorología, 1° en radiación), no una rejilla de 0,5°.
6. IMERG V07 no tiene colección diaria en GEE. Diez años de datos semihorarios son unas 175.000 imágenes. La
   colección mensual acaba en 2025, y desde el 30 de septiembre de 2025 los datos son provisionales. Para contar
   días de lluvia extrema conviene usar POWER (de NASA) o CHIRPS.
7. SMAP es el primer conjunto de datos que nombra el reto y está en GEE (`NASA/SMAP/SPL4SMGP/008`). El prompt
   anterior lo dejaba como opcional; debería entrar en el producto mínimo.
8. Earth Engine no comercial tiene, desde el 27 de abril de 2026, un nivel Community de 150 EECU-horas al mes. Los
   map IDs duran "unas horas". La librería exige Python 3.11 o superior. Para la demo hace falta una caché
   precalculada.
9. Fuera de EE. UU., la mitad de los recursos no sirve. Para la rotación real, en la UE hay EUCROPMAP (2018 y 2022,
   10 m) y en todo el mundo WorldCereal de la ESA (2021, 10 m). Los dos están en GEE.
10. El NDVI no distingue el rastrojo del suelo desnudo. Añadir NDTI (SWIR1 y SWIR2) mejora mucho el indicador de
    "campo desnudo".
11. La captura de recursos acierta en lo esencial (OpenLandMap antes que la API REST de SoilGrids, un catálogo de
    8 a 12 cultivos en JSON). Open-Meteo es útil pero no es de NASA, es solo para uso no comercial y se aparta de la
    pregunta principal.
12. Tests: casi ninguno durante el trabajo. Al final, una prueba de humo con datos reales y tests de las fórmulas
    puras (decisión del propietario, 14 de noviembre).

---

## 1. Método de esta revisión

| Qué | Cómo | Fecha |
|---|---|---|
| Página del reto, reglas, calendario | API GraphQL de la propia web (`api.spaceappschallenge.org/graphql`, con cabecera `Origin`), porque la página se pinta con JavaScript | 14-11-2026 |
| Catálogo de Earth Engine | Páginas oficiales `developers.google.com/earth-engine/datasets/catalog/...` | 14-11-2026 |
| Acceso, autenticación, cuotas y teselas de GEE | Guías oficiales de Earth Engine y PyPI | 14-11-2026 |
| NASA POWER | Documentación oficial y **una llamada real a la API** (punto de prueba 41,65 N, 0,88 W, enero de 2024) | 14-11-2026 |
| Recursos de la captura (OpenLandMap, SoilGrids, ECOCROP y GAEZ, Open-Meteo) | Búsquedas sobre páginas oficiales | 14-11-2026 |
| WorldCereal, EUCROPMAP, NDTI | Búsquedas sobre el catálogo de GEE y la literatura | 14-11-2026 |

Etiquetas de confianza que se usan abajo:

- **[vivo]**: comprobado con una llamada real.
- **[doc]**: leído en la documentación oficial.
- **[búsqueda]**: sale del extracto de un buscador sobre una página oficial que no se pudo abrir entera.
- **[sin verificar]**: conocimiento general o inferencia. Hay que comprobarlo antes de usarlo.

No hay ningún repositorio del proyecto en esta máquina. Se buscó en `~` y en `~/Desktop` (por "space apps",
"field shift", "nasa" y "earth engine") y no apareció nada. La sesión que ejecute el prompt tendrá que inspeccionar
el repositorio donde se lance.

---

## 2. El reto, tal como está publicado

Página: https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/
Etiquetas de habilidades: Arts & Multimedia, Earth Science, Software.

### 2.1 Objetivo (cita)

> Your challenge is to create a decision-support tool that uses NASA Earth observations along with local soil
> information, crop characteristics, and farmer priorities to help farmers explore rotation strategies that could
> strengthen soil health and adapt their farms to changing conditions.

> You may compare at least three rotation strategies, including the existing rotation. For each strategy, you may
> explain why it was suggested, what evidence supports it, what benefits it may offer, where information gaps exist,
> and any risks that would need local review by farmers or agricultural experts.

> The intended outcome is a supportive tool — one that helps identify patterns and possibilities, but does not
> replace farmer judgment or local agricultural expertise.

**Lectura.** Todo está escrito con "may". Las "Potential Considerations" llevan el aviso "You may (but are not
required to)". El único requisito formal es responder a un reto oficial. Aun así, comparar tres rotaciones con su
justificación, su evidencia, sus carencias y sus riesgos es lo que diferencia este reto, y conviene hacerlo.

### 2.2 Datos que nombra el reto

- **Objetivos:** SMAP, ECOSTRESS, GPM, Landsat, MODIS, NASA POWER, GRACE y GRACE-FO, SRTM u otros productos de
  elevación de NASA.
- **Consideraciones:** además, GEDI (biomasa) y "soil datasets".
- **Variables:** temperatura, estrés térmico, lluvia, humedad del suelo, evaporación, riesgo de heladas,
  precipitación extrema, estrés de la vegetación y tendencias de agua a largo plazo.
- **Prioridades del agricultor:** uso de agua, valor forrajero, fijación de nitrógeno, reducción de la erosión,
  mejora de la materia orgánica y salida en el mercado.
- **Indicadores que pide destacar:** épocas en que el campo suele estar desnudo, temporadas en que el cultivo actual
  es más vulnerable, ruptura de ciclos de plagas, menor demanda de agua, mejor infiltración e ingresos
  complementarios.
- **Fusión de datos:** sugiere armonizar resoluciones distintas (remuestrear a una rejilla común) para combinar SMAP,
  ECOSTRESS, GPM, Landsat o MODIS, GEDI y suelo en variables explicables.
- **Diseño para el agricultor:** que sea fácil de interpretar, que el agricultor pueda meter sus prioridades y
  restricciones (agua disponible, maquinaria, mercado), y que recuerde dónde importa el juicio humano.

### 2.3 Recursos de la pestaña Resources

Son 24 entradas: 22 bajo "NASA Data & Resources" (de ellas, solo unas 7 son de NASA) y 2 bajo "Space Agency Partner
Resources: ESA". La entrada "Landsat / MODIS / VIIRS" lleva tres enlaces, así que hay 26 enlaces en total. El "24"
del prompt anterior cuadra si esa entrada cuenta como una.

| # | Recurso | Dueño | Cobertura | ¿Sirve para una parcela? | En GEE |
|---|---|---|---|---|---|
| 1 | SMAP | NASA | Global | No da escala de parcela (9 km), pero sí el contexto de humedad. **Es central para Relevance** | Sí: `NASA/SMAP/SPL4SMGP/008` |
| 2 | GPM / IMERG | NASA | Global | Zona (0,1°, unos 11 km) | Sí, ver §4.3 |
| 3 | Landsat / MODIS / VIIRS | NASA y USGS | Global | Landsat sí (30 m). MODIS 250 m da contexto | Sí |
| 4 | NASA POWER | NASA | Global | Zona (unos 50 × 60 km) | No: API REST |
| 5 | SRTM | NASA | 60° N a 56° S | Sí (30 m) | Sí |
| 6 | ECOSTRESS | NASA y JPL | Parcial (órbita de la ISS) | 70 m; en GEE la cobertura es muy limitada | Parcial, ver §4.8 |
| 7 | USDA Ag Data Commons | USDA | Sobre todo EE. UU. | Depende del conjunto de datos | No |
| 8 | Web Soil Survey | USDA NRCS | EE. UU. | Sí, en EE. UU. | No |
| 9 | Cropland Data Layer | USDA NASS | EE. UU. | Sí (30 m, rotación histórica real) | Sí: `USDA/NASS/CDL`, de 1997 a 2024 |
| 10 | PRISM | Oregon State | EE. UU. | 4 km y 800 m | Parcial |
| 11 | SSURGO / STATSGO2 | USDA NRCS | EE. UU. | Sí | No es oficial; el catálogo comunitario tiene gNATSGO |
| 12 | NAIP | USDA | EE. UU. | 1 m | Sí |
| 13 | NLCD | USGS | EE. UU. | 30 m | Sí |
| 14 | NLDAS / GLDAS | NASA | NLDAS en Norteamérica, GLDAS global | Zona (GLDAS a 0,25°) | Sí [sin verificar el ID] |
| 15 | FAO GAEZ | FAO | Global | Aptitud regional | No; usar el portal de la FAO |
| 16 | CoCoRaHS | Red ciudadana | Norteamérica | Estaciones | No |
| 17 | USGS NWIS | USGS | EE. UU. | Estaciones | No |
| 18 | USDA AMS Market News | USDA | EE. UU. | Precios | No |
| 19 | USDA NASS QuickStats | USDA | EE. UU. | Condado y estado | No |
| 20 | OpenET | Consorcio OpenET | Oeste de EE. UU. | Sí (30 m) | Sí, con un ID nuevo (§4.8) |
| 21 | LANDFIRE | USFS | EE. UU. | 30 m | Sí |
| 22 | GEDI | NASA y UMD | Entre 51,6° N y 51,6° S, en muestras | Muestras de huella; pensado para bosque | Sí |
| 23 | Copernicus Sentinel-2 | ESA | Global | Sí (10 m) | Sí |
| 24 | ERA5 | ECMWF | Global | Zona (ERA5-Land a 0,1°) | Sí |

GRACE y GRACE-FO se nombran en el texto, pero no están en la pestaña de recursos.

**Juicio.**

- Fuera de EE. UU. no sirven las entradas 7 a 13, 16 a 19, 20 y 21.
- Lo que sirve en cualquier sitio: SMAP, IMERG, Landsat, MODIS, POWER, SRTM (o NASADEM), Sentinel-2, ERA5, GAEZ y
  GLDAS.
- GRACE (1°, y en GEE la serie acaba en 2017-01-07) y GEDI (pensado para bosque, en muestras) no aportan nada a una
  parcela de cultivo. Como mucho, GRACE da contexto regional de agua subterránea en la presentación.

### 2.4 Reglas que afectan al backend

**Datos de NASA.**

> To be eligible for a Global Award, you must use at least one NASA data or resource.

El criterio Relevance pide que el proyecto "meaningfully integrates NASA data, utilizing it as a core component of
the proposed solution rather than a superficial addition".

**Consecuencia.** Cuando una variable se puede sacar de NASA o de otra fuente, conviene que la principal sea de NASA
y la otra sirva de contraste. Por ejemplo: la ET0 calculada con POWER antes que la de Open-Meteo, NASADEM antes que
Copernicus DEM, y SMAP antes que ERA5-Land para la humedad.

**IA ("SI").**

> We require that you clearly indicate where and how SI tools were utilized in your project, including: [...] Code
> and data: Must acknowledge SI generation in descriptive text and metadata.

> SI should not be used to (come up with your idea of how to solve the challenge).

**Consecuencia.** El README tiene que llevar una sección "Use of AI tools" que diga qué módulos generó o ayudó a
escribir una IA y cómo se revisaron. Cada módulo generado lleva una línea de cabecera que lo declare, y el JSON de
respuesta lleva un campo de metadatos. El jurado ve estas marcas, y también ve si faltan.

**Licencias y citas (términos de participación, 7 de agosto de 2026).**

> If your Solution requires the use of non-NASA materials [...] you are responsible for ensuring that your Solution
> Materials are freely and publicly available without restriction or [...] licensed as open source [...]. Any
> licenses applicable to your Solution Materials must be identified in the documentation [...]. You must cite every
> source that is used in the creation of your project, even if it is open source or freely available.

**Consecuencia.** La tabla de fuentes del README necesita una columna de licencia y una cita por fuente. Ver §8.

- **OpenLandMap** se publica con CC-BY-SA 4.0, que es "compartir igual": un producto derivado que redistribuya esas
  capas hereda la licencia. Hay que decirlo.
- **Open-Meteo** pone condiciones propias de uso no comercial.
- **ERA5** exige la frase de atribución de Copernicus.
- **Earth Engine** es una plataforma con sus propios términos, no un dato. Se cita como herramienta.

**Envío.**

- Demo: un vídeo de 30 segundos o menos, o hasta 7 diapositivas, accesible sin iniciar sesión. Si se pasa del
  límite, el proyecto no entra en el juicio global.
- Todo en inglés. Un vídeo hablado en otro idioma vale si lleva subtítulos en inglés.
- El enlace al proyecto puede ser un repositorio o una web. Al jurado le basta con la demo y la página del
  proyecto; no necesita ejecutar el backend.

**Criterios de evaluación.** Cinco criterios, cada uno de 1 a 5, sin pesos publicados:

- **Impact:** el alcance del problema que resuelve.
- **Creativity:** originalidad e innovación.
- **Validity:** que se apoye en principios científicos y sea viable. **Aquí puntúan la trazabilidad y las
  advertencias honestas.**
- **Relevance:** que responda al reto, con los datos de NASA como núcleo.
- **Presentation:** la demo y el proyecto completo.

**Calendario.**

| Fecha | Qué |
|---|---|
| Sábado 14-11, 9:00 hora local | Se abre la pestaña de proyecto |
| **Domingo 15-11, 23:59 hora local** | **Cierre del envío** |
| 30-11 | Encuesta a participantes |
| 3-12 | Nominados globales |
| 17-12 | Finalistas y menciones de honor |
| 26-01-2027 | Ganadores globales |

**Equipos.** Entre 1 y 6 personas en un evento local, y al menos 2 en el evento universal.

Fuentes: la página del reto, https://www.spaceappschallenge.org/resources/project-submission-guide/,
https://www.spaceappschallenge.org/resources/judging-awards-guide/ y https://www.spaceappschallenge.org/legal/.

---

## 3. Revisión crítica del prompt anterior

### 3.1 Lo que está bien y hay que conservar

- Limitar el encargo a la capa de datos, sin lógica de recomendación. Es una buena separación.
- Exigir indicadores trazables: fuente, versión, resolución, tipo de dato y advertencias. Apunta directo a
  "Validity" y a "what evidence supports it".
- Avisar de que el NDVI mide verdor, no fertilidad ni rendimiento.
- Distinguir satélite, reanálisis y modelo, y avisar cuando el dato describe una zona y no la parcela.
- Calcular en el servidor de GEE, sin `getInfo()` dentro de bucles, con `scale` y `maxPixels` fijados.
- Usar una sola fuente de verdad por variable y verificar cada ID en el catálogo.
- Validar la geometría (inválida, autointersecada, demasiados vértices, área máxima) y convertir un punto en buffer
  con aviso.
- La seguridad: ninguna credencial en el frontend ni en el repositorio, un `.env.example`, caché por hash y límite de
  frecuencia.
- Las ramas por región para los recursos que solo cubren EE. UU.
- Avisar de que GRACE y ECOSTRESS no encajan a escala de parcela.

### 3.2 Errores de hecho (corregidos y con fuente)

| # | El prompt dice | Lo verificado | Etiqueta |
|---|---|---|---|
| 1 | POWER tiene una resolución aproximada de 0,5° | Un punto devuelve la resolución nativa: MERRA-2 a 0,5° × 0,625° (unos 50 × 60 km) en meteorología y CERES a 1° en radiación. Solo el producto regional va en rejilla de 0,5° | [doc] [vivo] |
| 2 | POWER da "humedad del suelo en la zona radicular" | `GWETROOT` es "Root Zone Soil Wetness", con unidad "1": una fracción de saturación relativa entre 0 y 1 que sale del modelo de MERRA-2, no humedad volumétrica (m³/m³). En la prueba salió exactamente 0,5 tres días seguidos: hay que mirar su variabilidad antes de usarlo | [vivo] |
| 3 | Balance hídrico como "precipitación menos evapotranspiración de referencia", sin decir de dónde sale la ET0 | **POWER no tiene ET0.** Al pedir `ET0` responde "One of your parameters is incorrect". `EVPTRNS` es un flujo de energía en MJ/m²/día, no la ET0 FAO-56. Hay que calcularla (§6.4) | [vivo] |
| 4 | IMERG V07: "verifica cómo convertir la tasa a totales" | No hay colección diaria V07 en GEE. La semihoraria (`NASA/GPM_L3/IMERG_V07`) da mm/h por media hora, así que cada imagen se multiplica por 0,5 y se suma. Diez años son unas 175.000 imágenes. La mensual (`NASA/GPM_L3/IMERG_MONTHLY_V07`) acaba en 2025. Desde el 30-09-2025 no hay producto permanente porque el proveedor pasa a V8, y lo posterior es provisional | [doc] |
| 5 | Pocos meses con observaciones de Landsat, sin más detalle | Landsat 8 empieza el 18-03-2013 y Landsat 9 el 31-10-2021. Con los dos juntos, la revisita es de unos 8 días | [doc] y [sin verificar] lo de 8 días |
| 6 | Fase 6: SMAP como opcional | SMAP es el primer conjunto de datos que nombra el reto. En GEE: `NASA/SMAP/SPL4SMGP/008` (bandas `sm_rootzone` y `sm_surface`, en fracción volumétrica, unos 9 a 11 km, de 2015-03-31 a hoy). `NASA_USDA/HSL/SMAP10KM_soil_moisture` está obsoleto y acaba el 02-08-2022. `NASA/SMAP/SPL3SMP_E/006` solo empieza el 04-12-2023; lo anterior está en `/005` | [doc] |
| 7 | MODIS MOD13Q1 | El ID correcto es `MODIS/061/MOD13Q1` (no 006). NDVI con escala 0,0001. SummaryQA: 0 bueno, 1 marginal, 2 nieve, 3 nube | [doc] |
| 8 | "Una sola `getInfo()` por indicador" | Es razonable. Mejor todavía: una petición por módulo (NDVI, relieve, lluvia, suelo) lanzada en paralelo. Un fallo o un timeout en una no tira las demás, y se respeta el límite de 40 peticiones concurrentes por proyecto | Juicio |
| 9 | `maxPixels` fijado, sin valor | El valor por defecto no está documentado (un ejemplo de error muestra 10 millones). En una parcela de hasta 1.000 ha a 30 m hay unos 11.000 píxeles, así que no hay problema. Hay que fijar `scale` siempre, porque si no puede caer a 1° | [doc] |
| 10 | Las URLs de teselas caducan: incluir `expires_at` | La documentación solo dice que un map ID vale "for a moderate period (a few hours)". No da una cifra exacta, así que `expires_at` tiene que ser una estimación prudente (p. ej. creado más 2 h) y regenerarse | [doc] |
| 11 | Proyecto de Cloud "habilitado y registrado" | Desde el 13-11-2024 no se puede usar sin proyecto. Desde el 27-04-2026, los proyectos no comerciales tienen niveles: **Community, 150 EECU-horas al mes**; Contributor, 1.000, con una cuenta de facturación activa; Partner, 100.000, con solicitud de semanas. Al agotar la cuota, el proyecto pasa a modo restringido (menos concurrencia), no se corta. Usar varios proyectos para esquivar el límite va contra los términos | [doc] |
| 12 | IAM, sin detalle | `roles/earthengine.writer` (es el rol que la documentación asocia a ejecutar cálculos interactivos; no consta que `viewer` baste) y `roles/serviceusage.serviceUsageConsumer`, sin el cual `ee.Initialize(project=...)` falla. La API de Earth Engine tiene que estar habilitada en el proyecto | [doc] |
| 13 | `earthengine-api`, sin versión | 1.7.52 (09-11-2026), **exige Python 3.11 o superior**. Con una versión no soportada puede fallar la autenticación | [doc] |
| 14 | Tipos de dato `satellite`, `reanalysis`, `model` | Faltan tipos. IMERG Final es satélite combinado con pluviómetros; POWER mezcla reanálisis (MERRA-2) y radiación derivada de satélite (CERES); `GWETROOT` es salida de modelo; los indicadores derivados son cálculos propios; lo que mete el agricultor es dato de usuario. Enum propuesto en §5.3 | Juicio y [doc] |
| 15 | SRTM con aviso fuera de 60° N a 56° S | Correcto. Pero NASADEM (`NASA/NASADEM_HGT/001`) es el reprocesado de SRTM que hizo NASA, con la misma cobertura y mejor calidad: mejor para Relevance. Para zonas fuera de la cobertura, `COPERNICUS/DEM/GLO30_2024_1`; **el ID antiguo `COPERNICUS/DEM/GLO30` está obsoleto** | [doc] |
| 16 | Sentinel-2 con Cloud Score+ | Correcto: `COPERNICUS/S2_SR_HARMONIZED` con `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, enlazados con `linkCollection(csPlus, ['cs_cdf'])`, y se conservan los píxeles con `cs_cdf >= 0.60` (Google dice que funcionan bien valores entre 0,50 y 0,65). `QA60` dejó de producirse el 25-01-2022. La cobertura L2A de 2017 y 2018 no es global | [doc] |
| 17 | OpenET, sin ID | `OpenET/ENSEMBLE/CONUS/GRIDMET/MONTHLY/v2_0` está reemplazado por `projects/openet/assets/ensemble/conus/gridmet/monthly/v2_0`. Solo cubre el oeste de EE. UU. y acaba en 2024-12 | [doc] |
| 18 | ECOSTRESS "seguramente no está" en GEE | Hay dos productos oficiales (`NASA/ECOSTRESS/L2T_LSTE/V2` y `NASA/ECOSTRESS/L2T_STARS/V2`, a 70 m). Según un extracto, LSTE solo tiene ingeridas teselas de Los Ángeles. Para el resto, AppEEARS con cuenta de Earthdata. La conclusión del prompt (no integrarlo sin consultar) se mantiene | [doc] y [búsqueda] |
| 19 | CDL "rotación histórica real" | Correcto, pero solo de 1997 a 2024 y solo en EE. UU. continental | [doc] |
| 20 | SoilGrids como alternativa global | La API REST de SoilGrids está "temporalmente pausada" según su documentación (18-12-2025). Unas FAQ posteriores no lo repiten: estado incierto. En GEE, el catálogo oficial solo confirma las capas de contenido de agua (`ISRIC/SoilGrids250m/v2_0/...`); el resto está en el catálogo comunitario `projects/soilgrids-isric/*`. OpenLandMap está en el catálogo oficial (§4.6) | [doc] y [búsqueda] |
| 21 | FAO GAEZ en GEE | No hay un asset de GAEZ v5 en GEE. Se usa el portal de la FAO (`data.apps.fao.org/gaez`, CC BY 4.0) | [búsqueda] |

### 3.3 Lagunas de método

1. **El NDVI no ve el rastrojo.** Un campo con rastrojo o residuo da NDVI bajo, igual que el suelo desnudo, pero
   protege el suelo de la erosión. Para el indicador de "campo desnudo", que alimenta el de erosión, hay que añadir
   **NDTI**:
   - Fórmula: (SWIR1 − SWIR2) / (SWIR1 + SWIR2). En Landsat 8 y 9, `SR_B6` y `SR_B7`; en Sentinel-2, `B11` y `B12`.
   - Cuándo sirve: solo cuando el NDVI es bajo (p. ej. NDVI < 0,3), porque la vegetación verde también absorbe en
     el SWIR.
   - Sesgo: el suelo húmedo se parece al residuo, así que hay que descartar las fechas justo después de llover.
   - Umbrales: son locales; la literatura muestra que cambian entre regiones.
2. **Heladas con aire a 2 m de reanálisis.** Un dato a 2 m sobre una celda de unos 50 km infraestima las heladas de
   radiación en fondos de valle y sobreestima en laderas. Hay que dar dos umbrales (Tmin ≤ 0 °C y Tmin ≤ 2 °C, este
   último como indicador de helada en superficie), fechas por percentiles y no "típicas", y tener en cuenta el
   hemisferio. POWER tiene un parámetro `FROST_DAYS` [vivo] que sirve de contraste.
3. **Estrés térmico.** El umbral de 35 °C depende del cultivo y de la fase: importa sobre todo en la floración. La
   capa de datos solo da los días por encima del umbral, por mes. Cruzarlos con el calendario del cultivo es trabajo
   del módulo de rotaciones. ECOSTRESS mide la temperatura de la superficie, no la del aire, y no hay que mezclarlas.
4. **Lluvia extrema.** "Percentil 95 de la serie" es ambiguo. El estándar de los índices de extremos climáticos
   (ETCCDI), R95p, se calcula sobre los días de lluvia (≥ 1 mm). Conviene dar además umbrales absolutos (p. ej.
   R20mm, días con ≥ 20 mm). Los reanálisis y los productos de 0,1° suavizan los extremos: hay que avisar.
5. **Lluvia: dos fuentes que no van a coincidir.** POWER (`PRECTOTCORR`) e IMERG darán totales distintos. Hay que
   decidir cuál es la principal para cada uso y enseñar la otra como contraste, sin mezclarlas.
6. **Vulnerabilidad.** Las anomalías de NDVI necesitan una climatología con suficientes años válidos por mes (p. ej.
   5 o más). Coincidir con calor o déficit hídrico es coincidencia, no causa, y hay que etiquetarlo así.
7. **Erosión.** Se puede hacer un índice relativo inspirado en RUSLE (las letras son los factores de la ecuación):
   - R, la erosividad de la lluvia: proxy con los días extremos o el máximo diario anual.
   - K, la erosionabilidad del suelo: proxy con la textura y el carbono orgánico de OpenLandMap.
   - LS, la pendiente: con NASADEM o SRTM.
   - C, la cobertura: los meses desnudos que caen en la época de lluvias.
   Se presenta como bajo, medio o alto, con el desglose de cada factor, nunca en t/ha/año.
8. **Suelo local.** El reto pide "local soil information". El prompt no tenía fuente de suelo en el producto mínimo.
   OpenLandMap en GEE resuelve pH, textura, carbono orgánico, densidad aparente y agua a capacidad de campo a 250 m
   (§4.6). Es una estimación, no un análisis de laboratorio, y lo que introduzca el agricultor debe tener prioridad.
9. **Características de los cultivos.** El reto las pide, y el prompt no las tenía porque las dejaba para el módulo
   de rotaciones. La captura propone un JSON de 8 a 12 cultivos a partir de ECOCROP: es lo correcto (§7.4).
10. **Rotación actual fuera de EE. UU.** En la UE, EUCROPMAP (`JRC/D5/EUCROPMAP/V1`, 2018 y 2022, 10 m). En todo el
    mundo, WorldCereal (`ESA/WorldCereal/2021/MODELS/v100`, 2021, 10 m, CC BY 4.0). Dan dos años o uno, no una
    serie. La rotación actual la confirma el agricultor.
11. **Tiempo de respuesta.** Diez años de Landsat por meses, más IMERG, POWER y suelo, para una parcela grande,
    pueden pasar de 30 a 60 segundos. El límite interactivo de GEE es de 5 minutos por petición. Para la demo hace
    falta una caché por hash y, sobre todo, **parcelas de demo precalculadas** guardadas como JSON, para que la demo
    no dependa de la cuota, del estado de GEE ni de la caducidad de los map IDs.
12. **Avisos como códigos.** Además del texto, cada aviso debe llevar un código estable (p. ej.
    `PARCEL_SMALLER_THAN_PIXEL`). Así el frontend puede traducirlo, agruparlo y contarlo.
13. **Hemisferio sur.** Las fechas de helada y las "épocas" cambian. Hay que decidir por la latitud del centroide.

### 3.4 Riesgo de alcance

El prompt anterior tenía seis fases, cada una con test y con salida real antes de pasar a la siguiente, además de un
README, un límite de frecuencia y un proxy de teselas. Está pensado para varias semanas, no para un fin de semana.
Con el cierre el domingo a las 23:59 hora local:

- **Imprescindible:** POWER con su derivado de clima; NDVI y NDTI de Landsat; SMAP; relieve; suelo de OpenLandMap;
  los indicadores derivados; el contrato JSON; las parcelas de demo precalculadas; el README con la tabla de fuentes
  y la declaración de IA.
- **Si sobra tiempo:** teselas para el mapa (NDVI y pendiente bastan); IMERG; Sentinel-2.
- **Fuera:** MODIS, ERA5-Land, CDL o SSURGO (salvo que la región sea EE. UU.), ECOSTRESS, GRACE, GEDI y el proxy de
  teselas.
- **Tests:** casi ninguno durante el trabajo. Al final, una prueba de humo con dos parcelas reales y tests unitarios
  solo de las fórmulas puras (ET0, fechas de helada, máscara de bits, índice de erosión). Lo decidió el propietario
  el 14 de noviembre.

---

## 4. Fuentes verificadas, una por una

### 4.1 Landsat 8 y 9, Collection 2 Level 2 [doc]

| Dato | Valor |
|---|---|
| IDs | `LANDSAT/LC08/C02/T1_L2` (del 18-03-2013 a hoy), `LANDSAT/LC09/C02/T1_L2` (del 31-10-2021 a hoy) |
| Rojo, NIR, SWIR1, SWIR2 | `SR_B4`, `SR_B5`, `SR_B6`, `SR_B7` |
| Escala de SR | DN × 0,0000275 − 0,2; DN válido de 1 a 65.455. Descartar la reflectancia fuera de [0, 1] |
| Escala de ST | `ST_B10` × 0,00341802 + 149 (K) |
| Resolución | 30 m |
| QA_PIXEL | bit 0 relleno; 1 nube dilatada; 2 cirro; 3 nube; 4 sombra de nube; 5 nieve; 6 despejado; 7 agua. Los bits 8 a 15 son confianzas de dos bits |
| Máscara recomendada | Quitar el píxel si cualquiera de los bits 0 a 5 está activo |
| QA_RADSAT | Bits 0 a 6: saturación de las bandas 1 a 7; bit 11: oclusión por el terreno. Quitar el píxel si está saturada alguna banda usada o hay oclusión |
| Código oficial de máscara | No hay: el catálogo solo trae `applyScaleFactors`. La máscara se escribe |
| Landsat 5 y 7 | `LANDSAT/LT05/C02/T1_L2` (1984 a 2012), `LANDSAT/LE07/C02/T1_L2` (1999 a 2024-01-19). Rojo y NIR son `SR_B3` y `SR_B4`. El bandeo SLC-off de Landsat 7 empieza el 31-05-2003 [sin verificar en el catálogo]. Fuera del alcance de este fin de semana |
| Licencia | Dominio público; se agradece citar al USGS |

### 4.2 Relieve [doc]

| Conjunto de datos | ID | Banda | Cobertura | Estado |
|---|---|---|---|---|
| NASADEM (recomendado) | `NASA/NASADEM_HGT/001` | `elevation` (m) | 60° N a 56° S | Vigente |
| SRTM | `USGS/SRTMGL1_003` | `elevation` (m) | 60° N a 56° S | Vigente |
| Copernicus GLO-30 | `COPERNICUS/DEM/GLO30_2024_1` | `DEM` | Global | Vigente; usar fuera de la cobertura de SRTM |
| Copernicus GLO-30 (antiguo) | `COPERNICUS/DEM/GLO30` | | | **Obsoleto** |

`ee.Terrain.slope` devuelve grados, en el rango [0, 90) [doc: https://developers.google.com/earth-engine/apidocs/ee-terrain-slope].
Usa los 4 vecinos de cada píxel, así que deja valores vacíos en los bordes de la imagen. Por eso la pendiente se
calcula sobre el modelo de elevación sin recortar, o sobre la parcela con un buffer de 100 m, y después se reduce
sobre la parcela: media, máximo y percentil 90.

### 4.3 Precipitación [doc]

| Conjunto de datos | ID | Unidad | Resolución | Periodo | Notas |
|---|---|---|---|---|---|
| IMERG V07 semihorario | `NASA/GPM_L3/IMERG_V07` | mm/h | 0,1° | 1998 a hoy | Banda `precipitation`. Total = Σ(tasa × 0,5 h). Desde el 30-09-2025, provisional |
| IMERG V07 mensual | `NASA/GPM_L3/IMERG_MONTHLY_V07` | mm/h (al menos la banda `randomError`; es una tasa media, así que total = tasa × horas del mes) [búsqueda] | 0,1° | Hasta 2025-09 aproximadamente | Fechas contradictorias entre versiones de la página |
| CHIRPS diario | `UCSB-CHG/CHIRPS/DAILY` | mm/día | 0,05° | 1981 a 2026-09-30 | Solo entre 50° S y 50° N. No es de NASA (UCSB y USGS) |
| POWER `PRECTOTCORR` | API | mm/día | Nativa de MERRA-2 | 1981 a hoy | De NASA. Precipitación del modelo corregida con observaciones (GPCP e IMERG, según un extracto) |

**Recomendación.**

- Para los días extremos y el balance hídrico, POWER `PRECTOTCORR`, que es de NASA, diario y barato.
- Para los totales mensuales, IMERG agregado en el servidor, solo si da tiempo, como "observación de satélite de
  contraste". Antes, medir el tiempo con un año.
- CHIRPS solo si hace falta más resolución y la parcela está entre 50° S y 50° N.

### 4.4 Humedad del suelo [doc]

| Conjunto de datos | ID | Bandas | Unidad | Resolución | Periodo |
|---|---|---|---|---|---|
| SMAP L4 (recomendado) | `NASA/SMAP/SPL4SMGP/008` | `sm_rootzone` (0 a 100 cm), `sm_surface` (0 a 5 cm) | Fracción volumétrica (0 a 0,9) | Unos 9 km (la tabla de bandas dice 11 km) | 31-03-2015 a hoy, cada 3 horas |
| SMAP L3 mejorado | `NASA/SMAP/SPL3SMP_E/006` | `soil_moisture_am`, `soil_moisture_pm` | Fracción volumétrica | 9 km | Desde 04-12-2023 (antes, `/005`) |
| POWER `GWETROOT` | API | | Índice entre 0 y 1 | Nativa de MERRA-2 | 1981 a hoy |

SMAP L4 es una asimilación en un modelo: tipo `model`, con observaciones de satélite asimiladas. Durante los cortes
del instrumento (del 19-06 al 23-07-2019 y del 06-08 al 20-09-2022) fue solo modelo. Hay que calcular la
climatología mensual y las anomalías. En SMAP L4, 10 años de datos cada 3 horas son unas 29.000 imágenes, y se
reducen a medias mensuales en el servidor.

### 4.5 Vegetación complementaria [doc]

| Conjunto de datos | ID | Uso | Estado en el plan |
|---|---|---|---|
| Sentinel-2 SR | `COPERNICUS/S2_SR_HARMONIZED` (rojo `B4`, NIR `B8`, SWIR `B11` y `B12`; escala 1/10.000) | NDVI y NDTI a 10 m desde 2017 | Si da tiempo |
| Cloud Score+ | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, `cs_cdf ≥ 0,60` | Máscara de nubes de Sentinel-2 | Junto con Sentinel-2 |
| MODIS NDVI | `MODIS/061/MOD13Q1` (250 m, 16 días, desde 2000) | Climatología larga | Fuera |
| MODIS ET | `MODIS/061/MOD16A2GF` (500 m, 8 días, de 2000 a 2025-12; `ET` en kg/m²/8 días, escala 0,1) | ET real de NASA para contrastar el balance | Opcional; es un buen argumento de Relevance |

### 4.6 Suelo: OpenLandMap en GEE [doc] [búsqueda]

Las capas son estáticas (compilación de 1950 a 2018), a 250 m, con seis profundidades por imagen (bandas `b0`,
`b10`, `b30`, `b60`, `b100` y `b200`, en cm). Licencia CC-BY-SA 4.0.

| Variable | ID | Unidad y escala |
|---|---|---|
| pH en agua | `OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02` | pH × 10 (rango de 42 a 110) |
| Clase textural USDA | `OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02` | Código de clase de 1 a 12 con tabla de equivalencias |
| Arcilla | `OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02` | % [sin verificar la escala] |
| Arena | `OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02` | % [sin verificar la escala] |
| Carbono orgánico | `OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02` | En unidades de 5 g/kg [comprobar en la página] |
| Densidad aparente | `OpenLandMap/SOL/SOL_BULKDENS-FINEEARTH_USDA-4A1H_M/v02` | 10 kg/m³ |
| Agua a 33 kPa (capacidad de campo) | `OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01` | % |

Para la parcela: media ponderada de 0 a 30 cm, a partir de `b0`, `b10` y `b30`. Hay que marcarlo como estimación
regional (tipo `model`), no como análisis de laboratorio, y dar prioridad a cualquier dato de suelo que meta el
agricultor.

### 4.7 Tipos de cultivo, para la rotación actual [doc] [búsqueda]

| Conjunto de datos | ID | Cobertura | Años | Licencia |
|---|---|---|---|---|
| USDA CDL | `USDA/NASS/CDL` (banda `cropland`) | EE. UU. continental | 1997 a 2024 | Dominio público |
| JRC EUCROPMAP | `JRC/D5/EUCROPMAP/V1` | UE | 2018 y 2022 | CC BY 4.0 |
| ESA WorldCereal | `ESA/WorldCereal/2021/MODELS/v100` (filtrar por `product` y `season`) | Global | 2021 | CC BY 4.0 |

WorldCereal es de la ESA, que es agencia socia. Usarlo encaja con "highly encouraged to use data [...] from the 2026
Space Apps Space Agency Partners".

### 4.8 Lo que no entra este fin de semana, y por qué

| Fuente | Motivo |
|---|---|
| ECOSTRESS | En GEE, cobertura mínima. AppEEARS exige cuenta de Earthdata y una cola de peticiones |
| GRACE | 1°, y en GEE acaba el 07-01-2017. Solo da contexto regional |
| GEDI | Muestras de huella, pensadas para bosque |
| OpenET | Oeste de EE. UU. y nuevo ID (§3.2, fila 17) |
| SSURGO | No está en el catálogo oficial. El catálogo comunitario tiene gNATSGO (ruta sin verificar) |
| ERA5-Land | `ECMWF/ERA5_LAND/DAILY_AGGR` funciona (0,1°, K y m), pero no es de NASA y duplica a POWER. Exige la atribución de Copernicus |
| GLDAS | `NASA/GLDAS/V021/NOAH/G025/T3H` [doc]: de NASA y global, a 0,25° y cada 3 horas, desde 2000 hasta unos meses antes de hoy (la página en inglés dice 2026-05-31). Bandas como `Evap_tavg` y las de humedad del suelo por capas. Es una buena alternativa de NASA a ERA5-Land, pero duplica a POWER y SMAP |

---

## 5. Arquitectura recomendada para la capa de datos

### 5.1 Módulos

```
backend/
  gee_client.py      # inicialización única, ADC o cuenta de servicio, reintentos ante 429
  sources/
    power.py         # cliente NASA POWER: comunidad AG, diario, punto, caché, reintentos
    landsat.py       # NDVI y NDTI de Landsat 8 y 9 por meses, con recuentos válidos
    smap.py          # sm_rootzone y sm_surface por meses, climatología y anomalías
    terrain.py       # NASADEM o SRTM: altitud y pendiente
    soil.py          # OpenLandMap de 0 a 30 cm
    precipitation.py # IMERG, solo si da tiempo
    croptype.py      # CDL, EUCROPMAP o WorldCereal, según la región
  derived.py         # funciones puras: ET0, balance, heladas, calor, extremos, campo desnudo, erosión
  geometry.py        # validación, buffer de un punto, área, hash
  api.py             # POST /api/parcel/analyze
  demo_cache/        # JSON precalculados de 2 o 3 parcelas de demo
```

Los nombres del prompt anterior (`landsat_ndvi.py` y demás) también sirven. Lo que importa es tener un módulo por
fuente, la autenticación aparte y que `derived.py` sea puro, sin llamadas de red, para poder probarlo sin simular
GEE.

### 5.2 Endpoint

- `POST /api/parcel/analyze`. Si el repositorio ya tiene otro nombre (p. ej. `/api/earth-engine/analyze`), se
  conserva el existente y se cambia una línea.
- **Entrada:** GeoJSON en WGS84 y orden [lon, lat], de tipo `Point`, `Polygon`, `MultiPolygon` o `Feature`. Fechas
  opcionales: por defecto los últimos 10 años completos, con un máximo configurable. Prioridades del agricultor
  opcionales; solo se devuelven tal cual, para el módulo de rotaciones.
- **Punto:** buffer de 50 m, configurable, con aviso. A 30 m eso son unos 8 píxeles de Landsat.
- **Rechazos:** geometría inválida o autointersecada (`shapely` `is_valid`), más de N vértices, más de 1.000 ha.
- **Ejecución:** módulos en paralelo con un pool de hilos (POWER sin GEE y las demás con GEE). Cada módulo tiene su
  timeout. Si uno falla, la respuesta sale igual: ese indicador llega como `null` y su error pasa a `data_gaps`. Un
  código 502 o 504 solo si falla todo.
- **Caché:** por SHA-256 de la geometría normalizada más las fechas más la versión del contrato. En disco o en
  memoria basta para el hackathon.
- **Modo demo:** si la geometría coincide con una parcela de demo, se sirve su JSON precalculado. Una cabecera o un
  campo `served_from: "demo_cache"` lo deja visible.

### 5.3 Contrato JSON (ampliado respecto al prompt anterior)

```json
{
  "version": "1",
  "generated_at": "2026-11-14T18:00:00Z",
  "served_from": "live | cache | demo_cache",
  "request": {
    "geometry_type": "Polygon",
    "area_ha": 12.4,
    "centroid": [-0.88, 41.65],
    "hemisphere": "north",
    "start_date": "2016-01-01",
    "end_date": "2025-12-31"
  },
  "indicators": {
    "ndvi": {
      "source": {
        "ids": ["LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"],
        "provider": "NASA/USGS",
        "nasa": true,
        "citation_key": "landsat_c2l2"
      },
      "data_type": "satellite",
      "resolution_m": 30,
      "scale_note": "parcel",
      "unit": "dimensionless (-1 to 1)",
      "method": "Monthly median of cloud-masked NDVI (QA_PIXEL bits 0-5, QA_RADSAT)",
      "monthly": [{ "month": "2024-05", "median": 0.62, "valid_observations": 3, "valid_pixel_pct": 87 }],
      "climatology": [{ "month": 5, "median": 0.58, "years": 9 }],
      "warnings": [{ "code": "NDVI_NOT_FERTILITY", "message": "NDVI indicates green vegetation vigor, not soil fertility or yield." }]
    },
    "ndti": {},
    "soil_moisture_smap": {},
    "agroclimate_power": {},
    "terrain": {},
    "soil_openlandmap": {},
    "precipitation_imerg": null,
    "crop_type": {}
  },
  "derived": {
    "bare_months": {
      "value": [7, 8],
      "method": "NDVI climatology < 0.25 and NDTI < local threshold",
      "inputs": ["ndvi", "ndti"],
      "thresholds": { "ndvi": 0.25 },
      "confidence": "medium",
      "confidence_reason": "Fewer than 3 valid observations in August in 4 of 9 years",
      "gaps": ["Residue vs bare soil not validated locally"]
    }
  },
  "layers": [
    {
      "id": "ndvi_median",
      "tile_url": "https://earthengine.googleapis.com/v1/.../tiles/{z}/{x}/{y}",
      "expires_at_estimate": "...",
      "legend": { "min": 0, "max": 0.9, "palette": ["..."], "unit": "NDVI" }
    }
  ],
  "data_gaps": ["No farmer-provided soil analysis", "Current rotation not confirmed by farmer"],
  "warnings": [{ "code": "POINT_BUFFERED", "message": "Point input buffered to 50 m." }],
  "provenance": {
    "ai_assistance": "Parts of this backend were generated with AI coding tools and reviewed by the team; see README, Use of AI tools.",
    "citations": { "landsat_c2l2": "...", "nasa_power": "...", "smap_l4": "..." }
  }
}
```

**`data_type` (enum):**

- `satellite`
- `satellite_gauge_merged`: IMERG Final, CHIRPS.
- `reanalysis`: la meteorología de POWER y ERA5.
- `model`: `GWETROOT`, SMAP L4, OpenLandMap.
- `derived`: cálculos propios.
- `user_input`
- `in_situ`

**`scale_note` (enum):**

- `parcel`: la resolución es igual o menor que la parcela.
- `sub_parcel_mixed`: la parcela es menor que el píxel.
- `zone`: el dato describe la zona y no la parcela (POWER, SMAP, IMERG).

**Códigos de aviso mínimos:**

- `LOW_VALID_OBS`
- `HIGH_CLOUD`
- `PARCEL_SMALLER_THAN_PIXEL`
- `OUT_OF_COVERAGE`
- `MIXED_SENSORS`
- `POINT_BUFFERED`
- `ZONE_SCALE_DATA`
- `PROVISIONAL_DATA` (IMERG desde 2025-10)
- `MODEL_SOIL_ESTIMATE`
- `NDVI_NOT_FERTILITY`
- `FROST_AIR_TEMP_PROXY`
- `SOLAR_DATA_LAG` (los retrasos de CERES desde agosto de 2024)

### 5.4 Autenticación de GEE

- **Desarrollo:** `earthengine authenticate` o `gcloud auth application-default login`, y después
  `ee.Initialize(project=os.environ["EE_PROJECT_ID"])`. Si no hay credenciales propias de Earth Engine,
  `ee.Initialize` recurre a `google.auth.default()` [doc].
- **Producción:** una cuenta de servicio con `roles/earthengine.writer` y `roles/serviceusage.serviceUsageConsumer`,
  a través de `GOOGLE_APPLICATION_CREDENTIALS` o de la identidad del servicio (Cloud Run y similares), sin cambiar
  código. El patrón exacto para Cloud Run está [sin verificar]. Pasar `credentials=` de forma explícita evita
  ambigüedades.
- **Cuándo:** se inicializa una vez al arrancar, y no se repite en cada petición.
- **Endpoint de alto volumen** (`earthengine-highvolume.googleapis.com`): no conviene aquí. Está pensado para muchas
  peticiones simples (teselas de imágenes ya construidas) y almacena menos en caché, así que una agregación cuesta
  más EECU [doc].

### 5.5 Cuotas y robustez

- 40 peticiones concurrentes por proyecto y 100 peticiones por segundo [doc].
- Ante un 429, el cliente reintenta hasta 5 veces. Encima hace falta caché propia.
- El tope interactivo es de 5 minutos por petición [doc].
- Con 150 EECU-horas al mes en el nivel Community, hay que precalcular las parcelas de demo antes de grabar el vídeo
  y no recalcularlas en cada clic.
- No usar varios proyectos para esquivar la cuota: va contra los términos.

### 5.6 Teselas

- En Python: `image.getMapId(vis)`. La URL `{z}/{x}/{y}` sale de `map_id["tile_fetcher"].url_format`. Es el campo
  documentado del resultado y el que usan rgee e ipygee. Si en 1.7.x se llamara de otra forma,
  `ee.data.getTileUrl(map_id, x, y, z)` es la vía oficial [doc: https://developers.google.com/earth-engine/apidocs/ee-data-gettileurl].
- El map ID dura "unas horas" [doc]. Se regenera bajo demanda (`GET /api/parcel/layers?hash=...`) o se cachea con
  `expires_at_estimate`.
- Las URLs llevan un token de ese mapa. Exponerlas al navegador es aceptable para un hackathon: no dan acceso al
  proyecto, solo a esas teselas, que sí gastan cuota. Un proxy en el backend es mejor, pero queda fuera de este fin
  de semana.

---

## 6. Indicadores derivados: especificación

Todas son funciones puras en `derived.py`. Cada una devuelve el valor, el método, los umbrales, las entradas, la
confianza y su motivo, y las carencias.

### 6.1 Meses de campo desnudo

- **Entradas:** la climatología mensual de NDVI y de NDTI (Landsat).
- **Regla:** un mes es "desnudo o con poca cubierta" si su NDVI mediano es menor que 0,25 (configurable). Si además
  el NDTI está por debajo del umbral, es "probablemente suelo desnudo". Si el NDTI es alto, es "probablemente
  rastrojo o residuo".
- **Confianza:** alta si cada mes tiene 5 años o más con 2 observaciones válidas o más; media entre 3 y 4; baja por
  debajo.
- **Carencias:** el umbral de NDTI es local y el suelo húmedo se parece al residuo.

### 6.2 Épocas de vulnerabilidad

- **Método:** anomalía de NDVI (z-score) por mes y año respecto a la climatología de la parcela. Se marcan los meses
  con z ≤ −1 que coinciden con calor (días por encima del umbral) o con déficit hídrico (P − ET0 por debajo de su
  percentil 20, o anomalía negativa de SMAP en la zona radicular).
- **Salida:** la lista de meses del calendario con su frecuencia de coincidencia, etiquetada como coincidencia y no
  como causa.

### 6.3 Riesgo de heladas (POWER `T2M_MIN`)

- **Año agrícola:** en el hemisferio norte se parte en el 1 de julio. La última helada de primavera es el último día
  antes del 1 de julio con Tmin ≤ 0 °C; la primera de otoño, el primer día después. En el hemisferio sur, lo mismo
  con el 1 de enero.
- **Salida:** las fechas en los percentiles 10, 50 y 90 entre años; los días con Tmin ≤ 0 °C y con Tmin ≤ 2 °C por
  mes; y `FROST_DAYS` de POWER como contraste.
- **Aviso:** `FROST_AIR_TEMP_PROXY` (aire a 2 m en una celda de unos 50 km).

### 6.4 Estrés térmico y ET0

- **Estrés térmico:** días con `T2M_MAX` ≥ 35 °C (configurable) por mes, con su media y su máximo entre años.
- **ET0 de Hargreaves-Samani:** ET0 = 0,0023 × (0,408 × Ra) × (Tmedia + 17,8) × √(Tmax − Tmin), en mm/día.
  - Ra es la radiación extraterrestre en MJ/m²/día, que se calcula con la latitud y el día del año (FAO-56, ec. 21).
- **ET0 FAO-56 Penman-Monteith:** si hay tiempo y los datos, es la mejor opción.
  - Entradas: `T2M_MAX`, `T2M_MIN`, `RH2M` o `T2MDEW`, `WS2M` (ya a 2 m), `ALLSKY_SFC_SW_DWN` (MJ/m²/día en la
    comunidad AG; en RE sale en kWh/m²/día) y `PS` (kPa), más la altitud, que POWER devuelve como tercera
    coordenada.
  - Hay que leer las unidades del bloque `parameters` de la respuesta, no fijarlas en el código.
- **Contraste opcional:** la ET real de MODIS MOD16 (de NASA) o la `et0_fao_evapotranspiration` de Open-Meteo, que
  no es de NASA.

### 6.5 Balance hídrico

- **Cálculo:** P − ET0 mensual (POWER `PRECTOTCORR` y la ET0 de §6.4), con su climatología y por años.
- **Salida:** los meses con déficit, el déficit anual medio y la tendencia, sin modelar el suelo.
- **Contexto:** SMAP `sm_rootzone` (fracción volumétrica, zona) y la capacidad de campo de OpenLandMap, como contexto
  de capacidad de almacenamiento.

### 6.6 Lluvia extrema (POWER diario)

- **R95p:** el umbral es el percentil 95 de los días con 1 mm o más del periodo de referencia. Se dan los días por
  año por encima del umbral y la lluvia que aportan.
- **Además:** R20mm (días con 20 mm o más, configurable) y Rx1day (el máximo diario anual).
- **Aviso:** `ZONE_SCALE_DATA`, porque el reanálisis suaviza los extremos.

### 6.7 Índice relativo de erosión

- **Factores, normalizados de 0 a 1:**
  - Pendiente: p90 de la parcela, con su escala por tramos.
  - Erosividad: Rx1day y R95p.
  - Erosionabilidad: textura y carbono orgánico de OpenLandMap; más limo y menos carbono es peor.
  - Cobertura: la fracción de meses desnudos que caen en los meses más lluviosos.
- **Combinación:** la media geométrica de los cuatro, para que un factor nulo baje el total.
- **Salida:** bajo, medio o alto, con el desglose de cada factor.
- **Texto fijo:** "Relative screening index inspired by RUSLE factors; not a soil-loss estimate."

---

## 7. Análisis de la captura de recursos

### 7.1 Google Earth Engine

**De acuerdo.** Es el núcleo, y ahorra descargar Landsat, GPM y los modelos de elevación. La captura avisa del
registro, las cuotas y la autenticación. Hay que añadir lo que falta:

- el nivel Community de 150 EECU-horas al mes;
- el modo restringido al agotar la cuota;
- Python 3.11 o superior;
- los roles de IAM (§5.4);
- que los map IDs duran unas horas.

### 7.2 NASA POWER

**De acuerdo,** con las correcciones de §3.2:

- La resolución de un punto es la nativa de la fuente, no una rejilla de 0,5°.
- `GWETROOT` es un índice, no humedad volumétrica.
- No hay ET0.
- La radiación de los meses recientes puede llevar meses de retraso.
- No hace falta clave. No hay un límite numérico publicado, pero pide no repetir la misma celda: con una petición por
  celda de 0,5° basta, y se cachea.
- Admite como mucho 20 parámetros por petición.
- El valor de relleno es −999.
- **Hay que citarlo.** Frase del proyecto: "The data was obtained from the National Aeronautics and Space
  Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy Resource (POWER) Project funded
  through the NASA Earth Science/Applied Science Program". Frase de los datos: "The data was obtained from the POWER
  Project's Daily 2.x.x version on YYYY/MM/DD". En la llamada de hoy, la API respondió como v2.10.3.

### 7.3 OpenLandMap: suelos

**De acuerdo,** y comprobado: las capas de pH, textura, carbono orgánico, densidad aparente y agua a 33 kPa están en
el catálogo oficial de GEE (IDs en §4.6). Lo de que la API REST de SoilGrids "está pausada" lo dice la documentación
de ISRIC del 18-12-2025, aunque unas FAQ de enero y febrero de 2026 hablan de una API beta con límite de 5 llamadas
por minuto sin repetir lo de la pausa. Es poco fiable para una demo en cualquier caso. Hay que añadir:

- Que es CC-BY-SA 4.0, con obligación de compartir igual.
- Que es una estimación estática de 250 m sobre datos de 1950 a 2018.
- Que la "retención de agua" se representa como agua a 33 kPa, es decir, a capacidad de campo.

### 7.4 FAO ECOCROP y GAEZ

**De acuerdo con la decisión** de precargar un catálogo de 8 a 12 cultivos en JSON, sin consultar GAEZ en cada
petición.

- ECOCROP como herramienta independiente se cerró hacia 2015 y hoy se consulta dentro de la plataforma GAEZ.
  Confirmado en la v4; en la v5 no está claro.
- La cifra de "más de 2.500 especies" está [sin verificar]. Las fuentes de la FAO hablan de más de 2.000.
- Los rangos de ECOCROP son gruesos: temperatura, lluvia anual, pH, altitud y latitud, cada uno con su mínimo y su
  máximo absolutos y óptimos. Sirven para filtrar la aptitud climática, no para razonar sobre rotaciones.

El catálogo necesita además, por cultivo, estos atributos de rotación, cada uno con su fuente:

- familia botánica (para cortar el ciclo de plagas);
- si fija nitrógeno;
- la profundidad de raíz;
- el residuo que aporta;
- la demanda de agua o su coeficiente de cultivo Kc (FAO-56, tabla 12);
- sus ventanas de siembra y cosecha por hemisferio;
- su sensibilidad a heladas y a calor por fase;
- su valor forrajero.

Ese catálogo es del módulo de rotaciones, no de la capa de datos. La capa de datos solo tiene que devolver las
variables con las que el catálogo se compara: temperaturas, lluvia anual, pH, altitud y latitud.

GAEZ v5: `data.apps.fao.org/gaez`, con descargas en bloque, licencia CC BY 4.0 y los términos de la FAO. No está en
GEE.

### 7.5 SRTM: topografía

**De acuerdo.** Recomiendo NASADEM, el reprocesado de SRTM que hizo NASA, con la misma cobertura y mejor calidad. Hay
que avisar fuera de 60° N a 56° S y pasar entonces a `COPERNICUS/DEM/GLO30_2024_1`, no al ID antiguo.

### 7.6 Open-Meteo: complemento

**De acuerdo con matices.**

- **A favor:** es gratis para uso no comercial (menos de 10.000 llamadas al día, 5.000 por hora y 600 por minuto),
  no pide clave y devuelve JSON. Su previsión incluye ET0 FAO-56 (`et0_fao_evapotranspiration`) y variables de suelo
  [búsqueda; los nombres exactos de las capas de humedad cambian según el endpoint].
- **No es de NASA.** Para Relevance, la ET0 principal debe salir de POWER. Open-Meteo sirve de contraste o de
  previsión a corto plazo.
- **Licencia:** los datos de la API son CC BY 4.0 (https://open-meteo.com/en/license). Exige poner un enlace junto a
  cada sitio donde se muestren, p. ej. "Weather data by Open-Meteo.com". La API gratuita es solo para uso no comercial
  (https://open-meteo.com/en/terms). El código del servidor es AGPLv3, pero no nos afecta porque solo llamamos a la
  API.
- **Alcance:** "¿cuándo debería sembrar?" es una pregunta de días, y el reto va de rotaciones a varios años. Es un
  añadido vistoso para la demo, no el núcleo. Encaja como "próximos 7 días" en la ficha de la parcela si sobra
  tiempo, y se marca como pronóstico (`data_type: "model"`, fuente no NASA).

### 7.7 Lo que le falta a la captura

- **SMAP:** el primer conjunto de datos del reto, en GEE y de NASA.
- **Landsat como serie de NDVI y NDTI:** la captura lo cita solo dentro de GEE.
- **El tipo de cultivo** para la rotación actual: CDL, EUCROPMAP o WorldCereal.
- **IMERG o la lluvia extrema** como indicador propio.
- **MODIS MOD16:** la ET real de NASA, como contraste del balance.
- **La declaración de IA y las licencias** que exige el envío.

---

## 8. Tabla de fuentes para el README y el jurado

| Fuente | ID o endpoint | ¿NASA? | Tipo | Resolución | Periodo | Cobertura | Licencia o términos | Uso en la app |
|---|---|---|---|---|---|---|---|---|
| Landsat 8 y 9 C2 L2 | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | Sí (con USGS) | satellite | 30 m | 2013 o 2021 a hoy | Global | Dominio público | NDVI, NDTI, campo desnudo, vulnerabilidad |
| SMAP L4 | `NASA/SMAP/SPL4SMGP/008` | Sí | model (asimila satélite) | Unos 9 km | 2015 a hoy | Global | Datos abiertos de NASA | Humedad en la zona radicular y anomalías |
| NASA POWER | API diaria, comunidad AG | Sí | reanalysis y satellite | 0,5° × 0,625° y 1° | 1981 (radiación desde 1984) a hoy | Global | Citación obligatoria | Heladas, calor, ET0, balance, lluvia extrema |
| NASADEM | `NASA/NASADEM_HGT/001` | Sí | satellite (radar) | 30 m | 2000 | 60° N a 56° S | Datos abiertos de NASA | Pendiente, factor de erosión |
| GPM IMERG V07 | `NASA/GPM_L3/IMERG_V07` | Sí | satellite_gauge_merged | 0,1° | 1998 a hoy; provisional desde 2025-10 | Global | Datos abiertos de NASA | Totales de contraste (si da tiempo) |
| MODIS MOD16A2GF | `MODIS/061/MOD16A2GF` | Sí | satellite y model | 500 m | 2000 a 2025 | Global | Datos abiertos de NASA | ET real de contraste (opcional) |
| OpenLandMap | `OpenLandMap/SOL/...` | No | model | 250 m | Estático | Global | CC-BY-SA 4.0 | pH, textura, carbono orgánico, capacidad de campo |
| WorldCereal | `ESA/WorldCereal/2021/MODELS/v100` | No (ESA, agencia socia) | satellite (clasificación) | 10 m | 2021 | Global | CC BY 4.0 | Cultivo de 2021 |
| EUCROPMAP | `JRC/D5/EUCROPMAP/V1` | No (JRC) | satellite (clasificación) | 10 m | 2018 y 2022 | UE | CC BY 4.0 | Cultivos de 2018 y 2022 |
| USDA CDL | `USDA/NASS/CDL` | No | satellite (clasificación) | 30 m | 1997 a 2024 | EE. UU. continental | Dominio público | Rotación histórica |
| Sentinel-2 SR + Cloud Score+ | `COPERNICUS/S2_SR_HARMONIZED`, `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | No (ESA, agencia socia) | satellite | 10 m | 2017 a hoy | Global | Términos de Copernicus Sentinel | NDVI a 10 m (si da tiempo) |
| FAO ECOCROP y GAEZ | Portal de GAEZ | No | Base de conocimiento | | | Global | CC BY 4.0 y términos de la FAO | Catálogo de cultivos (módulo de rotaciones) |
| Open-Meteo | API de previsión | No | model (pronóstico) | Según el modelo | Próximos días | Global | Datos CC BY 4.0 con enlace junto al dato; API gratuita solo no comercial | Previsión de 7 días (opcional) |
| GLDAS-2.1 Noah | `NASA/GLDAS/V021/NOAH/G025/T3H` | Sí | model (asimilación) | 0,25° | 2000 a unos meses antes de hoy | Global | Datos abiertos de NASA | Alternativa de NASA a ERA5-Land (no entra este fin de semana) |
| Google Earth Engine | Plataforma | No | Herramienta | | | | Términos de Earth Engine (no comercial) | Cálculo |

Las citas completas de cada conjunto de datos están en sus páginas del catálogo de GEE (apartado "Citations"); se
copian en `provenance.citations` y en el README.

---

## 9. Región: decisión pendiente

No se sabe en qué región están las parcelas. Opciones, con la recomendada primero:

1. **Solo fuentes globales por ahora (recomendada).** Landsat, SMAP, POWER, NASADEM (o GLO-30), OpenLandMap y
   WorldCereal funcionan en cualquier sitio. Las capas regionales se añaden detrás de un `region` configurable cuando
   la demo ya funcione.
2. **España o UE.** Sumar EUCROPMAP para la rotación de 2018 y 2022. Sentinel-2 aporta los 10 m. La Agencia Espacial
   Española figura entre las socias de 2026, y usar datos de socios "se anima mucho". AEMET, SIGPAC y las
   declaraciones de la PAC podrían aportar datos locales [sin verificar el acceso; fuera de este fin de semana].
3. **EE. UU.** Subir CDL al producto mínimo: da la rotación real de cada año (1997 a 2024) y resuelve la "rotación
   actual" sin preguntársela al agricultor. SSURGO y gNATSGO, OpenET y PRISM se suman después.

---

## 10. Riesgos y mitigaciones

| Riesgo | Probabilidad | Efecto | Mitigación |
|---|---|---|---|
| No acabar a tiempo (cierre el domingo a las 23:59 hora local) | Alta | No hay envío | Recorte de §3.4; POWER y los derivados primero, porque no dependen de GEE |
| GEE sin registrar, o la verificación no comercial pendiente | Media | Sin NDVI ni SMAP | Empezar por POWER; comprobar `ee.Initialize` en la primera hora; tener demos precalculadas |
| Cuota de 150 EECU-horas o modo restringido | Media | Respuestas lentas | Caché, parcelas de demo precalculadas, IMERG solo si da tiempo |
| Petición de más de 5 minutos o falta de memoria | Baja con parcelas de hasta 1.000 ha | 504 | Módulos separados con timeout, sin pedir colecciones semihorarias de 10 años |
| Caducidad del map ID durante la demo | Alta en vídeos largos | Teselas rotas | Regenerar antes de grabar, o usar una captura estática en el vídeo |
| Python inferior a 3.11 en el entorno | Media | Falla la autenticación | Fijar Python 3.11 o superior en el proyecto |
| Confundir `GWETROOT` con humedad volumétrica | Alta si no se avisa | El jurado lo verá en Validity | Etiquetarlo "soil wetness index (0-1)" |
| NDVI bajo leído como suelo desnudo | Alta | Erosión sobreestimada | NDTI, y separar "desnudo" de "rastrojo" |
| Declaración de IA olvidada | Media | Penaliza en originalidad | Sección en el README, cabeceras y campo de metadatos |
| Licencias sin declarar | Media | NASA no publica el proyecto | Tabla de §8 en el README |
| La radiación de CERES con retraso | Media | Faltan datos recientes en la ET0 | Avisar con `SOLAR_DATA_LAG`; usar Hargreaves, que no necesita radiación |
| `GWETROOT` constante (0,5) | Observado en 3 días | Indicador inútil | Mirar la varianza; si es plano, ocultarlo y usar SMAP |

---

## 11. Plan para lo que queda del fin de semana

Las horas son orientativas y empiezan cuando se lance el prompt. El domingo por la tarde se reserva para el vídeo de
30 segundos o las 7 diapositivas, la página del proyecto y el envío.

| Bloque | Duración | Qué | Depende de GEE |
|---|---|---|---|
| 1 | 1 h | Inspeccionar el repositorio, entorno con Python 3.11 o superior, `.env.example`, comprobar `ee.Initialize` | Sí (solo comprobar) |
| 2 | 2 h | `power.py` y los derivados de clima (heladas, calor, ET0, balance, extremos) | No |
| 3 | 3 h | `landsat.py` (NDVI y NDTI), `smap.py`, `terrain.py`, `soil.py` | Sí |
| 4 | 2 h | `derived.py` completo (campo desnudo, vulnerabilidad, erosión), el contrato JSON y el endpoint | No |
| 5 | 1 h | Parcelas de demo precalculadas (2 o 3, en la región del equipo) | Sí |
| 6 | 1 a 2 h | Teselas de NDVI y pendiente; IMERG o Sentinel-2 si sobra tiempo | Sí |
| 7 | 1 h | Tests finales (humo y fórmulas), README con la tabla de fuentes, licencias y la declaración de IA | No |

---

## 12. Para la presentación

- **Relevance:** "SMAP, Landsat, POWER, NASADEM and IMERG are the core inputs." Enseñar el campo `nasa: true` y la
  tabla de fuentes.
- **Validity:** enseñar en pantalla un indicador con su método, su umbral, su resolución, su confianza y sus avisos.
  La honestidad sobre la escala (zona frente a parcela) es un punto fuerte, no una debilidad.
- **Presentation:** 30 segundos dan para esto: elegir una parcela, ver tres rotaciones lado a lado, y en cada una el
  porqué, la evidencia, las carencias y lo que debe revisar un experto local.
- **IA:** declararla de forma visible en el README y en la página del proyecto.

---

## 13. Preguntas abiertas para el equipo

Cada pregunta lleva sus opciones, con la recomendada primero.

1. **Región de las parcelas:** (a) solo fuentes globales por ahora; (b) España o UE; (c) EE. UU. Ver §9.
2. **`EE_PROJECT_ID`:** el ID del proyecto de Cloud registrado. Hay que comprobar que la verificación no comercial
   está hecha. Si no está, se empieza por POWER.
3. **Nombre del endpoint:** (a) `/api/parcel/analyze`; (b) el que ya exista en el repositorio.
4. **Ejecución:** (a) síncrona con caché y demos precalculadas; (b) en segundo plano, con un ID de trabajo y
   consulta periódica (más robusta, pero cuesta más tiempo).
5. **Parcelas de demo:** 2 o 3 parcelas agrícolas reales de la región, con geometría. Hay que pedirlas al equipo; si
   no las hay, se elige una de muestra y se dice.
6. **Open-Meteo:** (a) fuera por ahora; (b) solo la previsión de 7 días en la ficha de la parcela.

---

## 14. Lo que queda sin verificar

Resuelto en una segunda pasada el mismo día:

- La pendiente sale en grados [doc].
- La URL de teselas es `tile_fetcher.url_format` [doc y búsqueda].
- El ID de GLDAS es `NASA/GLDAS/V021/NOAH/G025/T3H` [doc].
- Los datos de Open-Meteo son CC BY 4.0 [doc].
- IMERG mensual va en mm/h [búsqueda].

Sigue sin verificar:

- Que la banda `precipitation` de IMERG mensual vaya en mm/h (solo se vio `randomError`), y la fecha final real de
  esa colección.
- El patrón exacto de autenticación en Cloud Run.
- La escala de arcilla, arena y carbono orgánico en OpenLandMap.
- El estado actual de la API REST de SoilGrids.
- Si ECOCROP sigue disponible en GAEZ v5, y el número de especies.
- Los nombres exactos de las variables de suelo de Open-Meteo según el endpoint. La de ET0 es
  `et0_fao_evapotranspiration` [búsqueda].
- Que el uso en un hackathon cuente como no comercial a efectos de Earth Engine. La página no lo nombra; se interpreta
  como no comercial si no hay pago ni cliente.
- La fecha de inicio del bandeo SLC-off de Landsat 7.
- Si se añadieron recursos a la página del reto entre el 28 de octubre y hoy (no se comparó con una versión anterior).

---

## 15. Fuentes

**El reto**
- https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/
- https://www.spaceappschallenge.org/resources/project-submission-guide/
- https://www.spaceappschallenge.org/resources/judging-awards-guide/
- https://www.spaceappschallenge.org/legal/

**Earth Engine: acceso, cuotas y teselas**
- https://developers.google.com/earth-engine/guides/access
- https://developers.google.com/earth-engine/guides/noncommercial_tiers
- https://developers.google.com/earth-engine/guides/transition_to_cloud_projects
- https://developers.google.com/earth-engine/guides/auth
- https://developers.google.com/earth-engine/guides/access_control
- https://developers.google.com/earth-engine/guides/usage
- https://developers.google.com/earth-engine/guides/processing_environments
- https://developers.google.com/earth-engine/guides/best_practices
- https://developers.google.com/earth-engine/guides/reducers_reduce_region
- https://developers.google.com/earth-engine/reference/rest/v1/projects.maps/create
- https://pypi.org/project/earthengine-api/

**Catálogo de Earth Engine.** La base es `https://developers.google.com/earth-engine/datasets/catalog/` más el ID con
"/" cambiado por "_". Fichas consultadas:
- LANDSAT_LC08_C02_T1_L2, LANDSAT_LC09_C02_T1_L2
- USGS_SRTMGL1_003, NASA_NASADEM_HGT_001, COPERNICUS_DEM_GLO30_2024_1
- NASA_GPM_L3_IMERG_V07, NASA_GPM_L3_IMERG_MONTHLY_V07
- NASA_SMAP_SPL4SMGP_008, NASA_SMAP_SPL3SMP_E_006
- COPERNICUS_S2_SR_HARMONIZED, GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED
- MODIS_061_MOD13Q1, MODIS_061_MOD16A2GF
- ECMWF_ERA5_LAND_DAILY_AGGR
- USDA_NASS_CDL, JRC_D5_EUCROPMAP_V1, ESA_WorldCereal_2021_MODELS_v100
- UCSB-CHG_CHIRPS_DAILY
- OpenLandMap_SOL_SOL_PH-H2O_USDA-4C1A2A_M_v02, OpenLandMap_SOL_SOL_TEXTURE-CLASS_USDA-TT_M_v02,
  OpenLandMap_SOL_SOL_ORGANIC-CARBON_USDA-6A1C_M_v02, OpenLandMap_SOL_SOL_WATERCONTENT-33KPA_USDA-4B1C_M_v01
- NASA_ECOSTRESS_L2T_LSTE_V2, NASA_GRACE_MASS_GRIDS_V04_LAND, OpenET_ENSEMBLE_CONUS_GRIDMET_MONTHLY_v2_0

**NASA POWER**
- https://power.larc.nasa.gov/docs/services/api/
- https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- https://power.larc.nasa.gov/docs/faqs/data/
- https://power.larc.nasa.gov/docs/referencing/

**Catálogo comunitario de GEE**
- https://gee-community-catalog.org/projects/isric/
- https://gee-community-catalog.org/projects/gnatsgo/

**SoilGrids**
- https://docs.isric.org/globaldata/soilgrids/
- https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html

**ECOCROP y GAEZ**
- https://www.fao.org/geospatial/data-and-tools/data-portals/ecocrop/
- https://www.fao.org/land-water/databases-and-software/gaez/en

**Open-Meteo**
- https://open-meteo.com/en/terms
- https://openmeteo.substack.com/p/reference-evapotranspiration-for

**NDTI:** Van Deventer et al. (1997); resumen en https://ntrs.nasa.gov/api/citations/20230014116/downloads/remotesensing-14-06128-v3.pdf

**FAO-56** (Allen et al., 1998), para Hargreaves, Penman-Monteith, Ra y la tabla de Kc.

---

## Anexo A. El prompt anterior del equipo

Su contenido útil está incorporado y corregido en §3 y §5, y el prompt nuevo (`PROMPT-field-shift-backend.md`) lo
reemplaza. Va completo al final de este anexo para que quede trazable. Lo que cambia:

- Se acota el tiempo al fin de semana.
- Tests solo al final.
- SMAP, el suelo (OpenLandMap) y NDTI entran en el producto mínimo.
- IMERG baja a "si da tiempo".
- POWER va primero.
- Se añaden la declaración de IA y las licencias.
- Las parcelas de demo se precalculan.
- Se corrigen los IDs y las unidades.

### A.1 Las notas del equipo que acompañaban al prompt anterior (resumen fiel)

- Se leyó la página del reto (objetivo, contexto, consideraciones y 24 recursos) a partir de los datos embebidos,
  porque la web carga con JavaScript.
- El reto pide comparar al menos 3 estrategias, incluida la actual, con el porqué, la evidencia, los beneficios, las
  carencias y los riesgos. Por eso el backend devuelve indicadores trazables y no solo números. **Corrección:** el
  reto dice "may", no "must" (§2.1).
- Se añadieron como indicadores derivados: periodos desnudos, épocas vulnerables, heladas, calor, balance hídrico,
  erosión y lluvias extremas.
- Se añadió NASA POWER, porque es una API REST gratuita y sin autenticación. **Correcciones** en §3.2, filas 1 a 3.
- Sentinel-2 queda como fase posterior a Landsat.
- Casi la mitad de los recursos solo cubre EE. UU., de ahí la rama por región. Confirmado en §2.3.
- GRACE solo sirve como contexto regional, y ECOSTRESS probablemente no está en GEE. **Matiz:** está, pero con
  cobertura mínima (§3.2, fila 18).
- El endpoint pasa a `/api/parcel/analyze` porque POWER no pasa por GEE.
- Antes de usarlo: fijar la región, y subir CDL si es EE. UU. Comprobar si faltaba algún documento de recursos: hoy
  no hay adjuntos (§2.4).

### A.2 Estructura del prompt anterior (en español, unos 9 KB)

1. Contexto del reto y alcance: solo la capa de datos, sin recomendación.
2. Contexto técnico: `EE_PROJECT_ID`, la región sin rellenar, e inspeccionar el repositorio.
3. Reglas generales: verificar los IDs; calcular en el servidor; el NDVI no es fertilidad; distinguir satélite,
   reanálisis y modelo.
4. Fase 1: autenticación por ADC; NDVI de Landsat 8 y 9 con QA_PIXEL y QA_RADSAT, en medianas mensuales; el endpoint
   con validación y buffer; prueba de humo real y tests con GEE simulado.
5. Fase 2: SRTM (altitud y pendiente) e IMERG V07 (totales y días extremos con p95).
6. Fase 3: el cliente de POWER (comunidad AG, diario, centroide, reintentos, caché).
7. Fase 4: los derivados (desnudo, vulnerabilidad, heladas, calor, P − ET0, erosión relativa).
8. Fase 5: las teselas con `getMapId`, su leyenda y su `expires_at`, y la geometría en GeoJSON.
9. Fase 6 opcional: Sentinel-2 con Cloud Score+, MODIS, SMAP, ERA5-Land, CDL y SSURGO o SoilGrids y GAEZ; ni
   ECOSTRESS ni GRACE sin consultar.
10. El formato JSON versionado con un ejemplo, y los avisos mínimos.
11. Seguridad: credenciales fuera del repositorio y del frontend, límite de frecuencia y caché.
12. Entregables: un módulo por fuente, los tests, un README con la tabla de fuentes y un informe por fase.

Las diferencias con el prompt nuevo se resumen en la lista de arriba. Las correcciones de hecho están en §3.2.
