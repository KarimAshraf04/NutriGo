"""Ranks healthier swaps for an eaten food.

score = w_sim * similarity + w_cal * calorie_saving + w_health * health/100 + goal_bonus

Similarity  = 0.6 * Jaccard(tags) + 0.4 * category match (1 same, 0.5 related)
Rules       = fewer kcal than the eaten portion, health score at least as high,
              sweet stays sweet (and savory stays savory), max 2 swaps per category.
"""
from nutrition import health_score, public, scale

RELATED = {
    "Fast food": {"Sandwich", "Snack", "Meat"},
    "Sandwich": {"Fast food", "Breakfast", "Meat"},
    "Meat": {"Fast food", "Seafood", "Rice & noodles", "Sandwich"},
    "Pasta": {"Rice & noodles"},
    "Rice & noodles": {"Pasta", "Soup", "Meat"},
    "Breakfast": {"Sandwich", "Dessert"},
    "Dessert": {"Breakfast", "Snack"},
    "Soup": {"Rice & noodles", "Appetizer"},
    "Snack": {"Appetizer", "Fast food", "Dessert"},
    "Seafood": {"Meat", "Appetizer", "Salad"},
    "Appetizer": {"Snack", "Seafood", "Salad", "Soup"},
    "Salad": {"Appetizer", "Seafood"},
}

# (similarity, calorie saving, health) weights per goal
GOALS = {
    "balanced":     (0.45, 0.30, 0.25),
    "lose_weight":  (0.30, 0.45, 0.25),
    "high_protein": (0.45, 0.25, 0.30),
    "low_carb":     (0.45, 0.25, 0.30),
    "vegetarian":   (0.45, 0.30, 0.25),
}
MIN_SIMILARITY = 0.22
MAX_PER_CATEGORY = 2
NON_TASTE_TAGS = {"vegetarian", "whole_grain", "side", "fresh"}


def jaccard(a, b):
    a, b = set(a) - NON_TASTE_TAGS, set(b) - NON_TASTE_TAGS
    return len(a & b) / len(a | b) if a | b else 0.0


def category_match(c1, c2):
    if c1 == c2:
        return 1.0
    return 0.5 if c2 in RELATED.get(c1, set()) else 0.0


def similarity(food, alt):
    return 0.6 * jaccard(food["tags"], alt["tags"]) + 0.4 * category_match(food["category"], alt["category"])


def is_sweet(food):
    return "sweet" in food["tags"]


def goal_bonus(alt, goal):
    if goal == "high_protein":
        return 0.15 * min(alt["protein_g"] / 40, 1.0)
    if goal == "low_carb":
        return 0.15 * (1 - min(alt["carbs_g"] / 60, 1.0))
    if goal == "vegetarian":
        return 0.05
    return 0.0


def _chips(eaten, alt):
    """Short 'why' labels like the app cards: -6 g saturated fat, +16 g protein..."""
    chips = []
    dp = alt["protein_g"] - eaten["protein_g"]
    if dp >= 5:
        chips.append(f"+{dp:.0f} g protein")
    dfi = alt["fibre_g"] - eaten["fibre_g"]
    if dfi >= 2:
        chips.append(f"+{dfi:.0f} g fibre")
    ds = eaten["sat_fat_g"] - alt["sat_fat_g"]
    if ds >= 2:
        chips.append(f"-{ds:.0f} g saturated fat")
    dsu = eaten["sugar_g"] - alt["sugar_g"]
    if dsu >= 5:
        chips.append(f"-{dsu:.0f} g sugar")
    dn = eaten["sodium_mg"] - alt["sodium_mg"]
    if dn >= 200:
        chips.append(f"-{dn:.0f} mg sodium")
    shared = sorted((set(eaten["tags"]) & set(alt["tags"])) - NON_TASTE_TAGS)
    if shared:
        chips.append("Similar: " + ", ".join(shared[:3]))
    return chips


def recommend(food, alternatives, portion=1.0, goal="balanced", limit=4):
    """Return (eaten, swaps). `eaten` is the food scaled to the portion."""
    if goal not in GOALS:
        raise ValueError(f"unknown goal '{goal}', use one of {sorted(GOALS)}")
    w_sim, w_cal, w_health = GOALS[goal]
    eaten = scale(food, portion)

    candidates = []
    for alt in alternatives.values():
        if alt["kcal"] >= eaten["kcal"]:
            continue
        if alt["health_score"] < eaten["health_score"]:
            continue
        if is_sweet(alt) != is_sweet(eaten):
            continue
        if goal == "vegetarian" and "vegetarian" not in alt["tags"]:
            continue
        sim = similarity(eaten, alt)
        if sim < MIN_SIMILARITY:
            continue
        saving = (eaten["kcal"] - alt["kcal"]) / eaten["kcal"]
        score = w_sim * sim + w_cal * saving + w_health * alt["health_score"] / 100 + goal_bonus(alt, goal)
        candidates.append((score, sim, alt))

    candidates.sort(key=lambda t: t[0], reverse=True)
    swaps, per_cat = [], {}
    for score, sim, alt in candidates:
        if per_cat.get(alt["category"], 0) >= MAX_PER_CATEGORY:
            continue
        per_cat[alt["category"]] = per_cat.get(alt["category"], 0) + 1
        saved = eaten["kcal"] - alt["kcal"]
        item = public(alt)
        item.update({
            "kcal_saved": round(saved),
            "kcal_saved_pct": round(100 * saved / eaten["kcal"]),
            "similarity": round(sim, 2),
            "rank_score": round(score, 3),
            "why": _chips(eaten, alt),
        })
        swaps.append(item)
        if len(swaps) >= limit:
            break
    return eaten, swaps


# ---------- Kaggle fast-food menu (optional: data/fastfood.csv) ----------

MENU_KEYWORDS = {
    "hamburger": ["burger"], "hot_dog": ["hot dog", "dog"], "pizza": ["pizza", "flatbread"],
    "french_fries": ["fries"], "chicken_wings": ["wing", "nugget", "tender"],
    "nachos": ["nacho"], "tacos": ["taco"], "chicken_quesadilla": ["quesadilla"],
    "onion_rings": ["onion ring"], "club_sandwich": ["sandwich", "sub", "club"],
    "grilled_cheese_sandwich": ["sandwich", "melt"], "pulled_pork_sandwich": ["sandwich", "sub"],
    "breakfast_burrito": ["burrito"], "chicken_curry": ["chicken"],
}
LIGHT_WORDS = ["grilled", "salad", "veggie", "turkey", "wrap", "fresco", "6\""]


def load_fastfood(path):
    """Read Kaggle 'fastfood.csv' (restaurant, item, calories, ... 17 columns)."""
    import csv
    items = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                f = {
                    "restaurant": r["restaurant"], "name": r["item"],
                    "kcal": float(r["calories"]),
                    "protein_g": float(r.get("protein") or 0),
                    "carbs_g": float(r.get("total_carb") or 0),
                    "fat_g": float(r.get("total_fat") or 0),
                    "sat_fat_g": float(r.get("sat_fat") or 0),
                    "fibre_g": float(r.get("fiber") or 0),
                    "sugar_g": float(r.get("sugar") or 0),
                    "sodium_mg": float(r.get("sodium") or 0),
                }
            except (KeyError, ValueError):
                continue
            f["health_score"] = health_score(f)
            items.append(f)
    return items


def menu_swaps(food_id, eaten, menu, limit=3):
    """Lighter real menu items that match the eaten dish, healthiest first."""
    keys = MENU_KEYWORDS.get(food_id)
    if not keys or not menu:
        return []
    out = []
    for it in menu:
        name = it["name"].lower()
        if not any(k in name for k in keys):
            continue
        if it["kcal"] >= eaten["kcal"] or it["health_score"] < eaten["health_score"]:
            continue
        light = any(w in name for w in LIGHT_WORDS)
        out.append((light, it["health_score"], it))
    out.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [dict(it, kcal_saved=round(eaten["kcal"] - it["kcal"])) for _, _, it in out[:limit]]
