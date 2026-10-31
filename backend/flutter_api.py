"""The REST API the Flutter app calls (contract: for_mobile_app/NutriGo_API_for_Flutter.md).

  GET  /api/status                              -> server, model and catalog status
  POST /api/predict    multipart 'image' [+ 'goal'] -> top-5 dishes, the top guess and its swaps
  POST /api/recommend  {food_id, portion, goal} -> eaten nutrition + ranked healthier swaps
  GET  /api/foods      ?q=&category=           -> the 101 foods (manual picker)
  GET  /api/foods/<id>                          -> one food
  POST /api/target     {sex, age, weight_kg, height_cm, activity, goal} -> daily targets
  GET  /api/images/<food_id>                    -> photo of a dish or swap (JPEG, or a PNG card)

  7-day meal plan (breakfast, lunch, dinner, snack), kept on the client's daily kcal target:
  POST   /api/plans                    {user_id, goal, kcal_target}  -> new plan
  GET    /api/plans/<user_id>                                         -> the plan
  PATCH  /api/plans/<user_id>          {kcal_target?, goal?}          -> re-fit every day to the new target
  DELETE /api/plans/<user_id>
  GET    /api/plans/<user_id>/<day>/<meal>/swaps                      -> healthier swaps sized to that meal
  PUT    /api/plans/<user_id>/<day>/<meal>   {food_id, source, portion?} -> replace the meal (swap / manual)
  POST   /api/plans/<user_id>/<day>/<meal>/photo  multipart 'image'  -> recognise what was eaten, put it in

  Accounts (email + password; send "Authorization: Bearer <token>" afterwards):
  POST   /api/auth/register   {name, email, password, sex?, age?, height_cm?, weight_kg?, activity?, goal?}
  POST   /api/auth/login      {email, password}             -> {token, user}
  POST   /api/auth/logout
  GET    /api/me   PATCH /api/me {profile fields}   DELETE /api/me (account + plan + photos)
  POST   /api/me/password {current_password, new_password} -> new token (other devices logged out)
  PUT    /api/me/avatar  multipart 'image'     GET /api/me/avatar
  GET    /api/me/photos  -> meal-photo gallery; GET / DELETE /api/me/photos/<id>
  Signed-in users' meal photos (/api/predict, plan photo) are kept in their gallery; their plan is
  /api/plans/me (or their user id) and only they can open it.

Every food object has "image_url" and "has_photo". Every call except image downloads is written
to the request log that the admin dashboard reads (no passwords, photos or profile data).
"""
import io
import os
import time

from flask import Blueprint, current_app, g, jsonify, request, send_file, url_for

import plans
import users
from images import placeholder_png
from nutrition import public
from recommender import GOALS, menu_swaps, recommend

LOW_CONFIDENCE = 0.60
MAX_LIMIT = 10
PREDICT_SWAPS = 4
NOT_LOGGED = {"food_image", "my_avatar", "my_photo"}
MIN_FAT_SHARE = 0.20
ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}

bp = Blueprint("flutter_api", __name__, url_prefix="/api")


def state():
    return current_app.extensions["nutrigo"]


def error(msg, code=400):
    return jsonify({"error": msg}), code


def read_photo():
    """(bytes, None) for a readable 'image' upload, else (None, error response)."""
    file = request.files.get("image")
    if file is None:
        return None, error("send the photo as multipart form field 'image'")
    data = file.read()
    try:
        from PIL import Image
        Image.open(io.BytesIO(data)).verify()
    except Exception as e:
        return None, error(f"could not read image: {e}")
    return data, None


def image_url(food_id, external=True):
    v = state().images.version(food_id)
    return url_for("flutter_api.food_image", food_id=food_id, v=v, _external=external)


def with_image(item):
    """Add image_url / has_photo to a food, swap or prediction dict (returns it)."""
    item["image_url"] = image_url(item["food_id"])
    item["has_photo"] = state().images.find(item["food_id"]) is not None
    return item


@bp.before_request
def start_timer():
    g.t0 = time.perf_counter()
    g.log = {}


@bp.after_request
def log_request(resp):
    if request.endpoint and request.endpoint.split(".")[-1] in NOT_LOGGED:
        return resp
    try:
        state().log.add(request.endpoint.split(".")[-1], resp.status_code,
                        round(1000 * (time.perf_counter() - g.t0), 1), **g.log)
    except Exception as e:  # logging must never break the app
        current_app.logger.warning("request log failed: %s", e)
    return resp


@bp.get("/status")
def status():
    st = state()
    return jsonify({
        "app": "NutriGo API", "model": st.model.name, "model_ready": st.model.available(),
        "model_classes": list(st.model.labels),
        "foods": len(st.store.foods), "alternatives": len(st.store.alternatives),
        "fastfood_items": len(st.store.menu), "goals": sorted(GOALS),
    })


@bp.get("/images/<food_id>")
def food_image(food_id):
    st = state()
    food = st.store.foods.get(food_id) or st.store.alternatives.get(food_id)
    if food is None:
        return error(f"unknown food_id '{food_id}'", 404)
    path = st.images.find(food_id)
    if path:
        # read into memory: an open file handle would stop admins replacing the photo on Windows
        with open(path, "rb") as fh:
            return send_file(io.BytesIO(fh.read()), mimetype="image/jpeg", max_age=86400)
    return send_file(io.BytesIO(placeholder_png(food["name"], food["category"])),
                     mimetype="image/png", max_age=3600)


@bp.get("/foods")
def list_foods():
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("category", "").strip().lower()
    out = [with_image(public(f)) for f in state().store.foods.values()
           if (not q or q in f["name"].lower() or q in f["food_id"])
           and (not cat or f["category"].lower() == cat)]
    out.sort(key=lambda f: f["name"])
    return jsonify({"count": len(out), "foods": out})


@bp.get("/foods/<food_id>")
def get_food(food_id):
    g.log["food_id"] = food_id
    f = state().store.foods.get(food_id)
    return jsonify(with_image(public(f))) if f else error(f"unknown food_id '{food_id}'", 404)


@bp.post("/predict")
def predict():
    model, foods = state().model, state().store.foods
    if not model.available():
        return error("No recognition model loaded. Add backend/models/food_model.onnx (or food_model.keras "
                     "with TensorFlow 2.20+) + labels.json, or let the user pick from /api/foods.", 503)
    goal = request.form.get("goal", "balanced")
    if goal not in GOALS:
        return error(f"'goal' must be one of {sorted(GOALS)}")
    data, bad = read_photo()
    if bad:
        return bad
    try:
        top = model.predict(data, k=5)
    except Exception as e:
        return error(f"recognition failed: {e}", 500)
    preds = [{"food_id": label, "name": foods[label]["name"] if label in foods else label,
              "confidence": round(p, 4)} for label, p in top]
    for p in preds:
        if p["food_id"] in foods:
            with_image(p)
    best = foods.get(preds[0]["food_id"]) if preds else None
    low = bool(preds) and preds[0]["confidence"] < LOW_CONFIDENCE
    swaps = recommend(best, state().store.alternatives, 1.0, goal, PREDICT_SWAPS)[1] if best else []
    if preds:
        g.log.update(food_id=preds[0]["food_id"], confidence=preds[0]["confidence"], low_conf=int(low),
                     goal=goal, n_swaps=len(swaps))
    uid = token_user()
    photo_id = state().users.add_photo(uid, data, preds[0]["food_id"], preds[0]["confidence"]) \
        if uid and preds else None
    return jsonify({
        "photo_id": photo_id,  # saved in the gallery when signed in, else null
        "model": model.name,
        "model_classes": len(model.labels),   # dishes the model knows; others -> manual picker
        "predictions": preds,
        "low_confidence": low,
        "top": with_image(public(best)) if best else None,
        "goal": goal,
        "swaps": [with_image(s) for s in swaps],  # healthier swaps for the top guess, 1x portion
    })


@bp.post("/recommend")
def recommend_swaps():
    store = state().store
    body = request.get_json(silent=True) or {}
    food = store.foods.get(body.get("food_id", ""))
    if food is None:
        return error("missing or unknown 'food_id'")
    g.log["food_id"] = food["food_id"]
    try:
        portion = float(body.get("portion", 1.0))
        limit = int(body.get("limit", 4))
    except (TypeError, ValueError):
        return error("'portion' and 'limit' must be numbers")
    if not 0.5 <= portion <= 2.0:
        return error("'portion' must be between 0.5 and 2.0")
    if not 1 <= limit <= MAX_LIMIT:
        return error(f"'limit' must be between 1 and {MAX_LIMIT}")
    goal = body.get("goal", "balanced")
    if goal not in GOALS:
        return error(f"'goal' must be one of {sorted(GOALS)}")
    eaten, swaps = recommend(food, store.alternatives, portion, goal, limit)
    g.log.update(goal=goal, n_swaps=len(swaps))
    return jsonify({
        "eaten": with_image(public(eaten)), "goal": goal, "swaps": [with_image(s) for s in swaps],
        "message": None if swaps else "Already a light choice: no lighter, healthier swap in the catalog.",
        "menu_swaps": menu_swaps(food["food_id"], eaten, store.menu),
    })


@bp.post("/target")
def target():
    b = request.get_json(silent=True) or {}
    try:
        age, w, h = float(b["age"]), float(b["weight_kg"]), float(b["height_cm"])
    except (KeyError, TypeError, ValueError):
        return error("send numeric 'age', 'weight_kg' and 'height_cm'")
    if not (10 <= age <= 100 and 25 <= w <= 300 and 100 <= h <= 250):
        return error("'age' must be 10-100, 'weight_kg' 25-300 and 'height_cm' 100-250")
    sex = b.get("sex", "male")
    if sex not in ("male", "female"):
        return error("'sex' must be 'male' or 'female'")
    goal = b.get("goal", "balanced")
    if goal not in GOALS:
        return error(f"'goal' must be one of {sorted(GOALS)}")
    activity = b.get("activity", "light")
    if activity not in ACTIVITY:
        return error(f"'activity' must be one of {list(ACTIVITY)}")
    g.log["goal"] = goal
    return jsonify(daily_target(sex, age, w, h, activity, goal))


def daily_target(sex, age, w, h, activity="light", goal="balanced"):
    """Mifflin-St Jeor BMR x activity, -500 kcal to lose weight, plus protein / carb / fat grams.

    The 1500 / 1200 kcal floor never puts a weight-loss target above maintenance. Protein is per kg of
    a healthy weight (BMI 25 at most) and fat is at least 20 % of the kcal, carbs take what is left.
    plan_kcal is kcal kept inside the range POST /api/plans accepts."""
    bmr = 10 * w + 6.25 * h - 5 * age + (5 if sex == "male" else -161)
    tdee = bmr * ACTIVITY[activity]
    floor = 1500 if sex == "male" else 1200
    kcal = max(tdee - 500, min(floor, tdee)) if goal == "lose_weight" else max(tdee, floor)
    ref_w = min(w, 25 * (h / 100) ** 2)
    protein = ref_w * (1.6 if goal in ("high_protein", "lose_weight") else 1.0)
    carb_share = 0.25 if goal == "low_carb" else 0.50
    carbs = kcal * carb_share / 4
    fat = (kcal - protein * 4 - carbs * 4) / 9
    if fat < kcal * MIN_FAT_SHARE / 9:
        fat = kcal * MIN_FAT_SHARE / 9
        carbs = max((kcal - protein * 4 - fat * 9) / 4, 0)
    lo, hi = plans.KCAL_RANGE
    return {"bmr": round(bmr), "tdee": round(tdee), "kcal": round(kcal), "plan_kcal": round(min(max(kcal, lo), hi)),
            "protein_g": round(protein), "carbs_g": round(carbs), "fat_g": round(fat), "goal": goal}


# ---------- 7-day meal plan ----------

def lookup(food_id):
    store = state().store
    return store.foods.get(food_id) or store.alternatives.get(food_id)


def owner_error(user_id):
    """Plans of registered users need that user's token; anonymous install ids stay open."""
    if user_id == "me" or state().users.exists(user_id):
        uid = token_user()
        if uid is None:
            return error("sign in first: send 'Authorization: Bearer <token>'", 401)
        if user_id != "me" and uid != user_id:
            return error("this plan belongs to another account", 403)
    return None


@bp.url_value_preprocessor
def resolve_me(endpoint, values):
    if values and values.get("user_id") == "me":
        uid = token_user()
        if uid:
            values["user_id"] = uid


def plan_or_404(user_id):
    bad = owner_error(user_id)
    if bad:
        return None, None, bad
    if not plans.USER_ID.match(user_id):
        return None, None, error("'user_id' must be 6-64 letters, digits, - or _ (make one UUID per install)")
    meta, rows = state().plans.get(user_id)
    if meta is None:
        return None, None, error(f"no plan for '{user_id}', create one with POST /api/plans", 404)
    return meta, rows, None


def day_json(day, rows, kcal_target):
    view = plans.day_view(day, [r for r in rows if r["day"] == day], kcal_target, lookup)
    for m in view["meals"]:
        m["food"] = with_image(public(m["food"]))
    return view


def plan_json(meta, rows):
    days = [day_json(d, rows, meta["kcal_target"]) for d in range(1, plans.DAYS + 1)]
    return {"user_id": meta["user_id"], "goal": meta["goal"], "kcal_target": round(meta["kcal_target"]),
            "meals_per_day": plans.MEALS, "meal_share": plans.MEAL_SHARE, "days": days,
            "week": {"kcal": sum(d["totals"]["kcal"] for d in days),
                     "target_kcal": round(meta["kcal_target"]) * plans.DAYS}}


def parse_target(body, default=None):
    try:
        kcal = float(body.get("kcal_target", default))
    except (TypeError, ValueError):
        return None, error("'kcal_target' must be a number (use the kcal from /api/target)")
    lo, hi = plans.KCAL_RANGE
    if not lo <= kcal <= hi:
        return None, error(f"'kcal_target' must be between {lo} and {hi}")
    return kcal, None


def rebalance_day(user_id, day, meta):
    _, rows = state().plans.get(user_id)
    new = plans.rebalance([r for r in rows if r["day"] == day], meta["kcal_target"], lookup)
    state().plans.set_portions(user_id, day, new)


def slot_or_error(rows, day, meal):
    try:
        day = int(day)
    except ValueError:
        day = 0
    if not 1 <= day <= plans.DAYS or meal not in plans.MEALS:
        return None, None, error(f"day must be 1-{plans.DAYS} and meal one of {plans.MEALS}")
    slot = next(r for r in rows if r["day"] == day and r["meal"] == meal)
    return day, slot, None


def others_today(rows, day, meal):
    return {r["food_id"] for r in rows if r["day"] == day and r["meal"] != meal}


def parse_portion(value, default):
    if value is None:
        return default, None
    try:
        portion = float(value)
    except (TypeError, ValueError):
        portion = 0
    if not plans.PORTIONS[0] <= portion <= plans.MAX_PORTION:
        return None, error(f"'portion' must be between {plans.PORTIONS[0]} and {plans.MAX_PORTION}")
    return portion, None


def replace_meal(user_id, meta, day, slot, food, portion, source):
    old_kcal = lookup(slot["food_id"])["kcal"] * slot["portion"]
    st = state().plans
    st.set_meal(user_id, day, slot["meal"], food["food_id"], portion, source)
    st.log_change(user_id, day, slot["meal"], slot["food_id"], food["food_id"], source,
                  round(old_kcal), round(food["kcal"] * portion))
    rebalance_day(user_id, day, meta)
    g.log.update(food_id=food["food_id"], goal=meta["goal"])
    _, rows = st.get(user_id)
    return day_json(day, rows, meta["kcal_target"])


@bp.post("/plans")
def create_plan():
    body = request.get_json(silent=True) or {}
    user_id = str(body.get("user_id") or token_user() or "")
    bad = owner_error(user_id)
    if bad:
        return bad
    if not plans.USER_ID.match(user_id):
        return error("'user_id' must be 6-64 letters, digits, - or _ (make one UUID per install)")
    goal = body.get("goal", "balanced")
    if goal not in GOALS:
        return error(f"'goal' must be one of {sorted(GOALS)}")
    kcal, bad = parse_target(body, 2000)
    if bad:
        return bad
    store = state().store
    state().plans.create(user_id, goal, kcal, plans.generate(store.foods, store.alternatives, goal, kcal))
    g.log["goal"] = goal
    return jsonify(plan_json(*state().plans.get(user_id))), 201


@bp.get("/plans/<user_id>")
def get_plan(user_id):
    meta, rows, bad = plan_or_404(user_id)
    return bad or jsonify(plan_json(meta, rows))


@bp.patch("/plans/<user_id>")
def update_plan(user_id):
    meta, rows, bad = plan_or_404(user_id)
    if bad:
        return bad
    body = request.get_json(silent=True) or {}
    fields = {}
    if "kcal_target" in body:
        fields["kcal_target"], bad = parse_target(body)
        if bad:
            return bad
    if "goal" in body:
        if body["goal"] not in GOALS:
            return error(f"'goal' must be one of {sorted(GOALS)}")
        fields["goal"] = body["goal"]
    if not fields:
        return error("send 'kcal_target' and/or 'goal'")
    st = state().plans
    st.update_meta(user_id, **fields)
    meta = dict(meta, **fields)
    # meals the app planned are picked again for the new target / goal; the user's own choices stay
    store = state().store
    chosen = {(r["day"], r["meal"]): r["food_id"] for r in rows if r["source"] != "plan"}
    for d, m, f, p in plans.generate(store.foods, store.alternatives, meta["goal"], meta["kcal_target"],
                                     keep=chosen):
        st.set_meal(user_id, d, m, f, p, "plan")
    # chosen swaps / picks keep their food but are re-sized to the new meal budget; photos stay as eaten
    for r in rows:
        if r["source"] in ("swap", "manual"):
            st.set_portions(user_id, r["day"], {r["meal"]: plans.fit_portion(
                lookup(r["food_id"]), plans.meal_budget(meta["kcal_target"], r["meal"]))})
    for day in range(1, plans.DAYS + 1):
        rebalance_day(user_id, day, meta)
    return jsonify(plan_json(*st.get(user_id)))


@bp.delete("/plans/<user_id>")
def delete_plan(user_id):
    _, _, bad = plan_or_404(user_id)
    if bad:
        return bad
    state().plans.delete(user_id)
    return jsonify({"deleted": user_id})


@bp.get("/plans/<user_id>/<day>/<meal>/swaps")
def plan_meal_swaps(user_id, day, meal):
    meta, rows, bad = plan_or_404(user_id)
    if bad:
        return bad
    day, slot, bad = slot_or_error(rows, day, meal)
    if bad:
        return bad
    try:
        limit = int(request.args.get("limit", 4))
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_LIMIT:
        return error(f"'limit' must be between 1 and {MAX_LIMIT}")
    budget = plans.meal_budget(meta["kcal_target"], meal)
    eaten, swaps = plans.slot_swaps(lookup(slot["food_id"]), slot["portion"], budget,
                                    state().store.alternatives, meta["goal"], limit,
                                    exclude=others_today(rows, day, meal))
    g.log.update(food_id=slot["food_id"], goal=meta["goal"], n_swaps=len(swaps))
    return jsonify({"day": day, "meal": meal, "budget_kcal": round(budget),
                    "current": with_image(public(eaten)), "swaps": [with_image(s) for s in swaps],
                    "message": None if swaps else "Already a light choice for this meal."})


@bp.put("/plans/<user_id>/<day>/<meal>")
def set_plan_meal(user_id, day, meal):
    meta, rows, bad = plan_or_404(user_id)
    if bad:
        return bad
    day, slot, bad = slot_or_error(rows, day, meal)
    if bad:
        return bad
    body = request.get_json(silent=True) or {}
    food = lookup(str(body.get("food_id", "")))
    if food is None:
        return error("missing or unknown 'food_id' (any dish or swap id)")
    source = body.get("source", "swap")
    if source not in plans.SOURCES - {"plan"}:
        return error("'source' must be 'swap', 'manual' or 'photo'")
    if source == "photo":
        default = 1.0  # what the user really ate
    else:
        cap = lookup(slot["food_id"])["kcal"] * slot["portion"] if source == "swap" else None
        default = plans.fit_portion(food, plans.meal_budget(meta["kcal_target"], meal), cap_kcal=cap)
    portion, bad = parse_portion(body.get("portion"), default)
    if bad:
        return bad
    return jsonify({"day": replace_meal(user_id, meta, day, slot, food, portion, source)})


@bp.post("/plans/<user_id>/<day>/<meal>/photo")
def plan_meal_photo(user_id, day, meal):
    meta, rows, bad = plan_or_404(user_id)
    if bad:
        return bad
    day, slot, bad = slot_or_error(rows, day, meal)
    if bad:
        return bad
    model = state().model
    if not model.available():
        return error("No recognition model loaded; pick the food from /api/foods and PUT it with "
                     "source 'photo'.", 503)
    portion, bad = parse_portion(request.form.get("portion"), 1.0)
    if bad:
        return bad
    data, bad = read_photo()
    if bad:
        return bad
    try:
        top = model.predict(data, k=5)
    except Exception as e:
        return error(f"recognition failed: {e}", 500)
    foods = state().store.foods
    preds = [with_image({"food_id": l, "name": foods[l]["name"], "confidence": round(p, 4)})
             for l, p in top if l in foods]
    if not preds:
        return error("the model returned no known dish; pick it from /api/foods", 500)
    low = preds[0]["confidence"] < LOW_CONFIDENCE
    eaten = foods[preds[0]["food_id"]]
    view = replace_meal(user_id, meta, day, slot, eaten, portion, "photo")
    if state().users.exists(user_id):
        state().users.add_photo(user_id, data, eaten["food_id"], preds[0]["confidence"], day, meal, "plan")
    g.log.update(confidence=preds[0]["confidence"], low_conf=int(low))
    _, swaps = plans.slot_swaps(eaten, portion, plans.meal_budget(meta["kcal_target"], meal),
                                state().store.alternatives, meta["goal"], exclude=others_today(rows, day, meal))
    return jsonify({"predictions": preds, "low_confidence": low, "day": view,
                    "swaps": [with_image(s) for s in swaps]})


# ---------- accounts ----------

def token_user():
    """User id of a valid 'Authorization: Bearer <token>', else None (cached per request)."""
    if "uid" not in g:
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        g.uid = state().users.user_for_token(token) if token else None
    return g.uid


def me_or_401():
    uid = token_user()
    if uid is None:
        return None, error("sign in first: send 'Authorization: Bearer <token>'", 401)
    user = state().users.get(uid)
    return (user, None) if user else (None, error("account not found", 401))


def parse_profile(body, require_name=False):
    """Validated profile fields from a JSON body (only the ones sent)."""
    out = {}
    if "name" in body or require_name:
        name = str(body.get("name", "")).strip()
        if not 1 <= len(name) <= 60:
            return None, error("'name' is required (1-60 characters)")
        out["name"] = name
    if body.get("sex") is not None:
        if body["sex"] not in ("male", "female"):
            return None, error("'sex' must be 'male' or 'female'")
        out["sex"] = body["sex"]
    for key, (lo, hi) in users.LIMITS.items():
        if body.get(key) is not None:
            try:
                v = float(body[key])
            except (TypeError, ValueError):
                v = None
            if v is None or not lo <= v <= hi:
                return None, error(f"'{key}' must be a number from {lo} to {hi}")
            out[key] = v
    if body.get("activity") is not None:
        if body["activity"] not in ACTIVITY:
            return None, error(f"'activity' must be one of {list(ACTIVITY)}")
        out["activity"] = body["activity"]
    if body.get("goal") is not None:
        if body["goal"] not in GOALS:
            return None, error(f"'goal' must be one of {sorted(GOALS)}")
        out["goal"] = body["goal"]
    return out, None


def profile_json(user):
    value, label = users.bmi(user["height_cm"], user["weight_kg"])
    complete = all(user[k] for k in ("sex", "age", "height_cm", "weight_kg"))
    target = daily_target(user["sex"], user["age"], user["weight_kg"], user["height_cm"],
                          user["activity"] or "light", user["goal"] or "balanced") if complete else None
    return {
        "id": user["id"], "email": user["email"], "name": user["name"], "sex": user["sex"],
        "age": user["age"], "height_cm": user["height_cm"], "weight_kg": user["weight_kg"],
        "activity": user["activity"], "goal": user["goal"], "bmi": value, "bmi_label": label,
        "daily_target": target,
        "avatar_url": url_for("flutter_api.my_avatar", _external=True) if user["has_avatar"] else None,
        "has_plan": state().plans.get(user["id"])[0] is not None, "created": user["created"],
    }


def auth_json(uid, code=200):
    return jsonify({"token": state().users.new_token(uid), "user": profile_json(state().users.get(uid))}), code


@bp.post("/auth/register")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not users.EMAIL.match(email):
        return error("enter a valid 'email'")
    if len(password) < users.MIN_PASSWORD:
        return error(f"'password' must be at least {users.MIN_PASSWORD} characters")
    profile, bad = parse_profile(body, require_name=True)
    if bad:
        return bad
    if state().users.by_email(email):
        return error("an account with this email already exists; log in instead", 409)
    uid = state().users.create(email, profile.pop("name"), password, profile)
    state().users.log_event(uid, "register")
    return auth_json(uid, 201)


@bp.post("/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    keys = ("api-ip:" + str(request.remote_addr), "api-email:" + email)
    wait = state().throttle.retry_after(*keys)
    if wait:
        resp = error(f"too many failed sign-ins; try again in {wait // 60 + 1} minutes", 429)
        resp[0].headers["Retry-After"] = str(wait)
        return resp
    user = state().users.by_email(email)
    if user is None or not state().users.check_password(user, str(body.get("password", ""))):
        state().throttle.fail(*keys)
        return error("wrong email or password", 401)
    state().throttle.clear(keys[1])
    state().users.log_event(user["id"], "login")
    return auth_json(user["id"])


@bp.post("/auth/logout")
def logout():
    uid = token_user()
    if uid:
        state().users.revoke(request.headers["Authorization"][7:].strip())
        state().users.log_event(uid, "logout")
    return jsonify({"logged_out": True})


@bp.get("/me")
def me():
    user, bad = me_or_401()
    if bad:
        return bad
    state().users.touch(user["id"])
    return jsonify(profile_json(user))


@bp.patch("/me")
def update_me():
    user, bad = me_or_401()
    if bad:
        return bad
    fields, bad = parse_profile(request.get_json(silent=True) or {})
    if bad:
        return bad
    state().users.update(user["id"], fields)
    return jsonify(profile_json(state().users.get(user["id"])))


@bp.post("/me/password")
def change_password():
    user, bad = me_or_401()
    if bad:
        return bad
    body = request.get_json(silent=True) or {}
    if not state().users.check_password(user, str(body.get("current_password", ""))):
        return error("current password is wrong", 401)
    new = str(body.get("new_password", ""))
    if len(new) < users.MIN_PASSWORD:
        return error(f"'new_password' must be at least {users.MIN_PASSWORD} characters")
    state().users.set_password(user["id"], new)  # logs out every device
    return auth_json(user["id"])


@bp.delete("/me")
def delete_me():
    user, bad = me_or_401()
    if bad:
        return bad
    state().plans.delete(user["id"])
    state().users.delete(user["id"])
    return jsonify({"deleted": True})


@bp.put("/me/avatar")
def set_avatar():
    user, bad = me_or_401()
    if bad:
        return bad
    data, bad = read_photo()
    if bad:
        return bad
    state().users.set_avatar(user["id"], data)
    return jsonify(profile_json(state().users.get(user["id"])))


def send_private_jpeg(path):
    if not path or not os.path.exists(path):
        return error("no photo", 404)
    with open(path, "rb") as fh:
        resp = send_file(io.BytesIO(fh.read()), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@bp.get("/me/avatar")
def my_avatar():
    user, bad = me_or_401()
    if bad:
        return bad
    return send_private_jpeg(state().users.avatar_path(user["id"]) if user["has_avatar"] else None)


def photo_json(uid, p):
    return {"id": p["id"], "food_id": p["food_id"], "name": (lookup(p["food_id"]) or {}).get("name", p["food_id"]),
            "confidence": p["confidence"], "day": p["day"], "meal": p["meal"], "source": p["source"],
            "taken": p["ts"], "url": url_for("flutter_api.my_photo", photo_id=p["id"], _external=True)}


@bp.get("/me/photos")
def my_photos():
    user, bad = me_or_401()
    if bad:
        return bad
    items = [photo_json(user["id"], p) for p in state().users.photos(user["id"])]
    return jsonify({"count": len(items), "photos": items})


@bp.get("/me/photos/<int:photo_id>")
def my_photo(photo_id):
    user, bad = me_or_401()
    if bad:
        return bad
    if not state().users.photo(user["id"], photo_id):
        return error("no such photo", 404)
    return send_private_jpeg(state().users.photo_path(user["id"], photo_id))


@bp.delete("/me/photos/<int:photo_id>")
def delete_my_photo(photo_id):
    user, bad = me_or_401()
    if bad:
        return bad
    if not state().users.photo(user["id"], photo_id):
        return error("no such photo", 404)
    state().users.delete_photo(user["id"], photo_id)
    return jsonify({"deleted": photo_id})
