"""Loads the nutrition tables and computes the health score."""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("NUTRIGO_DATA_DIR", os.path.join(ROOT, "data"))

NUMERIC = ["serving_g", "kcal", "protein_g", "carbs_g", "fat_g", "sat_fat_g",
           "fibre_g", "sugar_g", "sodium_mg"]
NUTRIENTS = NUMERIC[1:]  # everything that scales with portion


def health_score(f):
    """Health score 0-100 (higher is healthier).

    60 - (kcal/40 + sat_fat + 0.4*sugar + sodium/150) + (0.5*protein + 1.5*fibre)
    """
    penalty = f["kcal"] / 40 + f["sat_fat_g"] + 0.4 * f["sugar_g"] + f["sodium_mg"] / 150
    bonus = 0.5 * f["protein_g"] + 1.5 * f["fibre_g"]
    return int(round(max(0.0, min(100.0, 60 - penalty + bonus))))


def scale(food, portion):
    """Return a copy of a food with nutrients multiplied by the portion (0.5x-2x)."""
    out = dict(food)
    for k in NUTRIENTS + ["serving_g"]:
        out[k] = round(food[k] * portion, 1)
    out["portion"] = portion
    out["health_score"] = health_score(out)
    return out


def load_table(path):
    foods = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for k in NUMERIC:
                row[k] = float(row[k])
            row["tags"] = [t for t in row["tags"].split(",") if t]
            row["health_score"] = health_score(row)
            foods[row["food_id"]] = row
    return foods


def load_foods(data_dir=DATA_DIR):
    return load_table(os.path.join(data_dir, "food101_nutrition.csv"))


def load_alternatives(data_dir=DATA_DIR):
    return load_table(os.path.join(data_dir, "healthy_alternatives.csv"))


def public(food):
    """JSON-friendly view of a food row."""
    keys = ["food_id", "name", "category", "serving", "serving_g", "health_score",
            "tags"] + NUTRIENTS
    out = {k: food[k] for k in keys if k in food}
    if "portion" in food:
        out["portion"] = food["portion"]
    return out
