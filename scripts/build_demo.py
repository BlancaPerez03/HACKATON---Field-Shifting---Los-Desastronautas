"""Precompute the demo parcels into backend/demo_cache/ so the demo works offline and without quota.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Writes, per parcel: <cache_key>.json (analyze response), baseline/<key>.json (simulator bundle),
power/<cell file>.json (NASA POWER daily series) and terrain/<key>.json (30 m terrain grid).
Usage:  python -m scripts.build_demo                  # refuses if any source is missing
        python -m scripts.build_demo --allow-partial  # write anyway (rebuild once GEE works!)
"""
import argparse
import json
import shutil
import sys

from backend import config
from backend.analyze import build, check_dates, default_dates, save_baseline
from backend.geometry import cache_key, prepare
from backend.simulate import simulate
from backend.sources import terrain_grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-partial", action="store_true")
    a = ap.parse_args()
    parcels = json.loads((config.ROOT / "scripts" / "demo_parcels.json").read_text())["parcels"]
    start, end = default_dates()
    check_dates(start, end)
    for sub in ("", "baseline", "power", "terrain"):
        (config.DEMO_DIR / sub).mkdir(parents=True, exist_ok=True)
    index, failed = [], False
    for p in parcels:
        parcel = prepare(p["geometry"])
        key = cache_key(parcel, start, end)      # same key the API will compute for this geometry
        out = build(parcel, start, end)          # live computation (NASA + Earth Engine), no cache
        missing = [g for g in out["data_gaps"] if g["code"] in ("GEE_UNAVAILABLE", "MODULE_ERROR", "MODULE_TIMEOUT")]
        if missing and not a.allow_partial:
            print(f"SKIP {p['id']}: missing {[g['indicator'] for g in missing]}")
            failed = True
            continue
        out["request"]["demo_id"] = p["id"]
        bundle = save_baseline(key, parcel, start, end, out)
        (config.DEMO_DIR / f"{key}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        (config.DEMO_DIR / "baseline" / f"{key}.json").write_text(json.dumps(bundle), encoding="utf-8")
        if bundle["power_file"]:
            shutil.copy(config.CACHE_DIR / "power" / bundle["power_file"], config.DEMO_DIR / "power" / bundle["power_file"])
        grid_ok = False
        try:
            grid = terrain_grid.fetch(parcel)
            (config.DEMO_DIR / "terrain" / f"{key}.json").write_text(json.dumps(grid), encoding="utf-8")
            grid_ok = True
        except Exception as e:
            print(f"  terrain grid failed for {p['id']}: {e}")
        index.append({"id": p["id"], "name": p["name"], "cache_key": key, "start_date": start,
                      "end_date": end, "partial": bool(missing), "terrain_grid": grid_ok})
        # Sanity check: the simulator must be able to run from these files alone.
        sim = simulate(key)   # sanity: the simulator can run from the demo cache
        print(f"OK {p['id']} -> {key[:12]}  partial={bool(missing)} grid={grid_ok} "
              f"sim_mode={sim['mode']} zones={'yes' if sim['risk_zones'] else 'no'}")
    (config.DEMO_DIR / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
