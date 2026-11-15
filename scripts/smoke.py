"""Smoke run against the real APIs on the demo parcels (bypasses all caches for responses).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Usage: python -m scripts.smoke
"""
import json
import time

from backend import config
from backend.analyze import build, default_dates
from backend.geometry import prepare


def trim(out):
    """Keep only the most useful numbers of a full response so the printed output stays readable."""
    ind = out["indicators"]
    a = ind.get("agroclimate_power")
    s = {"request": out["request"],
         "populated": [k for k, v in ind.items() if v],
         "data_gaps": [f"{g['indicator']}: {g['code']}" for g in out["data_gaps"]],
         "warnings": [w["code"] for w in out["warnings"]]}
    if a:
        s["power"] = {"api": a["power_api_version"], "years": a["years_complete"],
                      "et0_mm_yr": a["et0"]["annual_mean_mm"],
                      "p_minus_et0_mm_yr": a["water_balance"]["annual_mean_p_minus_et0_mm"],
                      "last_spring_frost_0c": a["frost"]["air_frost_0c"]["last_spring_frost"],
                      "extremes": a["precip_extremes"]["mean_per_year"],
                      "july": a["monthly_climatology"][6]}
    for k in ("ndvi", "soil_moisture_smap", "terrain", "soil_openlandmap", "crop_type"):
        v = ind.get(k)
        if v:
            s[k] = {kk: vv for kk, vv in v.items()
                    if kk in ("confidence", "scale_note", "slope_deg", "elevation_m", "ph_h2o",
                              "organic_carbon_g_kg", "clay_pct", "texture_class")}
            s[k]["warnings"] = [w["code"] for w in v["warnings"]]
            if k == "ndvi":
                s[k]["climatology"] = [c["median"] for c in v["climatology"]]
            if k == "crop_type":
                s[k]["years"] = [f"{y['year']}: " + ", ".join(f"{d['name']} {d['fraction']}" for d in y["dominant"][:2])
                                 for y in v["years"]]
    s["derived"] = {k: (v and {"value": v.get("value"), "confidence": v.get("confidence")})
                    for k, v in out["derived"].items()}
    return s


def main():
    parcels = json.loads((config.ROOT / "scripts" / "demo_parcels.json").read_text())["parcels"]
    start, end = default_dates()
    for p in parcels:
        t = time.time()
        out = build(prepare(p["geometry"]), start, end)
        print(f"=== {p['id']}  ({time.time() - t:.1f} s)")
        print(json.dumps(trim(out), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
