"""Smoke run of the simulator on the demo parcels + HTTP timing of 20 consecutive control moves.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Usage: python -m scripts.simulate_smoke            (direct, no server needed)
       python -m scripts.simulate_smoke --http     (also times POST /api/parcel/simulate on :8000)
"""
import argparse
import json
import time

import requests

from backend import config
from backend.simulate import clear_simulation_cache, simulate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and adds ~2 s per request
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    idx = json.loads((config.DEMO_DIR / "index.json").read_text())
    clear_simulation_cache()
    for d in idx:
        out = simulate(d["cache_key"], -20, 2.0, True, 60)
        print(f"=== {d['id']}  mode={out['mode']}  server={out['timing_ms']['server']} ms")
        for x in out["deltas"]:
            print(f"  {x['indicator']:<28}{x['baseline']!s:>9} -> {x['scenario']!s:<9} {x['change']:+9.2f} {x['unit']:<12} {x['direction']}")
        z = out["risk_zones"]
        if z:
            print(f"  risk zones {z['rows']}x{z['cols']}: erosion base {z['erosion']['summary']['base']} -> "
                  f"scenario {z['erosion']['summary']['scenario']}; cold-air hollows {z['cold_air']['hollow_fraction']}")
        print("  " + "\n  ".join(out["explanation"]))
    if a.http:
        # Performance test: 20 different slider combinations sent to the running server, timing the
        # full HTTP round trip. Random values avoid hitting the server's memo cache.
        import random
        rnd = random.Random()
        k = idx[0]["cache_key"]
        times = []
        for i in range(20):      # random, mostly unseen combinations (the server memoizes repeats)
            body = {"geometry_hash": k, "delta_precip_pct": -rnd.randint(0, 30), "delta_temp_c": rnd.randint(0, 30) / 10,
                    "irrigation_enabled": rnd.random() < 0.5, "irrigation_availability_pct": 5 * rnd.randint(0, 20)}
            t = time.perf_counter()
            r = requests.post(f"{a.url}/api/parcel/simulate", json=body, timeout=30)
            r.raise_for_status()
            times.append((time.perf_counter() - t) * 1000)
        s = sorted(times)
        print(f"\nHTTP round trip, 20 moves (3 controls each): p50 {s[9]:.0f} ms, p95 {s[18]:.0f} ms, max {s[-1]:.0f} ms")


if __name__ == "__main__":
    main()
