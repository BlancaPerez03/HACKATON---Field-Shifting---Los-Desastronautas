"""Crop catalogue (team CSV, US crops) parsed into typed records.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
The CSV (backend/catalog/crops_us.csv) was compiled by the team and is the source of truth;
this module only parses it. Spanish number format: "650.000" = 650000, "11,71" = 11.71.
Water columns come in ml/m2 and are converted to mm (1 mm = 1 L/m2 = 1000 ml/m2).
"""
import csv
import json
import re
from functools import lru_cache

from . import config

CSV_PATH = config.ROOT / "backend" / "catalog" / "crops_us.csv"
SOURCE = ("Team crop catalogue 'Fichas de cultivos EE. UU.' (backend/catalog/crops_us.csv). "
          "Per-attribute references are not yet cited; values must be checked against FAO ECOCROP, "
          "FAO-56 and USDA sources before submission.")

# CSV column -> (key, parser)
# Each tuple maps a Spanish column header of the team CSV to an English key and says how to parse
# the text: "str" (keep text), "int", "num" (Spanish decimal), "range" ("5,8–7,0"), "ml_to_mm".
_COLS = [
    ("Cultivo", "name_es", "str"),
    ("Siembra / brotación: mes inicio", "sowing_start_month", "int"),
    ("Siembra / brotación: mes fin", "sowing_end_month", "int"),
    ("Cosecha: mes inicio", "harvest_start_month", "int"),
    ("Cosecha: mes fin", "harvest_end_month", "int"),
    ("T mín. de crecimiento (°C)", "t_min_growth_c", "num"),
    ("T óptima mín. (°C)", "t_opt_min_c", "num"),
    ("T óptima máx. (°C)", "t_opt_max_c", "num"),
    ("Días mín. sin heladas", "min_frost_free_days", "num"),
    ("Agua del ciclo (ml/m²)", "season_water_mm", "ml_to_mm"),
    ("Pico de agua (ml/m²·día)", "peak_water_mm_day", "ml_to_mm"),
    ("Rendimiento medio EE. UU. (t/ha)", "us_mean_yield_t_ha", "num"),
    ("Productividad del agua (kg/m³)", "water_productivity_kg_m3", "num"),
    ("Grados-día necesarios (GDD, °C·día)", "gdd_required", "num"),
    ("Base del GDD (°C)", "gdd_base_c", "num"),
    ("Tipo fotosintético", "photosynthesis", "str"),
    ("Clima en el que mejor rinde", "best_climate_es", "str"),
    ("Suelo recomendado", "soil_es", "str"),
    ("pH óptimo", "ph_optimum", "range"),
    ("Minerales clave", "key_nutrients", "str"),
    ("Fertilización N / P₂O₅ / K₂O (kg/ha)", "fertilisation_npk_kg_ha", "str"),
    ("Tolerancia a la sequía (1–5, 5 = muy tolerante)", "drought_tolerance_1_5", "int"),
    ("Presión de plagas (1–5, 5 = muy alta)", "pest_pressure_1_5", "int"),
    ("Balance de nitrógeno (kg N/ha; positivo = aporta, negativo = extrae)", "n_balance_kg_ha", "num"),
    ("Balance de fósforo (kg P₂O₅/ha; negativo = extrae)", "p2o5_balance_kg_ha", "num"),
    ("Balance de potasio (kg K₂O/ha; negativo = extrae)", "k2o_balance_kg_ha", "num"),
    ("Principales plagas y enfermedades", "pests_diseases_es", "str"),
]

NAME_EN = {
    "Maíz": "Corn (maize)", "Soja": "Soybean", "Alfalfa (heno, perenne)": "Alfalfa (hay, perennial)",
    "Trigo de invierno": "Winter wheat", "Remolacha azucarera": "Sugar beet",
    "Caña de azúcar (perenne)": "Sugarcane (perennial)", "Patata": "Potato", "Sorgo": "Sorghum",
    "Algodón": "Cotton", "Arroz": "Rice", "Cebada": "Barley", "Cacahuete": "Peanut",
    "Tomate de industria": "Processing tomato", "Uva (perenne)": "Grape (perennial)",
    "Almendro (perenne)": "Almond (perennial)",
}


def parse_number(s):
    """Spanish-format number -> float. '650.000' -> 650000; '11,71' -> 11.71; '10,' -> 10."""
    s = (s or "").strip()
    if not s:
        return None
    # In Spanish "." separates thousands and "," is the decimal mark: remove the dots first,
    # then turn the comma into a Python decimal point.
    s = s.replace(".", "").replace(",", ".").rstrip(".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_range(s):
    """'5,8–7,0' -> [5.8, 7.0]."""
    parts = re.split(r"\s*[–-]\s*", (s or "").strip())
    vals = [parse_number(p) for p in parts if p]
    return vals if len(vals) == 2 and None not in vals else None


def _parse(kind, raw):
    if kind == "str":
        return (raw or "").strip() or None
    if kind == "range":
        return parse_range(raw)
    v = parse_number(raw)
    if v is None:
        return None
    if kind == "int":
        return int(v)
    if kind == "ml_to_mm":
        return round(v / 1000, 1)
    return v


PARAMS_PATH = config.ROOT / "backend" / "catalog" / "crop_params.json"


@lru_cache(maxsize=1)
def load_params():
    """Agronomic parameters with sources (Kc, Ky, cardinal temperatures...) and documented corrections."""
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)   # the CSV is read once per server run, then kept in memory
def load_catalog():
    # "utf-8-sig" removes the invisible BOM character that Excel/Sheets put at the start of the file.
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    params = load_params()
    crops = []
    for row in rows:
        c = {key: _parse(kind, row.get(col)) for col, key, kind in _COLS}
        c["id"] = re.sub(r"[^a-z0-9]+", "_", NAME_EN.get(c["name_es"], c["name_es"]).lower()).strip("_")
        c["name_en"] = NAME_EN.get(c["name_es"], c["name_es"])
        c["perennial"] = "perenne" in (c["name_es"] or "").lower()
        # Merge the sourced parameters; a correction replaces the CSV value and keeps the old one
        # and the reason, so the page can show what was changed and why.
        p = dict(params["crops"].get(c["id"], {}))
        corr = p.pop("corrections", {})
        c.update(p)
        c["corrections"] = []
        for k, v in corr.items():
            c["corrections"].append({"field": k, "was": c.get(k), "now": v["value"], "reason": v["reason"]})
            c[k] = v["value"]
        crops.append(c)
    return {"source": SOURCE, "params_source": "backend/catalog/crop_params.json",
            "references": params["_references"], "shared": params["_shared"],
            "units": {"season_water_mm": "mm per season (catalogue reference; the checks use Kc x ET0)",
                      "peak_water_mm_day": "mm/day", "gdd_required": "degC-day"},
            "crops": crops}
