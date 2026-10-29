"""Admin dashboard (web pages for the team, not for the Flutter app).

  /admin/            overview: API usage, model confidence, popular dishes, recommender numbers
  /admin/foods       browse and edit the 101 dishes and the 50 healthier swaps (writes the CSVs),
                     upload a photo for each one (shown in the Flutter app through image_url)
  /admin/requests    the request log, filterable by endpoint and errors
  /admin/try         upload a photo and see the recognised dish and its healthier swaps with photos
  /admin/users       everyone who signed up in the app; click one for profile, photos, weight and plan
  /admin/plans       users' 7-day meal plans: which swaps and photos replaced which meals, day totals
  /admin/api/stats   the overview numbers as JSON (for a future admin screen in Flutter)

Login with NUTRIGO_ADMIN_PASSWORD. Every form POST carries a CSRF token from the session.
"""
import hmac
import io
import re
import secrets
import time
from datetime import date, timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from evaluate import evaluate
from flutter_api import image_url
from images import thumbnail_data_uri
from nutrition import NUMERIC, public
from recommender import GOALS, RELATED, recommend

bp = Blueprint("admin", __name__, url_prefix="/admin")

TABLES = {"foods": "Dishes (Food-101)", "alternatives": "Healthier swaps"}
CATEGORIES = sorted(RELATED)
FOOD_ID = re.compile(r"^[a-z0-9_]{2,60}$")
ENDPOINTS = {"predict": "Predict (photo)", "recommend_swaps": "Recommend", "list_foods": "Food list",
             "get_food": "One food", "target": "Daily target", "status": "Status",
             "create_plan": "Plan created", "get_plan": "Plan opened", "update_plan": "Plan target changed",
             "delete_plan": "Plan deleted", "plan_meal_swaps": "Plan meal swaps",
             "set_plan_meal": "Plan meal replaced", "plan_meal_photo": "Plan meal photo",
             "register": "Sign up", "login": "Log in", "logout": "Log out", "me": "Profile opened",
             "update_me": "Profile updated", "delete_me": "Account deleted", "set_avatar": "Profile photo",
             "my_photos": "Gallery opened", "delete_my_photo": "Gallery photo deleted"}


def state():
    return current_app.extensions["nutrigo"]


@bp.before_request
def require_login():
    if request.endpoint == "admin.login":
        return None
    if not session.get("admin"):
        if request.path.startswith("/admin/api/"):
            return jsonify({"error": "login required"}), 401
        return redirect(url_for("admin.login", next=request.path))
    if request.method == "POST" and not hmac.compare_digest(
            request.form.get("csrf", ""), session.get("csrf", "")):
        abort(400, "bad CSRF token, reload the page")
    return None


@bp.context_processor
def template_globals():
    return {"csrf": session.get("csrf", ""), "endpoints": ENDPOINTS, "tables": TABLES,
            "model": state().model, "img_url": lambda fid: image_url(fid, external=False),
            "has_photo": lambda fid: state().images.find(fid) is not None}


@bp.app_template_filter("datetime")
def format_ts(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        given = request.form.get("password", "").encode()
        if hmac.compare_digest(given, state().admin_password.encode()):
            session.clear()
            session.update(admin=True, csrf=secrets.token_hex(16))
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin.overview"))
        flash("Wrong password.")
    return render_template("admin/login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ---------- overview ----------

def collect_stats(days=14):
    st = state()
    q = st.log.execute
    now = time.time()
    total, errors, avg_ms = q("SELECT COUNT(*), COALESCE(SUM(status >= 400), 0), AVG(ms) FROM requests")[0]
    last24 = q("SELECT COUNT(*) FROM requests WHERE ts >= ?", (now - 86400,))[0][0]
    n_pred, avg_conf, low_rate = q(
        "SELECT COUNT(*), AVG(confidence), AVG(low_conf) FROM requests WHERE endpoint='predict' AND status=200")[0]

    since = date.today() - timedelta(days=days - 1)
    per_day = {r[0]: r[1] for r in q(
        "SELECT date(ts, 'unixepoch', 'localtime') d, COUNT(*) FROM requests WHERE d >= ? GROUP BY d",
        (since.isoformat(),))}
    daily = [{"day": (since + timedelta(i)).isoformat(), "n": per_day.get((since + timedelta(i)).isoformat(), 0)}
             for i in range(days)]

    foods = st.store.foods
    name = lambda fid: foods[fid]["name"] if fid in foods else fid  # noqa: E731
    top_pred = [{"food_id": r[0], "name": name(r[0]), "n": r[1], "confidence": r[2]} for r in q(
        "SELECT food_id, COUNT(*) n, AVG(confidence) FROM requests WHERE endpoint='predict' AND status=200 "
        "GROUP BY food_id ORDER BY n DESC LIMIT 10")]
    top_rec = [{"food_id": r[0], "name": name(r[0]), "n": r[1], "with_swap": r[2]} for r in q(
        "SELECT food_id, COUNT(*) n, AVG(n_swaps > 0) FROM requests WHERE endpoint='recommend_swaps' "
        "AND status=200 GROUP BY food_id ORDER BY n DESC LIMIT 10")]
    goals = [{"goal": r[0], "n": r[1]} for r in q(
        "SELECT goal, COUNT(*) n FROM requests WHERE endpoint='recommend_swaps' AND status=200 "
        "GROUP BY goal ORDER BY n DESC")]
    by_endpoint = [{"endpoint": r[0], "label": ENDPOINTS.get(r[0], r[0]), "n": r[1], "errors": r[2], "ms": r[3]}
                   for r in q("SELECT endpoint, COUNT(*) n, SUM(status >= 400), AVG(ms) FROM requests "
                              "GROUP BY endpoint ORDER BY n DESC")]
    _, rec = evaluate("balanced", foods, st.store.alternatives)
    n_plans = st.plans.execute("SELECT COUNT(*) FROM plans")[0][0]
    n_users, new_users = st.users.execute("SELECT COUNT(*), COALESCE(SUM(created >= ?), 0) FROM users",
                                          (now - 7 * 86400,))[0]
    plan_swaps = st.plans.execute("SELECT COUNT(*) FROM plan_meals WHERE source = 'swap'")[0][0]
    plan_photos = st.plans.execute("SELECT COUNT(*) FROM plan_meals WHERE source = 'photo'")[0][0]
    return {
        "requests": {"total": total, "last_24h": last24, "errors": errors,
                     "error_rate": errors / total if total else 0.0, "avg_ms": avg_ms or 0.0},
        "predictions": {"total": n_pred, "avg_confidence": avg_conf, "low_confidence_rate": low_rate},
        "model": {"name": st.model.name, "ready": st.model.available(), "classes": len(st.model.labels)},
        "catalog": {"foods": len(foods), "alternatives": len(st.store.alternatives),
                    "fastfood_items": len(st.store.menu),
                    "food_photos": sum(st.images.find(f) is not None for f in foods),
                    "swap_photos": sum(st.images.find(f) is not None for f in st.store.alternatives)},
        "recommender": rec,
        "plans": {"users": n_plans, "swaps_chosen": plan_swaps, "photo_meals": plan_photos},
        "accounts": {"total": n_users, "new_7d": new_users},
        "daily": daily, "top_predicted": top_pred, "top_recommended": top_rec,
        "goals": goals, "by_endpoint": by_endpoint,
    }


@bp.get("/")
def overview():
    recent = state().log.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 10")
    return render_template("admin/overview.html", s=collect_stats(), recent=recent)


@bp.get("/api/stats")
def stats_json():
    return jsonify(collect_stats())


# ---------- data editing ----------

def table_or_404(table):
    if table not in TABLES:
        abort(404)
    return state().store.tables[table]


@bp.get("/foods")
def foods():
    table = request.args.get("table", "foods")
    rows = table_or_404(table)
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("category", "")
    shown = [r for r in rows.values()
             if (not q or q in r["name"].lower() or q in r["food_id"]) and (not cat or r["category"] == cat)]
    shown.sort(key=lambda r: r["name"])
    return render_template("admin/foods.html", table=table, rows=shown, total=len(rows), q=q, cat=cat,
                           categories=CATEGORIES)


def parse_form(form, food_id):
    row, errors = {"food_id": food_id}, []
    if not FOOD_ID.match(food_id):
        errors.append("ID: 2-60 lowercase letters, digits or _ (e.g. grilled_chicken_wrap).")
    for key in ("name", "serving"):
        row[key] = form.get(key, "").strip()
        if not row[key]:
            errors.append(f"{key.capitalize()} is required.")
    row["category"] = form.get("category", "")
    if row["category"] not in CATEGORIES:
        errors.append("Pick a category from the list.")
    for key in NUMERIC:
        try:
            row[key] = float(form.get(key, ""))
            if not 0 <= row[key] <= 10000:
                raise ValueError
        except ValueError:
            errors.append(f"{key} must be a number from 0 to 10000.")
    row["tags"] = [t.strip().lower().replace(" ", "_") for t in form.get("tags", "").split(",") if t.strip()]
    return row, errors


@bp.route("/foods/<table>/new", methods=["GET", "POST"])
@bp.route("/foods/<table>/<food_id>", methods=["GET", "POST"])
def edit_food(table, food_id=None):
    rows = table_or_404(table)
    is_new = food_id is None
    if not is_new and food_id not in rows:
        abort(404)
    if request.method == "POST":
        fid = request.form.get("food_id", "").strip() if is_new else food_id
        row, errors = parse_form(request.form, fid)
        if is_new and fid in rows:
            errors.append(f"'{fid}' already exists.")
        photo = request.files.get("photo")
        photo_data = photo.read() if photo and photo.filename else None
        if photo_data:
            try:
                from PIL import Image
                Image.open(io.BytesIO(photo_data)).verify()
            except Exception:
                errors.append("The photo is not a readable image (use JPG, PNG or WebP).")
        if not errors:
            state().store.save(table, row)
            if photo_data:
                state().images.save(fid, photo_data)
            elif request.form.get("remove_photo"):
                state().images.delete(fid)
            flash(f"Saved {row['name']}.")
            return redirect(url_for("admin.foods", table=table))
        for e in errors:
            flash(e, "error")
        current = dict(request.form, tags=request.form.get("tags", ""))
    else:
        current = dict(rows[food_id], tags=", ".join(rows[food_id]["tags"])) if not is_new else {}
    model_classes = set(state().model.labels)
    return render_template("admin/food_form.html", table=table, food_id=food_id, row=current,
                           categories=CATEGORIES, numeric=NUMERIC,
                           in_model=food_id in model_classes)


@bp.post("/foods/<table>/<food_id>/delete")
def delete_food(table, food_id):
    rows = table_or_404(table)
    if table == "foods":
        abort(400, "Dishes are Food-101 classes and can only be edited, not deleted.")
    if food_id in rows:
        state().store.delete(table, food_id)
        state().images.delete(food_id)
        flash(f"Deleted {rows[food_id]['name']}.")
    return redirect(url_for("admin.foods", table=table))


# ---------- request log ----------

@bp.get("/requests")
def requests_log():
    endpoint = request.args.get("endpoint", "")
    errors_only = request.args.get("errors") == "1"
    sql, args = "SELECT * FROM requests WHERE 1=1", []
    if endpoint:
        sql += " AND endpoint = ?"
        args.append(endpoint)
    if errors_only:
        sql += " AND status >= 400"
    rows = state().log.execute(sql + " ORDER BY id DESC LIMIT 200", args)
    return render_template("admin/requests.html", rows=rows, endpoint=endpoint, errors_only=errors_only)


# ---------- try the model ----------

@bp.route("/try", methods=["GET", "POST"])
def try_model():
    st, result = state(), None
    goal = request.form.get("goal", "balanced")
    if request.method == "POST":
        file = request.files.get("image")
        if not st.model.available():
            flash("No recognition model is loaded, see backend/models/README.md.", "error")
        elif not file or not file.filename:
            flash("Choose a photo first.", "error")
        else:
            data = file.read()
            try:
                top = st.model.predict(data, k=5)
                photo = thumbnail_data_uri(data)
            except Exception as e:
                flash(f"Could not read that photo: {e}", "error")
            else:
                foods = st.store.foods
                preds = [{"food_id": l, "name": foods[l]["name"] if l in foods else l, "confidence": p}
                         for l, p in top]
                best = foods.get(preds[0]["food_id"]) if preds else None
                swaps = recommend(best, st.store.alternatives, 1.0, goal if goal in GOALS else "balanced")[1] \
                    if best else []
                result = {"preds": preds, "best": public(best) if best else None, "swaps": swaps,
                          "photo": photo}
    return render_template("admin/try.html", result=result, goals=sorted(GOALS), goal=goal)


# ---------- meal plans ----------

SOURCE_LABELS = {"plan": "Planned", "swap": "Swap chosen", "manual": "Picked from list", "photo": "Photo (eaten)"}


def food_name(food_id):
    st = state().store
    f = st.foods.get(food_id) or st.alternatives.get(food_id)
    return f["name"] if f else food_id


@bp.get("/plans")
def plans_overview():
    q = state().plans.execute
    n_plans, avg_target = q("SELECT COUNT(*), AVG(kcal_target) FROM plans")[0]
    by_source = {r[0]: r[1] for r in q("SELECT source, COUNT(*) FROM plan_meals GROUP BY source")}
    total_meals = sum(by_source.values())
    changes = {r[0]: (r[1], r[2]) for r in q(
        "SELECT source, COUNT(*), AVG(kcal_before - kcal_after) FROM plan_changes GROUP BY source")}
    top_swaps = [{"name": food_name(r[0]), "food_id": r[0], "n": r[1]} for r in q(
        "SELECT new_food_id, COUNT(*) n FROM plan_changes WHERE source = 'swap' GROUP BY new_food_id "
        "ORDER BY n DESC LIMIT 10")]
    top_photos = [{"name": food_name(r[0]), "food_id": r[0], "n": r[1]} for r in q(
        "SELECT new_food_id, COUNT(*) n FROM plan_changes WHERE source = 'photo' GROUP BY new_food_id "
        "ORDER BY n DESC LIMIT 10")]
    users = q("SELECT p.user_id, p.goal, p.kcal_target, p.updated, u.name AS name, "
              "SUM(m.source != 'plan') AS changed FROM plans p JOIN plan_meals m USING (user_id) "
              "LEFT JOIN users u ON u.id = p.user_id "
              "GROUP BY p.user_id ORDER BY p.updated DESC LIMIT 100")
    recent = q("SELECT * FROM plan_changes ORDER BY id DESC LIMIT 20")
    return render_template("admin/plans.html", n_plans=n_plans, avg_target=avg_target or 0,
                           by_source=by_source, total_meals=total_meals, changes=changes,
                           top_swaps=top_swaps, top_photos=top_photos, users=users, recent=recent,
                           source_labels=SOURCE_LABELS, food_name=food_name)


@bp.get("/plans/<user_id>")
def plan_detail(user_id):
    import plans as planner
    from flutter_api import lookup
    meta, rows = state().plans.get(user_id)
    if meta is None:
        abort(404)
    days = [planner.day_view(d, [r for r in rows if r["day"] == d], meta["kcal_target"], lookup)
            for d in range(1, planner.DAYS + 1)]
    recent = state().plans.execute("SELECT * FROM plan_changes WHERE user_id = ? ORDER BY id DESC LIMIT 30",
                                   (user_id,))
    return render_template("admin/plan_detail.html", meta=meta, days=days, meals=planner.MEALS,
                           recent=recent, source_labels=SOURCE_LABELS, food_name=food_name,
                           owner=state().users.get(user_id))


# ---------- app users ----------

def user_rows(q=""):
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM user_photos p WHERE p.user_id = u.id) AS n_photos, "
           "EXISTS (SELECT 1 FROM plans WHERE plans.user_id = u.id) AS has_plan FROM users u")
    args = ()
    if q:
        sql += " WHERE lower(u.name) LIKE ? OR lower(u.email) LIKE ?"
        args = (f"%{q.lower()}%", f"%{q.lower()}%")
    return [dict(r) for r in state().users.execute(sql + " ORDER BY u.last_seen DESC LIMIT 500", args)]


@bp.get("/users")
def users_list():
    import users as accounts
    q = request.args.get("q", "").strip()
    rows = user_rows(q)
    for r in rows:
        r["bmi"], r["bmi_label"] = accounts.bmi(r["height_cm"], r["weight_kg"])
    week = time.time() - 7 * 86400
    stats = state().users.execute(
        "SELECT COUNT(*), SUM(created >= ?), SUM(last_seen >= ?), AVG(weight_kg), AVG(height_cm) FROM users",
        (week, week))[0]
    return render_template("admin/users.html", rows=rows, q=q, stats=stats)


@bp.get("/users/<uid>")
def user_detail(uid):
    import plans as planner
    import users as accounts
    from flutter_api import daily_target, lookup
    user = state().users.get(uid)
    if user is None:
        abort(404)
    value, label = accounts.bmi(user["height_cm"], user["weight_kg"])
    complete = all(user[k] for k in ("sex", "age", "height_cm", "weight_kg"))
    target = daily_target(user["sex"], user["age"], user["weight_kg"], user["height_cm"],
                          user["activity"] or "light", user["goal"] or "balanced") if complete else None
    photos = state().users.photos(uid)
    for p in photos:
        p["name"] = food_name(p["food_id"])
    weights = state().users.weights(uid)
    meta, rows = state().plans.get(uid)
    days = [planner.day_view(d, [r for r in rows if r["day"] == d], meta["kcal_target"], lookup)
            for d in range(1, planner.DAYS + 1)] if meta else []
    changes = state().plans.execute("SELECT * FROM plan_changes WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid,))
    return render_template("admin/user_detail.html", user=user, bmi=value, bmi_label=label, target=target,
                           photos=photos, weights=weights, weight_chart=weight_chart(weights), meta=meta,
                           days=days, meals=planner.MEALS, recent=changes, source_labels=SOURCE_LABELS,
                           food_name=food_name)


def weight_chart(weights, w=560, h=140, pad=18):
    """SVG polyline points + labels for the weight history (None with fewer than 2 entries)."""
    if len(weights) < 2:
        return None
    ys = [x["weight_kg"] for x in weights]
    lo, hi = min(ys) - 1, max(ys) + 1
    n = len(ys) - 1
    pts = [(pad + i * (w - 2 * pad) / n, h - pad - (y - lo) / (hi - lo) * (h - 2 * pad)) for i, y in enumerate(ys)]
    return {"w": w, "h": h, "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in pts),
            "dots": [{"x": x, "y": y, "kg": k, "ts": t["ts"]} for (x, y), k, t in zip(pts, ys, weights)],
            "change": round(ys[-1] - ys[0], 1)}


@bp.get("/users/<uid>/avatar")
def user_avatar(uid):
    from flutter_api import send_private_jpeg
    user = state().users.get(uid)
    if user is None or not user["has_avatar"]:
        abort(404)
    return send_private_jpeg(state().users.avatar_path(uid))


@bp.get("/users/<uid>/photos/<int:pid>")
def user_photo(uid, pid):
    from flutter_api import send_private_jpeg
    if not state().users.photo(uid, pid):
        abort(404)
    return send_private_jpeg(state().users.photo_path(uid, pid))


@bp.post("/users/<uid>/delete")
def delete_user(uid):
    user = state().users.get(uid)
    if user is None:
        abort(404)
    state().plans.delete(uid)
    state().users.delete(uid)
    flash(f"Deleted the account of {user['name']} ({user['email']}) with its plan and photos.")
    return redirect(url_for("admin.users_list"))
