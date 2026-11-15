"""Farm budget check for one crop on one parcel: can the farmer afford it, and when does it pay?

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Pure functions. Not a yield or price forecast: the farmer supplies (or accepts sourced defaults for)
expected yield, price and cost; the tool returns totals, break-even yield and price, and a what-if
table for lower yields. Defaults come from backend/catalog/economics_us.json with source and year.
"""
import json
from functools import lru_cache

from . import config
from .contract import r
from .crops import load_catalog

ECON_PATH = config.ROOT / "backend" / "catalog" / "economics_us.json"
ACRE_HA = 0.40468564224
SENSITIVITY = (0, -10, -20, -30)


@lru_cache(maxsize=1)
def load_economics():
    return json.loads(ECON_PATH.read_text(encoding="utf-8"))


def defaults(crop_id):
    """Sourced default inputs for a crop (per hectare, USD, tonnes). Missing values stay None."""
    econ = load_economics()
    crop = next((c for c in load_catalog()["crops"] if c["id"] == crop_id), None)
    if crop is None:
        raise KeyError(crop_id)
    e = econ["crops"].get(crop_id, {})
    src = econ["sources"]
    bu = e.get("bushel_kg")
    out = {"crop_id": crop_id, "crop": crop["name_en"], "bushel_kg": bu, "notes": []}

    # Unit conversions (US budgets use bushels and acres; the app works in tonnes and hectares):
    #   t/ha  = bu/acre * kg per bushel / 1000 / 0.4047 ha per acre
    #   USD/t = USD/bu / (tonnes per bushel)
    y = e.get("yield")
    if y and y["unit"] == "bu/acre" and bu:
        out["yield_t_ha"] = r(y["value"] * bu / 1000 / ACRE_HA, 2)
        out["yield_source"] = f"{y['label']} ({y['value']} bu/acre) — {src[y['source']]['name']}"
    elif crop.get("us_mean_yield_t_ha"):
        out["yield_t_ha"] = crop["us_mean_yield_t_ha"]
        out["yield_source"] = f"US mean yield — {src['team_catalogue']['name']} (not field-specific)"
    else:
        out["yield_t_ha"], out["yield_source"] = None, "No default: enter your expected yield"

    p = e.get("price")
    if p and p["unit"] == "USD/bu" and bu:
        out["price_usd_t"] = r(p["value"] / (bu / 1000), 2)
        out["price_source"] = f"{p['value']:.2f} USD/bu — {src[p['source']]['name']}"
    else:
        out["price_usd_t"], out["price_source"] = None, "No default: enter your expected sale price"

    if e.get("cost_usd_acre"):
        out["cost_usd_ha"] = r(e["cost_usd_acre"] / ACRE_HA, 0)
        s = src[e["cost_source"]]
        out["cost_source"] = f"{e['cost_label']}: {e['cost_usd_acre']:.2f} USD/acre — {s['name']}"
        out["notes"].append(s["note"])
        if not e.get("cost_verified", False):
            out["notes"].append("Cost default read from a secondary summary; check the original publication.")
    else:
        out["cost_usd_ha"], out["cost_source"] = None, "No default: enter your costs per hectare"
    if p:
        out["notes"].append(src[p["source"]]["note"])
    return out


def budget(area_ha, yield_t_ha, price_usd_t, cost_usd_ha, available_usd=None,
           irrigation_mm=0.0, irrigation_cost_usd_mm_ha=0.0, bushel_kg=None):
    """Budget for the whole parcel. Returns None-valued fields when an input is missing."""
    missing = [n for n, v in (("expected yield", yield_t_ha), ("sale price", price_usd_t),
                              ("cost per hectare", cost_usd_ha)) if v in (None, "")]
    irr_ha = (irrigation_mm or 0) * (irrigation_cost_usd_mm_ha or 0)
    out = {"area_ha": r(area_ha, 2), "area_acres": r(area_ha / ACRE_HA, 1), "missing_inputs": missing,
           "irrigation_cost_usd_ha": r(irr_ha, 0)}
    if cost_usd_ha not in (None, ""):
        cost_ha = cost_usd_ha + irr_ha
        out["cost_usd_ha"] = r(cost_ha, 0)
        out["total_cost_usd"] = r(cost_ha * area_ha, 0)
        if available_usd not in (None, ""):
            gap = available_usd - cost_ha * area_ha
            out["affordable"] = gap >= 0
            out["cash_gap_usd"] = r(gap, 0)
    if missing:
        return out
    cost_ha = cost_usd_ha + irr_ha
    rev_ha = yield_t_ha * price_usd_t
    # Break-even yield = the yield where income equals cost (cost / price).
    # Break-even price  = the price where income equals cost (cost / yield).
    # Yield buffer      = how much (in %) the yield can fall before the margin becomes negative.
    out.update({
        "revenue_usd_ha": r(rev_ha, 0), "revenue_usd": r(rev_ha * area_ha, 0),
        "margin_usd_ha": r(rev_ha - cost_ha, 0), "margin_usd": r((rev_ha - cost_ha) * area_ha, 0),
        "breakeven_yield_t_ha": r(cost_ha / price_usd_t, 2) if price_usd_t else None,
        "breakeven_price_usd_t": r(cost_ha / yield_t_ha, 2) if yield_t_ha else None,
        "yield_buffer_pct": r((1 - cost_ha / rev_ha) * 100, 1) if rev_ha else None,
        "what_if": [{"yield_change_pct": d, "yield_t_ha": r(yield_t_ha * (1 + d / 100), 2),
                     "margin_usd": r((yield_t_ha * (1 + d / 100) * price_usd_t - cost_ha) * area_ha, 0)}
                    for d in SENSITIVITY],
    })
    if bushel_kg:
        t_per_bu = bushel_kg / 1000
        out["breakeven_yield_bu_acre"] = r(out["breakeven_yield_t_ha"] / t_per_bu * ACRE_HA, 1)
        out["breakeven_price_usd_bu"] = r(out["breakeven_price_usd_t"] * t_per_bu, 2)
    out["note"] = ("Budget arithmetic on your inputs, not a forecast. Costs from the defaults include land rent, "
                   "machinery and labour (economic costs), so the cash you actually spend may be lower.")
    return out
