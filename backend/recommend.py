"""Which crop suits this field, and when to sow it: transparent rule-based recommendation.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.
Pure functions. No hidden score: every crop gets the same visible checks (climate from the
simulator's crop checks, soil pH, rotation with last year's crop) and lands in one of three groups:
  recommended  - no check tight or limiting
  possible     - at least one check tight, none limiting
  not_recommended - at least one check limiting
Inside a group crops are ordered by fewest tight checks, then rotation benefit (legume after an
N-removing crop, or an N-demanding crop after a legume), then years grown on this field (USDA CDL:
machinery and buyers likely in place), then water cover.
It supports the farmer's decision; it does not replace local agronomic advice.
"""
from datetime import date, timedelta
import calendar

CLIMATE_CHECKS = ("gdd", "water", "heat", "cool_season", "frost_free", "safe_sowing", "winter_cold",
                  "vernalization", "humid_summer", "bloom_frost")
LABELS = {"gdd": "heat to mature", "water": "water", "heat": "heat at flowering", "cool_season": "summer heat",
          "frost_free": "frost-free season", "safe_sowing": "frost at sowing", "winter_cold": "winter cold",
          "vernalization": "winter chilling", "humid_summer": "humid climate", "bloom_frost": "frost at bloom",
          "ph": "soil pH", "texture": "soil texture", "rotation": "rotation"}
GROUP_ORDER = {"recommended": 0, "possible": 1, "not_recommended": 2}
RULES = {
    "groups": "recommended = no check tight or limiting; possible = some tight, none limiting; "
              "not_recommended = at least one limiting (team rules, visible per crop).",
    "order": "Inside a group: fewest tight checks, then rotation benefit, then years grown on this field "
             "(USDA CDL), then share of the crop's water need covered by rain.",
    "ph": "ok inside the catalogue's optimum pH range, tight within 0.5 of it, limit beyond (0-30 cm soil estimate).",
    "texture": "rice needs a soil that holds a flood (sand / loamy sand = limit); peanut needs light soil to dig pods "
               "(clay, silty clay, sandy clay = limit). Other crops: no texture rule.",
    "rotation": "tight if it repeats last year's crop (pest and disease build-up) or is a perennial tree, vine or "
                "cane crop (multi-year land-use change; alfalfa counts as a rotation crop); ok otherwise; a legume "
                "(positive N balance) after a crop that removes nitrogen is marked as a rotation benefit.",
    "frost_at_sowing": "Frost ending inside the sowing window only moves the sowing date; it counts against a "
                       "crop only when frost lasts beyond the whole window.",
    "sowing": "Sow from the later of: the opening of the catalogue sowing window, or the date after which spring "
              "frost is over 9 years in 10 (scenario); until the window closes. Winter and perennial crops use "
              "the catalogue window.",
}


# Status words used everywhere: "ok", "marginal" (shown as "Tight" on the page), "limit", "n/a".


def ph_check(crop, ph):
    """Compare the field's soil pH with the crop's optimum range from the catalogue."""
    rng = crop.get("ph_optimum")
    if ph is None or not rng:
        return {"status": "n/a", "detail": "No soil pH estimate."}
    lo, hi = rng
    if lo <= ph <= hi:
        st = "ok"
    elif min(abs(ph - lo), abs(ph - hi)) <= 0.5:
        st = "marginal"
    else:
        st = "limit"
    side = "acid" if ph < lo else "alkaline"
    fix = "adding lime raises it" if ph < lo else "sulphur or acidifying fertilisers lower it slowly"
    plain = {"ok": "The soil acidity suits it.",
             "marginal": f"The soil is slightly too {side} for it ({fix}).",
             "limit": f"The soil is too {side} for it ({fix}, but it takes years)."}[st]
    return {"status": st, "detail": f"Soil pH {ph:.1f} vs optimum {lo:g}-{hi:g}", "plain": plain}


def texture_check(crop, soil):
    """Soil texture rules for the crops where texture decides feasibility (crop_params.json `texture`)."""
    rule = crop.get("texture")
    name = ((soil or {}).get("texture_class") or {}).get("name")
    if not rule:
        return None
    if not name:
        return {"status": "n/a", "detail": "No soil texture estimate."}
    st = "limit" if name in rule["limit"] else "marginal" if name in rule.get("marginal", []) else "ok"
    plain = {"ok": f"The soil type ({name}) suits it.",
             "marginal": f"The soil type ({name}) is not ideal for it. {rule['note']}",
             "limit": f"The soil type ({name}) does not suit it. {rule['note']}"}[st]
    return {"status": st, "detail": f"Soil texture {name}. {rule['note']}", "plain": plain}


ROTATION_PERENNIALS = {"alfalfa_hay_perennial"}     # perennial forage commonly used inside rotations


def rotation_check(crop, prev_crop):
    """Rotation rules with last year's crop. The nitrogen balance column of the catalogue tells us
    which crops add nitrogen (legumes, positive) and which remove it (negative)."""
    if crop.get("perennial") and crop["id"] not in ROTATION_PERENNIALS:
        return {"status": "marginal", "benefit": False,
                "detail": "Perennial tree/vine/cane crop: a multi-year change of land use, not a rotation crop.",
                "plain": "It stays in the field for many years (trees, vines or cane): a big, long-term change, "
                         "not a crop to rotate."}
    if prev_crop is None:
        return {"status": "n/a", "benefit": False, "detail": "Last year's crop unknown.",
                "plain": "We do not know last year's crop on this field."}
    prev = prev_crop["name_en"].lower()
    if prev_crop["id"] == crop["id"]:
        return {"status": "marginal", "benefit": False,
                "detail": f"Repeats last year's crop ({prev_crop['name_en']}): pests and diseases build up.",
                "plain": f"It repeats last year's crop ({prev}): the pests and diseases of that crop stay in the "
                         "field and grow from year to year."}
    nb, pnb = crop.get("n_balance_kg_ha"), prev_crop.get("n_balance_kg_ha")
    if nb is not None and pnb is not None and nb > 0 and pnb < 0:
        return {"status": "ok", "benefit": True,
                "detail": f"Legume after {prev_crop['name_en']}: needs no N fertiliser, leaves an N credit of about "
                          f"{nb:.0f} kg N/ha for the next crop and breaks the pest cycle.",
                "plain": f"Good rotation: after {prev}, which used up nitrogen, this legume makes its own nitrogen "
                         f"from the air, needs no nitrogen fertiliser and leaves about {nb:.0f} kg N/ha for next year."}
    if nb is not None and pnb is not None and nb < 0 < pnb:
        return {"status": "ok", "benefit": True,
                "detail": f"After a legume ({prev_crop['name_en']}): can count an N credit of about {pnb:.0f} kg N/ha "
                          "(less N fertiliser) and breaks the pest cycle.",
                "plain": f"Good rotation: last year's {prev} left about {pnb:.0f} kg N/ha in the soil, so this crop "
                         "needs that much less nitrogen fertiliser."}
    return {"status": "ok", "benefit": False,
            "detail": f"Different crop from last year ({prev_crop['name_en']}): breaks the pest cycle.",
            "plain": f"It is a different crop from last year's {prev}, which breaks the cycle of pests and diseases."}


# ---------------------------------------------------------------------------------------------
# Rotation plan: alternate crops that ADD nitrogen (legumes, positive N balance in the catalogue)
# with crops that USE it (negative balance), choosing among the crops that pass the checks here.
def _role(crop):
    nb = crop.get("n_balance_kg_ha")
    return None if nb is None else "adds" if nb > 0 else "uses" if nb < 0 else None


def rotation_plan(items, catalog, prev_crop=None, prev_year=None, years=4, start_year=None):
    """Next `years` seasons alternating nitrogen-adding and nitrogen-using crops.

    items: ranked evaluations (best first). Only crops that are not 'not_recommended' and are rotation
    crops (no trees, vines or cane) are used. Alfalfa is offered as a multi-year alternative, not a
    single year. The N credit of a legume is the catalogue value (extension N credits for the next crop).
    """
    def ok(x):
        c = catalog[x["crop_id"]]
        return x.get("group_without_rotation", x["group"]) != "not_recommended" and not c.get("perennial")
    # Order for planning: climate/soil fit first, then crops already grown on the field (machinery and
    # buyers in place), then water cover. Last year's crop is handled by the alternation itself.
    items = sorted(items, key=lambda x: (GROUP_ORDER[x.get("group_without_rotation", x["group"])],
                                         x.get("n_tight_without_rotation", 9), -(x.get("grown_here_years") or 0),
                                         -(x.get("water_cover_pct") or 0), x["crop"]))
    usable = [x for x in items if ok(x)]
    adders = [x for x in usable if _role(catalog[x["crop_id"]]) == "adds"]
    users = [x for x in usable if _role(catalog[x["crop_id"]]) == "uses"]
    alfalfa = next((x for x in items if x["crop_id"] in ROTATION_PERENNIALS and x["group"] != "not_recommended"), None)
    users, adders = users[:2], adders[:2]          # the two best of each kind, alternated for variety
    # (the loop below never repeats last year's crop in year 1; it is kept for the following cycles)
    if not usable:
        return {"years": [], "summary": "No annual crop passes the checks in this scenario, so no rotation can be "
                                         "suggested.", "alfalfa_option": None}
    prev_role = _role(prev_crop) if prev_crop else None
    want = "uses" if prev_role == "adds" else "adds"
    if not adders:
        want = "uses"
    if not users:
        want = "adds"
    plan, last, counters = [], prev_crop, {"adds": 0, "uses": 0}
    y0 = start_year or ((prev_year + 1) if prev_year else None)
    saved = 0.0
    for i in range(years):
        pool = adders if want == "adds" else users
        if not pool:
            pool, want = (users, "uses") if want == "adds" else (adders, "adds")
        x = pool[counters[want] % len(pool)]
        if last is not None and x["crop_id"] == last["id"] and len(pool) > 1:
            counters[want] += 1
            x = pool[counters[want] % len(pool)]
        counters[want] += 1
        c = catalog[x["crop_id"]]
        nb = c.get("n_balance_kg_ha") or 0
        lname = last["name_en"].lower() if last else None
        last_nb = (last or {}).get("n_balance_kg_ha") or 0
        if want == "adds":
            why = (f"{c['name_en']} is a legume: bacteria in its roots take nitrogen from the air, so it needs no "
                   f"nitrogen fertiliser and leaves about {nb:.0f} kg of nitrogen per hectare for next year's crop.")
        elif last_nb > 0:
            why = (f"{c['name_en']} needs a lot of nitrogen (it takes about {abs(nb):.0f} kg/ha from the soil). After "
                   f"{lname} it finds about {last_nb:.0f} kg/ha already in the soil, so you can buy that much less "
                   "nitrogen fertiliser.")
            saved += last_nb
        else:
            why = (f"{c['name_en']} needs a lot of nitrogen (about {abs(nb):.0f} kg/ha); with no legume before it, "
                   "it needs its full nitrogen fertiliser.")
        plan.append({"year": (y0 + i) if y0 else None, "step": i + 1, "crop_id": x["crop_id"], "crop": x["crop"],
                     "group": x.get("group_without_rotation", x["group"]), "role": want, "n_balance_kg_ha": nb, "why": why})
        last = c
        want = "uses" if want == "adds" else "adds"
        if want == "adds" and not adders:
            want = "uses"
        if want == "uses" and not users:
            want = "adds"
    if adders and users:
        summary = (f"Alternate a crop that adds nitrogen ({', '.join(x['crop'] for x in adders)}) with one that uses "
                   f"it ({', '.join(x['crop'] for x in users)}). Each legume year feeds the next crop, saving about "
                   f"{saved:.0f} kg of nitrogen fertiliser per hectare over these {years} years, and changing crop every "
                   "year breaks the cycle of pests and diseases.")
    elif users:
        summary = ("No legume passes the checks here, so the plan only alternates different crops. A winter cover crop "
                   "of a legume (such as clover or vetch) between them would still add some nitrogen.")
    else:
        summary = ("Only legumes pass the checks here: alternate different legumes to break pest cycles; "
                   "nitrogen fertiliser is not needed.")
    alt = None
    if alfalfa:
        alt = (f"Alfalfa can replace the legume years: it stays 3-4 years, makes hay every summer and leaves the most "
               f"nitrogen (about {catalog[alfalfa['crop_id']].get('n_balance_kg_ha') or 0:.0f} kg/ha) for the crop "
               "that follows it.")
    start_note = (f"Starts from the last crop we know on this field ({prev_crop['name_en']}, {prev_year}, USDA CDL). "
                  "If you grew something else since, start the plan at the year that follows the same kind of crop."
                  if prev_crop else "Last year's crop is unknown: the plan starts with a legume.")
    return {"years": plan, "summary": summary, "alfalfa_option": alt, "start_note": start_note,
            "n_saved_kg_ha": round(saved), "rule": "Alternate crops with a positive N balance (legumes) and a negative "
            "one, among the crops that pass the checks; the two best of each kind are alternated for variety."}


def _date(year, mmdd):
    m, d = (int(x) for x in mmdd.split("-"))
    return date(year, m, d)


def sowing_dates(crop, safe_from_mmdd, year=2001):
    """Recommended sowing window as MM-DD strings (non-leap reference year)."""
    s, e = crop["sowing_start_month"], crop["sowing_end_month"]
    w_start = date(year, s, 1)
    # calendar.monthrange(year, month)[1] = number of days in that month (last day of the window).
    w_end = date(year, e, calendar.monthrange(year, e)[1])
    wraps = e < s
    if crop.get("min_frost_free_days") is None or wraps:
        return {"from": w_start.strftime("%m-%d"), "to": w_end.strftime("%m-%d"),
                "basis": "catalogue sowing window (winter or perennial crop)"}
    start, basis = w_start, "opening of the sowing window"
    if safe_from_mmdd:
        safe = _date(year, safe_from_mmdd) + timedelta(days=1)
        if safe > start:
            start, basis = safe, "day after the 1-in-10-year last spring frost"
    if start > w_end:
        return {"from": None, "to": None, "basis": "frost risk lasts beyond the whole sowing window"}
    return {"from": start.strftime("%m-%d"), "to": w_end.strftime("%m-%d"), "basis": basis}


def evaluate(crop, effect, ph, prev_crop, grown_years=0, n_years=0, soil=None):
    """One crop -> group, reasons, sowing dates. grown_years: seasons it was the dominant CDL crop here."""
    if effect is None:
        return {"crop_id": crop["id"], "crop": crop["name_en"], "group": "not_recommended",
                "checks": {}, "reasons": ["Not enough climate data for its season."], "sowing": None}
    sc = effect["scenario"]
    rows = {x["key"]: x for x in effect.get("rows", [])}
    checks = {k: {"status": sc[k]["status"],
                  **({"detail": rows[k]["detail"], "plain": rows[k].get("plain", "")} if k in rows else {})}
              for k in CLIMATE_CHECKS if k in sc}
    # Frost ending inside the sowing window only sets the sowing date (handled by sowing_dates);
    # it is a problem only when frost lasts beyond the whole window.
    if checks.get("safe_sowing", {}).get("status") == "marginal":
        checks["safe_sowing"] = {"status": "ok", "detail": "Sow after the frost-safe date shown.",
                                 "plain": checks["safe_sowing"].get("plain", "Sow after the frost-safe date shown.")}
    checks["ph"] = ph_check(crop, ph)
    tx = texture_check(crop, soil)
    if tx:
        checks["texture"] = tx
    rot = rotation_check(crop, prev_crop)
    checks["rotation"] = rot
    # The group is decided by the worst check: any "limit" -> not recommended; else any "marginal"
    # -> possible with care; else recommended.
    statuses = [c["status"] for c in checks.values()]
    group = ("not_recommended" if "limit" in statuses
             else "possible" if "marginal" in statuses else "recommended")
    # Two versions of every reason: `reasons` in everyday words, `reasons_numbers` with the figures.
    reasons, numbers = [], []
    for k, c in checks.items():
        if c["status"] in ("limit", "marginal"):
            word = "limiting" if c["status"] == "limit" else "tight"
            reasons.append(c.get("plain") or f"{LABELS[k].capitalize()} is {word}.")
            numbers.append(f"{LABELS[k].capitalize()} ({word})" + (f": {c['detail']}" if c.get("detail") else ""))
    if rot.get("benefit"):
        reasons.append(rot["plain"])
        numbers.append(f"Rotation: {rot['detail']}")
    if grown_years:
        reasons.append(f"It was grown on this field in {grown_years} of the last {n_years} years, so the machinery "
                       "and buyers are probably already there.")
        numbers.append(f"Dominant crop in {grown_years} of {n_years} years (USDA CDL).")
    if group == "recommended" and not rot.get("benefit"):
        reasons.insert(0, "Everything we can check fits: climate, water, soil and rotation.")
    verdict = {"recommended": f"{crop['name_en']} suits this field well.",
               "possible": f"{crop['name_en']} can grow here, but watch the points below.",
               "not_recommended": f"{crop['name_en']} is not a good choice for this field."}[group]
    w = sc["water"]
    return {
        "crop_id": crop["id"], "crop": crop["name_en"], "group": group, "checks": checks, "reasons": reasons,
        "reasons_numbers": numbers, "verdict": verdict, "n_role": _role(crop),
        # Group without the rotation check (used to plan later years, where last year's crop no longer applies).
        "group_without_rotation": ("not_recommended" if any(c["status"] == "limit" for k, c in checks.items() if k != "rotation")
                                   else "possible" if any(c["status"] == "marginal" for k, c in checks.items()
                                                          if k != "rotation") else "recommended"),
        "n_tight_without_rotation": sum(c["status"] == "marginal" for k, c in checks.items() if k != "rotation"),
        "n_tight": statuses.count("marginal"), "rotation_benefit": bool(rot.get("benefit")),
        "grown_here_years": grown_years,
        "water_cover_pct": w.get("cover_pct"),
        "sowing": sowing_dates(crop, sc["safe_sowing"].get("safe_from")),
        "harvest_months": [crop["harvest_start_month"], crop["harvest_end_month"]],
        "nitrogen_balance_kg_ha": crop.get("n_balance_kg_ha"),
    }


def rank(items):
    # Python sorts tuples element by element, so this sorts by group first, then by the number of
    # tight checks, then the other tie-breakers. Negative numbers sort "more is better" first.
    return sorted(items, key=lambda x: (GROUP_ORDER[x["group"]], x.get("n_tight", 9),
                                        0 if x.get("rotation_benefit") else 1,
                                        -(x.get("grown_here_years") or 0),
                                        -(x.get("water_cover_pct") or 0), x["crop"]))
