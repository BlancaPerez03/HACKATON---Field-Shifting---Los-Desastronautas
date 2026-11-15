"""Soil 0-30 cm from USDA SSURGO through the Soil Data Access web service (no login, no key).

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Used when Earth Engine (OpenLandMap) is not available. Coverage: the United States (SSURGO soil
survey, mapped at 1:12,000-1:24,000). Service: https://sdmdataaccess.sc.egov.usda.gov (POST SQL).

Method: map units under the parcel centroid and 4 interior points; for each, the major components
weighted by their share (comppct_r); each property depth-weighted over 0-30 cm from the horizon
table (chorizon, representative values *_r). Organic carbon = organic matter / 1.724 (van Bemmelen).
Field capacity = water content at 1/3 bar (wthirdbar_r).
"""
from concurrent.futures import ThreadPoolExecutor

import requests
from shapely.geometry import Point, shape

from ..contract import indicator, r, warn

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
TEXTURE_CODES = {"clay": 1, "silty clay": 2, "sandy clay": 3, "clay loam": 4, "silty clay loam": 5,
                 "sandy clay loam": 6, "loam": 7, "silt loam": 8, "sandy loam": 9, "silt": 10,
                 "loamy sand": 11, "sand": 12}
PROPS = ("ph1to1h2o_r", "claytotal_r", "sandtotal_r", "om_r", "wthirdbar_r")


class SoilUnavailable(RuntimeError):
    code = "OUT_OF_COVERAGE"


class SoilServiceDown(RuntimeError):
    code = "SOURCE_UNAVAILABLE"          # temporary: analyze.py retries it later


def usda_texture(sand, clay):
    """USDA texture class from sand and clay % (NRCS texture-triangle rules)."""
    if sand is None or clay is None:
        return None
    silt = 100 - sand - clay
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52) or (clay < 7 and silt < 50):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    return "clay"


def _query(lon, lat):
    sql = ("SELECT c.cokey, c.comppct_r, h.hzdept_r, h.hzdepb_r, " + ", ".join(f"h.{p}" for p in PROPS) +
           f" FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon:.6f} {lat:.6f})') AS m"
           " JOIN component c ON c.mukey = m.mukey AND c.majcompflag = 'Yes'"
           " JOIN chorizon h ON h.cokey = c.cokey WHERE h.hzdept_r < 30")
    last = None
    for _ in range(2):                       # one retry: the service sometimes stalls
        try:
            resp = requests.post(SDA_URL, json={"query": sql, "format": "JSON+COLUMNNAME"}, timeout=20)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            last = e
    else:
        raise last
    table = (resp.json() or {}).get("Table") or []
    if len(table) < 2:
        return []
    cols = table[0]
    return [dict(zip(cols, row)) for row in table[1:]]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _point_values(rows):
    """Depth-weighted 0-30 cm per component, then weighted by component share."""
    comps = {}
    for row in rows:
        top, bot = _num(row["hzdept_r"]), _num(row["hzdepb_r"])
        if top is None or bot is None:
            continue
        w = max(0.0, min(bot, 30.0) - max(top, 0.0))
        if w <= 0:
            continue
        c = comps.setdefault(row["cokey"], {"pct": _num(row["comppct_r"]) or 0.0, "sum": {}, "w": {}})
        for p in PROPS:
            v = _num(row[p])
            if v is not None:
                c["sum"][p] = c["sum"].get(p, 0.0) + v * w
                c["w"][p] = c["w"].get(p, 0.0) + w
    out = {}
    for p in PROPS:
        num = den = 0.0
        for c in comps.values():
            if c["w"].get(p):
                num += c["pct"] * c["sum"][p] / c["w"][p]
                den += c["pct"]
        out[p] = num / den if den else None
    return out


def sample_points(geojson, n=4):
    """Centroid plus up to n points spread inside the parcel (no projection needed at field scale)."""
    g = shape(geojson)
    pts = [g.representative_point() if not g.contains(g.centroid) else g.centroid]
    minx, miny, maxx, maxy = g.bounds
    for fx, fy in ((0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7))[:n]:
        p = Point(minx + fx * (maxx - minx), miny + fy * (maxy - miny))
        if g.contains(p):
            pts.append(p)
    return [(p.x, p.y) for p in pts]


def run(parcel, start=None, end=None):
    pts = sample_points(parcel.geojson)

    def one(xy):
        try:
            return _point_values(_query(*xy))
        except requests.RequestException:
            return None                      # one slow point must not lose the others

    with ThreadPoolExecutor(max_workers=len(pts)) as pool:
        results = list(pool.map(one, pts))
    failed = sum(x is None for x in results)
    results = [x for x in results if x and any(v is not None for v in x.values())]
    if not results:
        if failed:
            raise SoilServiceDown("USDA Soil Data Access did not answer in time; it is retried automatically later.")
        raise SoilUnavailable("No USDA SSURGO soil data at this location (US soil survey only).")
    mean = {p: (sum(x[p] for x in results if x[p] is not None) / n) if (n := sum(x[p] is not None for x in results)) else None
            for p in PROPS}
    clay, sand = mean["claytotal_r"], mean["sandtotal_r"]
    tex = usda_texture(sand, clay)
    return indicator(
        ids=["USDA NRCS SSURGO via Soil Data Access (sdmdataaccess.sc.egov.usda.gov)"],
        provider="USDA Natural Resources Conservation Service", nasa=False, citation_key="usda_ssurgo",
        data_type="soil_survey", resolution_m=30, scale_note="parcel", unit="see each field",
        method=(f"Map units under {len(results)} point(s) of the parcel; major components weighted by their share; "
                "representative horizon values depth-weighted over 0-30 cm. Organic carbon = organic matter / 1.724. "
                "Texture class from sand and clay (USDA triangle)."),
        confidence="medium",
        confidence_reason="Field soil survey (SSURGO) at 1:12,000-1:24,000, representative values of the mapped soil "
                          "series; not a lab analysis of this field.",
        warnings=[warn("SOURCE_DEPRECATED_FALLBACK", "Earth Engine is not configured: soil comes from USDA SSURGO "
                       "(no login) instead of OpenLandMap. Farmer-provided soil tests take priority.")],
        licence="Public domain (USDA)", via="web_service",
        sampled_at=f"{len(results)} points",
        ph_h2o=r(mean["ph1to1h2o_r"], 2),
        organic_carbon_g_kg=r(mean["om_r"] / 1.724 * 10, 1) if mean["om_r"] is not None else None,
        clay_pct=r(clay, 1), sand_pct=r(sand, 1),
        silt_pct=r(100 - clay - sand, 1) if clay is not None and sand is not None else None,
        field_capacity_33kpa_pct_vol=r(mean["wthirdbar_r"], 1),
        texture_class={"code": TEXTURE_CODES.get(tex), "name": tex},
    )
