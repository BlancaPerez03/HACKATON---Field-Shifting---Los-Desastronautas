"""Genera mock/climate.mock.json con DATOS FICTICIOS para que el equipo trabaje sin esperar.

Uso: python make_mock.py
El archivo lleva "isMock": true; la interfaz debe mostrar un aviso si lo detecta.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tests"))
from test_climate import _synthetic  # noqa: E402

import build_climate  # noqa: E402
import power  # noqa: E402


def fake_fetch(lat, lon, start, end, cache_dir, refresh):
    return _synthetic((start, end)), {"downloadedAt": None, "fromCache": False,
                                      "elevation_m": 90.0, "cacheFile": None}


build_climate.fetch_power = fake_fetch
res = build_climate.build(forecast=False)
res["isMock"] = True
res["source"] = "MOCK - datos ficticios generados por make_mock.py. NO USAR EN LA DEMO."
out = Path("mock/climate.mock.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
print(f"Mock -> {out}")
