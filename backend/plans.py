"""7-day meal plans: breakfast, lunch, dinner and a snack per day, kept on the client's kcal target.

Each meal has a calorie budget = daily kcal target x its share (25 / 35 / 30 / 10 %).
  generate   picks a food for every meal from the 50 healthier swaps (all have real photos; vegetarian
             plans also use the lighter vegetarian dishes, as there are few vegetarian swaps), sized
             with a portion of 0.5x-2.5x so it fits the meal budget, no food twice within 3 days
  replace    a meal changes because the user chose a swap, picked a food, or uploaded a photo
               swap / manual -> portion sized to the meal budget (a swap never above what it replaces)
               photo         -> what the user really ate, kept at the portion they give (default 1x)
  rebalance  after a change, the meals of that day still marked "plan" get new portions so the day
             total stays as close as possible to the target; meals the user chose are never touched
"""
import contextlib
import os
import random
import re
import sqlite3
import time

from nutrition import NUTRIENTS, scale
from recommender import goal_bonus, recommend

DAYS = 7
MEALS = ["breakfast", "lunch", "dinner", "snack"]
MEAL_SHARE = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30, "snack": 0.10}
MEAL_CATEGORIES = {
    "breakfast": {"Breakfast"},
    "lunch": {"Sandwich", "Salad", "Rice & noodles", "Pasta", "Soup", "Fast food", "Seafood"},
    "dinner": {"Meat", "Seafood", "Pasta", "Rice & noodles", "Soup", "Salad"},
    "snack": {"Snack", "Dessert", "Appetizer"},
}
PORTIONS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
MAX_PORTION = PORTIONS[-1]
SOURCES = {"plan", "swap", "manual", "photo"}
KCAL_RANGE = (1200, 3000)  # above 3000 kcal, 4 meals of light swaps cannot get close
VEG_DISH_MIN_HEALTH = 40
USER_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def fit_portion(food, budget, cap_kcal=None):
    """Portion step whose kcal is closest to the budget (optionally never above cap_kcal)."""
    options = [p for p in PORTIONS if cap_kcal is None or food["kcal"] * p <= cap_kcal + 0.5] or [PORTIONS[0]]
    return min(options, key=lambda p: (abs(food["kcal"] * p - budget), p))


def meal_budget(kcal_target, meal):
    return kcal_target * MEAL_SHARE[meal]


def plan_pool(foods, alternatives, goal):
    """Plans use the healthier swaps; other dishes appear when the user swaps or photographs one."""
    pool = list(alternatives.values())
    if goal == "vegetarian":
        pool = [f for f in pool if "vegetarian" in f["tags"]] + [
            f for f in foods.values() if "vegetarian" in f["tags"] and f["category"] != "Fast food"
            and f["health_score"] >= VEG_DISH_MIN_HEALTH]
    return pool


def _score(food, budget, goal):
    p = fit_portion(food, budget)
    closeness = 1 - min(abs(food["kcal"] * p - budget) / budget, 1)
    return 0.5 * closeness + 0.4 * food["health_score"] / 100 + goal_bonus(food, goal)


def generate(foods, alternatives, goal, kcal_target, days=DAYS, rng=None, keep=None):
    """Return [(day, meal, food_id, portion)] for a whole plan.
    `keep` = {(day, meal): food_id} meals the user chose: left out of the result and planned around."""
    rng = rng or random.Random()
    pool = plan_pool(foods, alternatives, goal)
    keep = keep or {}
    last_used, rows = {}, []
    for day in range(1, days + 1):
        today = {f for (d, _), f in keep.items() if d == day}
        for meal in MEALS:
            if (day, meal) in keep:
                last_used[keep[day, meal]] = day
                continue
            budget = meal_budget(kcal_target, meal)
            right_kind = [f for f in pool if f["category"] in MEAL_CATEGORIES[meal]] or pool
            fresh = [f for f in right_kind if f["food_id"] not in today and day - last_used.get(f["food_id"], -9) >= 3]
            cands = fresh or [f for f in right_kind if f["food_id"] not in today] or right_kind
            best = sorted(cands, key=lambda f: _score(f, budget, goal), reverse=True)[:4]
            pick = rng.choice(best)
            today.add(pick["food_id"])
            last_used[pick["food_id"]] = day
            rows.append((day, meal, pick["food_id"], fit_portion(pick, budget)))
    return rows


def rebalance(day_meals, kcal_target, lookup):
    """New portions {meal: portion} for the day's 'plan' meals so the day total meets the target."""
    fixed = sum(lookup(m["food_id"])["kcal"] * m["portion"] for m in day_meals if m["source"] != "plan")
    open_meals = [m for m in day_meals if m["source"] == "plan"]
    if not open_meals:
        return {}
    left = max(kcal_target - fixed, 0)
    shares = sum(MEAL_SHARE[m["meal"]] for m in open_meals)
    return {m["meal"]: fit_portion(lookup(m["food_id"]), left * MEAL_SHARE[m["meal"]] / shares)
            for m in open_meals}


def slot_swaps(food, portion, budget, alternatives, goal, limit=4, exclude=()):
    """Healthier swaps for a planned meal, each sized to the meal budget and never above the planned kcal.
    `exclude` = foods already in that day's other meals, so the day does not get the same food twice."""
    eaten, swaps = recommend(food, alternatives, portion, goal, limit + len(exclude))
    out = []
    for s in [s for s in swaps if s["food_id"] not in exclude][:limit]:
        p = fit_portion(s, budget, cap_kcal=eaten["kcal"])
        sized = scale(s, p)
        s.update({k: sized[k] for k in NUTRIENTS + ["serving_g"]}, portion=p,
                 kcal_saved=round(eaten["kcal"] - sized["kcal"]))
        s["kcal_saved_pct"] = round(100 * s["kcal_saved"] / eaten["kcal"]) if eaten["kcal"] else 0
        out.append(s)
    return eaten, out


def day_view(day, meals, kcal_target, lookup):
    """JSON-ready day: every meal with its food scaled to the portion, its budget, and the day totals."""
    items, totals = [], {k: 0.0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
    for m in sorted(meals, key=lambda m: MEALS.index(m["meal"])):
        food = scale(lookup(m["food_id"]), m["portion"])
        for k in totals:
            totals[k] += food[k]
        items.append({"meal": m["meal"], "source": m["source"], "portion": m["portion"],
                      "budget_kcal": round(meal_budget(kcal_target, m["meal"])), "food": food})
    totals = {k: round(v) for k, v in totals.items()}
    return {"day": day, "meals": items, "totals": totals, "target_kcal": round(kcal_target),
            "diff_kcal": totals["kcal"] - round(kcal_target)}


class PlanStore:
    """Plans in SQLite (same file as the request log). user_id is an anonymous id made by the app."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.execute("""CREATE TABLE IF NOT EXISTS plans (
            user_id TEXT PRIMARY KEY, goal TEXT, kcal_target REAL, created REAL, updated REAL)""")
        self.execute("""CREATE TABLE IF NOT EXISTS plan_meals (
            user_id TEXT, day INTEGER, meal TEXT, food_id TEXT, portion REAL, source TEXT, updated REAL,
            PRIMARY KEY (user_id, day, meal))""")
        self.execute("""CREATE TABLE IF NOT EXISTS plan_changes (
            id INTEGER PRIMARY KEY, ts REAL, user_id TEXT, day INTEGER, meal TEXT,
            old_food_id TEXT, new_food_id TEXT, source TEXT, kcal_before REAL, kcal_after REAL)""")

    def execute(self, sql, args=(), many=False):
        with contextlib.closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.executemany(sql, args) if many else conn.execute(sql, args)
            rows = cur.fetchall()
            conn.commit()
            return rows

    def create(self, user_id, goal, kcal_target, rows):
        now = time.time()
        self.delete(user_id, keep_changes=True)
        self.execute("INSERT INTO plans VALUES (?, ?, ?, ?, ?)", (user_id, goal, kcal_target, now, now))
        self.execute("INSERT INTO plan_meals VALUES (?, ?, ?, ?, ?, 'plan', ?)",
                     [(user_id, d, m, f, p, now) for d, m, f, p in rows], many=True)

    def get(self, user_id):
        meta = self.execute("SELECT * FROM plans WHERE user_id = ?", (user_id,))
        if not meta:
            return None, []
        return dict(meta[0]), [dict(r) for r in self.execute(
            "SELECT * FROM plan_meals WHERE user_id = ? ORDER BY day", (user_id,))]

    def update_meta(self, user_id, **fields):
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE plans SET {sets}, updated = ? WHERE user_id = ?",
                     (*fields.values(), time.time(), user_id))

    def set_meal(self, user_id, day, meal, food_id, portion, source):
        self.execute("UPDATE plan_meals SET food_id = ?, portion = ?, source = ?, updated = ? "
                     "WHERE user_id = ? AND day = ? AND meal = ?",
                     (food_id, portion, source, time.time(), user_id, day, meal))

    def set_portions(self, user_id, day, portions):
        self.execute("UPDATE plan_meals SET portion = ? WHERE user_id = ? AND day = ? AND meal = ?",
                     [(p, user_id, day, m) for m, p in portions.items()], many=True)

    def log_change(self, user_id, day, meal, old_food_id, new_food_id, source, kcal_before, kcal_after):
        self.execute("INSERT INTO plan_changes (ts, user_id, day, meal, old_food_id, new_food_id, source, "
                     "kcal_before, kcal_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (time.time(), user_id, day, meal, old_food_id, new_food_id, source, kcal_before, kcal_after))

    def delete(self, user_id, keep_changes=False):
        self.execute("DELETE FROM plans WHERE user_id = ?", (user_id,))
        self.execute("DELETE FROM plan_meals WHERE user_id = ?", (user_id,))
        if not keep_changes:
            self.execute("DELETE FROM plan_changes WHERE user_id = ?", (user_id,))
