"""Reality check of the crop screening: run it on US reference sites with well-known agriculture.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Run: python -m scripts.validate_crops            (downloads NASA POWER once per site, then cached)
     python -m scripts.validate_crops --irrigated (assume irrigation covers the whole water shortfall)

For each site we list crops that are grown commercially there (USDA NASS county statistics) and
crops that are not viable there for climate reasons. The script prints the screening group of every
crop and flags two kinds of disagreement:
  MISS  a crop grown commercially at the site came out "not recommended"
  FALSE a crop that is not viable at the site came out "recommended" or "possible"
Water is judged separately with --irrigated because many of these sites (California, Idaho, Texas
High Plains, Washington) farm under irrigation; rainfed, their crops are expected to fail on water.
Soil pH and last year's crop are left out (unknown for a reference point), so only climate checks run.
"""
import sys

from backend import config
from backend.analyze import default_dates
from backend.simulate import screen_crops
from backend.sources import power

# Sources for "grown": USDA NASS Quick Stats / Census of Agriculture 2022 county rankings, state
# crop profiles (LSU AgCenter sugarcane, UF/IFAS EAA, Texas A&M High Plains cotton, NDSU, UGA, UI,
# WSU). "not_viable" lists only crops excluded by climate (winter cold, season length, heat, chilling,
# humidity), not by markets.
SITES = [
    {"name": "Ames, IA (Corn Belt)", "lat": 42.02, "lon": -93.77,
     "grown": ["corn_maize", "soybean", "alfalfa_hay_perennial"],
     "not_viable": ["sugarcane_perennial", "almond_perennial", "cotton", "peanut"]},
    {"name": "Fresno, CA (San Joaquin Valley)", "lat": 36.75, "lon": -119.80, "irrigated": True,
     "grown": ["almond_perennial", "grape_perennial", "processing_tomato", "cotton", "alfalfa_hay_perennial",
               "winter_wheat", "corn_maize"],
     "not_viable": ["sugarcane_perennial"]},
    {"name": "Thibodaux, LA (sugarcane belt)", "lat": 29.80, "lon": -90.82,
     "grown": ["sugarcane_perennial", "soybean", "corn_maize", "rice"],
     "not_viable": ["almond_perennial", "sugar_beet", "potato", "barley"]},
    {"name": "Belle Glade, FL (Everglades Agricultural Area)", "lat": 26.68, "lon": -80.67,
     "grown": ["sugarcane_perennial", "rice"],
     "not_viable": ["winter_wheat", "almond_perennial", "sugar_beet", "barley", "potato", "grape_perennial"]},
    {"name": "Lubbock, TX (Southern High Plains)", "lat": 33.58, "lon": -101.85, "irrigated": True,
     "grown": ["cotton", "sorghum", "peanut", "winter_wheat", "corn_maize"],
     "not_viable": ["sugarcane_perennial"]},
    {"name": "Fargo, ND (Red River Valley)", "lat": 46.88, "lon": -96.79,
     "grown": ["soybean", "corn_maize", "sugar_beet", "barley", "potato"],
     "not_viable": ["cotton", "rice", "peanut", "sugarcane_perennial", "almond_perennial"]},
    {"name": "Stuttgart, AR (Grand Prairie)", "lat": 34.50, "lon": -91.55, "irrigated": True,
     "grown": ["rice", "soybean", "corn_maize", "cotton", "winter_wheat"],
     "not_viable": ["sugarcane_perennial", "sugar_beet", "almond_perennial"]},
    {"name": "Tifton, GA (Coastal Plain)", "lat": 31.45, "lon": -83.51,
     "grown": ["peanut", "cotton", "corn_maize", "soybean"],
     "not_viable": ["sugar_beet", "almond_perennial", "barley"]},
    {"name": "Aberdeen, ID (Snake River Plain)", "lat": 42.95, "lon": -112.83, "irrigated": True,
     "grown": ["potato", "barley", "winter_wheat", "alfalfa_hay_perennial", "sugar_beet"],
     "not_viable": ["cotton", "rice", "peanut", "sugarcane_perennial", "sorghum", "almond_perennial"]},
    {"name": "Yakima, WA (Yakima Valley)", "lat": 46.60, "lon": -120.51, "irrigated": True,
     "grown": ["grape_perennial", "alfalfa_hay_perennial", "winter_wheat", "corn_maize"],
     "not_viable": ["cotton", "rice", "peanut", "sugarcane_perennial"]},
]

GROUP_SHORT = {"recommended": "OK  ", "possible": "care", "not_recommended": "NO  "}


def run(irrigated_flag=False):
    start, end = default_dates()
    total_miss = total_false = 0
    for s in SITES:
        df, meta = power.fetch(s["lat"], s["lon"], start, end)
        irr = 100.0 if (irrigated_flag and s.get("irrigated")) else 0.0
        items = screen_crops(df, s["lat"], meta["grid_elevation_m"] or 0.0, "north", irrigation_pct=irr)
        print(f"\n== {s['name']} ({'irrigated' if irr else 'rainfed'}) ==")
        for x in items:
            cid = x["crop_id"]
            flag = ""
            if cid in s["grown"] and x["group"] == "not_recommended":
                flag, total_miss = "  <-- MISS (grown here)", total_miss + 1
            if cid in s["not_viable"] and x["group"] != "not_recommended":
                flag, total_false = "  <-- FALSE (not viable here)", total_false + 1
            bad = [f"{k}:{c['status']}" for k, c in x["checks"].items() if c["status"] in ("limit", "marginal")]
            print(f"  {GROUP_SHORT[x['group']]} {x['crop']:<26} {', '.join(bad)}{flag}")
    print(f"\nMISS = {total_miss}  FALSE = {total_false}")
    return total_miss, total_false


if __name__ == "__main__":
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    run("--irrigated" in sys.argv)
