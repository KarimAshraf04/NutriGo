"""44 unit tests for the recommender, the Flutter API, the meal plan and the admin dashboard.  Run:  pytest -q  (from backend/)"""
import io
import os
import shutil
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from nutrition import DATA_DIR, health_score, load_alternatives, load_foods, scale  # noqa: E402
from predictor import KerasPredictor, OnnxModel  # noqa: E402
from recommender import MAX_PER_CATEGORY, is_sweet, recommend  # noqa: E402

FOODS = load_foods()
ALTS = load_alternatives()
ADMIN_PASSWORD = "test-password"


LABELS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "labels.json")


class FakeResNet:
    """Stands in for food_model.keras (11 classes): checks the 1/255 scaling, returns 'pizza'."""
    def predict(self, x, verbose=0):
        assert x.shape == (1, 224, 224, 3) and x.max() <= 1.0
        probs = np.full((1, 11), 0.01)
        probs[0, 7] = 0.90  # index 7 = pizza in labels.json
        return probs


def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (200, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    menu = tmp_path / "fastfood.csv"
    menu.write_text(
        "restaurant,item,calories,cal_fat,total_fat,sat_fat,trans_fat,cholesterol,sodium,"
        "total_carb,fiber,sugar,protein,vit_a,vit_c,calcium,salad\n"
        "Mcdonalds,Big Mac,540,250,28,10,1,80,950,46,3,9,25,6,2,25,Other\n"
        "Mcdonalds,Grilled Chicken Burger Wrap,380,120,13,3,0,60,700,38,3,5,28,6,2,10,Other\n",
        encoding="utf-8")
    app = create_app(predictor=KerasPredictor("food_model.keras", LABELS_JSON, model=FakeResNet()),
                     fastfood_path=str(menu), db_path=str(tmp_path / "log.db"), admin_password=ADMIN_PASSWORD,
                     image_dir=str(tmp_path / "img"), media_dir=str(tmp_path / "media"))
    app.testing = True
    return app.test_client()


@pytest.fixture
def admin(tmp_path):
    """Logged-in dashboard client on a copy of the data, so edits never touch data/*.csv."""
    data = tmp_path / "data"
    data.mkdir()
    for name in ("food101_nutrition.csv", "healthy_alternatives.csv"):
        shutil.copy(os.path.join(DATA_DIR, name), data / name)
    app = create_app(predictor=KerasPredictor("food_model.keras", LABELS_JSON, model=FakeResNet()),
                     data_dir=str(data), db_path=str(tmp_path / "log.db"), admin_password=ADMIN_PASSWORD,
                     image_dir=str(tmp_path / "img"), media_dir=str(tmp_path / "media"))
    app.testing = True
    c = app.test_client()
    assert c.post("/admin/login", data={"password": ADMIN_PASSWORD}).status_code == 302
    with c.session_transaction() as s:
        c.csrf = s["csrf"]
    c.app, c.data_dir = app, data
    return c


def test_1_health_score_matches_slide_example():
    assert health_score(FOODS["hamburger"]) == 38


def test_2_dataset_sizes():
    assert len(FOODS) == 101 and len(ALTS) == 50


def test_3_portion_scales_nutrients():
    half = scale(FOODS["pizza"], 0.5)
    assert half["kcal"] == 300 and half["sodium_mg"] == 650


def test_4_swaps_are_lighter_and_at_least_as_healthy():
    for food in FOODS.values():
        eaten, swaps = recommend(food, ALTS)
        for s in swaps:
            assert s["kcal"] < eaten["kcal"]
            assert s["health_score"] >= eaten["health_score"]


def test_5_sweet_stays_sweet_and_max_two_per_category():
    for food in FOODS.values():
        eaten, swaps = recommend(food, ALTS)
        cats = [s["category"] for s in swaps]
        assert all(cats.count(c) <= MAX_PER_CATEGORY for c in cats)
        assert all(("sweet" in s["tags"]) == is_sweet(food) for s in swaps)


def test_6_vegetarian_goal_only_returns_vegetarian_swaps():
    _, swaps = recommend(FOODS["lasagna"], ALTS, goal="vegetarian")
    assert swaps and all("vegetarian" in s["tags"] for s in swaps)


def test_7_api_foods_and_recommend(client):
    assert client.get("/api/foods").get_json()["count"] == 101
    r = client.post("/api/recommend", json={"food_id": "hamburger", "portion": 1, "goal": "balanced"})
    data = r.get_json()
    assert r.status_code == 200 and data["eaten"]["kcal"] == 650 and data["swaps"]
    assert any(m["name"] == "Grilled Chicken Burger Wrap" for m in data["menu_swaps"])
    assert client.post("/api/recommend", json={"food_id": "hamburger", "portion": 5}).status_code == 400


def test_8_api_predict_with_resnet_labels_json(client):
    r = client.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "meal.jpg")},
                    content_type="multipart/form-data")
    data = r.get_json()
    assert r.status_code == 200 and len(data["predictions"]) == 5 and data["model_classes"] == 11
    assert data["predictions"][0]["food_id"] == "pizza" and data["low_confidence"] is False
    assert data["top"]["kcal"] == 600


def test_9_api_target_lose_weight_is_500_below_tdee(client):
    r = client.post("/api/target", json={"sex": "male", "age": 21, "weight_kg": 80,
                                         "height_cm": 178, "activity": "light", "goal": "lose_weight"})
    data = r.get_json()
    assert r.status_code == 200 and data["kcal"] == data["tdee"] - 500


def test_10_api_rejects_bad_inputs(client):
    assert client.post("/api/recommend", json={"food_id": "pizza", "limit": 0}).status_code == 400
    assert client.post("/api/recommend", json={"food_id": "pizza", "limit": 50}).status_code == 400
    base = {"sex": "male", "age": 21, "weight_kg": 80, "height_cm": 178, "activity": "light"}
    assert client.post("/api/target", json={**base, "sex": "x"}).status_code == 400
    assert client.post("/api/target", json={**base, "goal": "bulk"}).status_code == 400
    assert client.post("/api/target", json={**base, "weight_kg": -80}).status_code == 400


def test_11_api_predict_rejects_non_image(client):
    r = client.post("/api/predict", data={"image": (io.BytesIO(b"not an image"), "meal.jpg")},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and "could not read image" in r.get_json()["error"]


def test_12_admin_needs_login(client):
    r = client.get("/admin/")
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]
    assert client.get("/admin/api/stats").status_code == 401
    assert client.post("/admin/login", data={"password": "wrong"}).status_code == 200  # form again


def test_13_admin_stats_count_flutter_calls(admin):
    admin.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "meal.jpg")},
               content_type="multipart/form-data")
    admin.post("/api/recommend", json={"food_id": "hamburger", "goal": "high_protein"})
    admin.post("/api/recommend", json={"food_id": "nope"})
    s = admin.get("/admin/api/stats").get_json()
    assert s["requests"]["total"] == 3 and s["requests"]["errors"] == 1
    assert s["top_predicted"][0]["food_id"] == "pizza" and s["predictions"]["total"] == 1
    assert s["goals"] == [{"goal": "high_protein", "n": 1}]
    for page in ("/admin/", "/admin/foods", "/admin/foods?table=alternatives", "/admin/requests",
                 "/admin/foods/foods/pizza", "/admin/try"):
        assert admin.get(page).status_code == 200, page


def test_14_admin_edits_swap_and_api_uses_it(admin):
    form = {"csrf": admin.csrf, "food_id": "test_salad", "name": "Test Salad", "category": "Salad",
            "serving": "1 bowl", "serving_g": 200, "kcal": 150, "protein_g": 10, "carbs_g": 12, "fat_g": 7,
            "sat_fat_g": 1, "fibre_g": 5, "sugar_g": 4, "sodium_mg": 200, "tags": "fresh, green"}
    assert admin.post("/admin/foods/alternatives/new", data=form).status_code == 302
    store = admin.app.extensions["nutrigo"].store
    assert store.alternatives["test_salad"]["kcal"] == 150
    assert "test_salad,Test Salad,Salad" in (admin.data_dir / "healthy_alternatives.csv").read_text("utf-8")
    assert admin.post("/admin/foods/alternatives/new", data=dict(form, csrf="bad")).status_code == 400
    assert admin.post("/admin/foods/alternatives/test_salad/delete", data={"csrf": admin.csrf}).status_code == 302
    assert "test_salad" not in store.alternatives and len(store.alternatives) == 50
    assert admin.post("/admin/foods/foods/pizza/delete", data={"csrf": admin.csrf}).status_code == 400


def test_15_admin_rejects_bad_food_form(admin):
    r = admin.post("/admin/foods/alternatives/new", data={"csrf": admin.csrf, "food_id": "Bad ID!", "kcal": "-5"})
    assert r.status_code == 200 and b"already exists" not in r.data and b"must be a number" in r.data
    assert len(admin.app.extensions["nutrigo"].store.alternatives) == 50


def test_16_onnx_model_runs_through_predictor(tmp_path):
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper
    w = np.zeros((3, 11), dtype=np.float32)
    w[0, 7] = 10.0  # red images -> index 7 = pizza
    graph = helper.make_graph(
        [helper.make_node("ReduceMean", ["x"], ["m"], axes=[1, 2], keepdims=0),
         helper.make_node("MatMul", ["m", "w"], ["logits"]),
         helper.make_node("Softmax", ["logits"], ["probs"], axis=1)],
        "tiny", [helper.make_tensor_value_info("x", TensorProto.FLOAT, [None, 224, 224, 3])],
        [helper.make_tensor_value_info("probs", TensorProto.FLOAT, [None, 11])],
        [helper.make_tensor("w", TensorProto.FLOAT, w.shape, w.flatten())])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=8)
    path = str(tmp_path / "food_model.onnx")
    onnx.save(model, path)
    p = KerasPredictor(path, LABELS_JSON, model=OnnxModel(path), kind="onnx")
    top = p.predict(jpeg_bytes(), k=3)
    assert p.name == "onnx:food_model (11 classes)" and top[0][0] == "pizza" and len(top) == 3


def test_17_every_food_has_an_image_url(client):
    foods = client.get("/api/foods?q=pizza").get_json()["foods"]
    assert foods[0]["image_url"].startswith("http://localhost/api/images/pizza") and foods[0]["has_photo"] is False
    r = client.get("/api/images/pizza")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data[1:4] == b"PNG"
    assert client.get("/api/images/greek_yogurt_parfait").status_code == 200  # swaps have images too
    assert client.get("/api/images/..%2Fapp").status_code == 404
    s = client.application.extensions["nutrigo"].log.execute("SELECT COUNT(*) FROM requests WHERE endpoint='food_image'")
    assert s[0][0] == 0  # image downloads are not logged


def test_18_predict_returns_swaps_with_photos(client):
    r = client.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "meal.jpg"), "goal": "lose_weight"},
                    content_type="multipart/form-data")
    data = r.get_json()
    assert r.status_code == 200 and data["goal"] == "lose_weight" and data["swaps"]
    assert all(s["image_url"].startswith("http://localhost/api/images/") and s["kcal"] < 600 for s in data["swaps"])
    assert data["top"]["image_url"] and data["predictions"][0]["image_url"]
    bad = client.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "m.jpg"), "goal": "x"},
                      content_type="multipart/form-data")
    assert bad.status_code == 400


def test_19_admin_uploads_swap_photo(admin):
    fid = "greek_yogurt_parfait"
    row = admin.app.extensions["nutrigo"].store.alternatives[fid]
    form = {k: (",".join(v) if k == "tags" else v) for k, v in row.items() if k != "health_score"}
    form["csrf"] = admin.csrf
    bad = admin.post(f"/admin/foods/alternatives/{fid}", data=dict(form, photo=(io.BytesIO(b"nope"), "x.jpg")),
                     content_type="multipart/form-data")
    assert bad.status_code == 200 and b"not a readable image" in bad.data
    big = io.BytesIO()
    Image.new("RGB", (2000, 1000), (90, 160, 60)).save(big, "PNG")
    big.seek(0)
    r = admin.post(f"/admin/foods/alternatives/{fid}", data=dict(form, photo=(big, "parfait.png")),
                   content_type="multipart/form-data")
    assert r.status_code == 302
    img = admin.get(f"/api/images/{fid}")
    assert img.mimetype == "image/jpeg" and max(Image.open(io.BytesIO(img.data)).size) == 800
    assert admin.app.extensions["nutrigo"].images.find(fid)
    assert admin.get("/admin/api/stats").get_json()["catalog"]["swap_photos"] == 1
    admin.post(f"/admin/foods/alternatives/{fid}", data=dict(form, remove_photo="1"), content_type="multipart/form-data")
    assert admin.get(f"/api/images/{fid}").mimetype == "image/png"


def test_20_home_opens_dashboard_and_status_is_json(client):
    r = client.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/")
    s = client.get("/api/status").get_json()
    assert s["app"] == "NutriGo API" and s["model_ready"] is True and s["foods"] == 101


USER = "test-device-01"


def make_plan(client, kcal=1800, goal="lose_weight"):
    r = client.post("/api/plans", json={"user_id": USER, "goal": goal, "kcal_target": kcal})
    assert r.status_code == 201
    return r.get_json()


def test_21_plan_has_7_days_of_4_meals_near_the_target(client):
    p = make_plan(client)
    assert len(p["days"]) == 7 and all([m["meal"] for m in d["meals"]] == ["breakfast", "lunch", "dinner", "snack"]
                                         for d in p["days"])
    for d in p["days"]:
        assert abs(d["totals"]["kcal"] - 1800) <= 0.1 * 1800
        assert len({m["food"]["food_id"] for m in d["meals"]}) == 4  # no food twice a day
        assert all(m["food"]["image_url"] and m["source"] == "plan" for m in d["meals"])
    assert client.get(f"/api/plans/{USER}").get_json()["kcal_target"] == 1800
    veg = make_plan(client, goal="vegetarian")
    assert all("vegetarian" in m["food"]["tags"] for d in veg["days"] for m in d["meals"])


def test_22_chosen_swap_replaces_the_meal_and_keeps_the_day_on_target(client):
    make_plan(client)
    s = client.get(f"/api/plans/{USER}/2/dinner/swaps").get_json()
    p = client.get(f"/api/plans/{USER}").get_json()["days"][1]
    others = {m["food"]["food_id"] for m in p["meals"] if m["meal"] != "dinner"}
    for sw in s["swaps"]:
        assert sw["kcal"] <= s["current"]["kcal"] + 0.5 and sw["food_id"] not in others
    if s["swaps"]:
        pick = s["swaps"][0]
        day = client.put(f"/api/plans/{USER}/2/dinner", json={"food_id": pick["food_id"], "source": "swap"}).get_json()["day"]
        dinner = [m for m in day["meals"] if m["meal"] == "dinner"][0]
        assert dinner["food"]["food_id"] == pick["food_id"] and dinner["source"] == "swap"
        assert dinner["portion"] == pick["portion"]
        assert client.get(f"/api/plans/{USER}").get_json()["days"][1]["meals"][2]["food"]["food_id"] == pick["food_id"]


def test_23_photo_of_a_meal_is_logged_and_the_rest_of_the_day_resized(client):
    make_plan(client, kcal=2000, goal="balanced")
    r = client.post(f"/api/plans/{USER}/1/lunch/photo",
                    data={"image": (io.BytesIO(jpeg_bytes()), "meal.jpg"), "portion": "1"},
                    content_type="multipart/form-data")
    data = r.get_json()
    assert r.status_code == 200 and data["predictions"][0]["food_id"] == "pizza"
    lunch = data["day"]["meals"][1]
    assert lunch["food"]["food_id"] == "pizza" and lunch["source"] == "photo" and lunch["food"]["kcal"] == 600
    assert abs(data["day"]["totals"]["kcal"] - 2000) <= 0.1 * 2000
    assert all(s["kcal"] <= 600 for s in data["swaps"])


def test_24_new_target_refits_the_week_and_keeps_user_choices(client):
    make_plan(client, kcal=1800)
    client.put(f"/api/plans/{USER}/1/lunch", json={"food_id": "pizza", "source": "photo"})
    p = client.patch(f"/api/plans/{USER}", json={"kcal_target": 2400}).get_json()
    assert p["kcal_target"] == 2400
    assert all(abs(d["totals"]["kcal"] - 2400) <= 0.12 * 2400 for d in p["days"])
    assert p["days"][0]["meals"][1]["food"]["food_id"] == "pizza" and p["days"][0]["meals"][1]["source"] == "photo"


def test_25_plan_rejects_bad_input(client):
    assert client.post("/api/plans", json={"user_id": "x", "kcal_target": 1800}).status_code == 400
    assert client.post("/api/plans", json={"user_id": USER, "kcal_target": 500}).status_code == 400
    assert client.get("/api/plans/nobody-123").status_code == 404
    make_plan(client)
    assert client.put(f"/api/plans/{USER}/8/lunch", json={"food_id": "pizza"}).status_code == 400
    assert client.put(f"/api/plans/{USER}/1/brunch", json={"food_id": "pizza"}).status_code == 400
    assert client.put(f"/api/plans/{USER}/1/lunch", json={"food_id": "nope"}).status_code == 400
    assert client.put(f"/api/plans/{USER}/1/lunch", json={"food_id": "pizza", "source": "plan"}).status_code == 400
    assert client.delete(f"/api/plans/{USER}").status_code == 200
    assert client.get(f"/api/plans/{USER}").status_code == 404


def test_26_admin_sees_plans_and_changes(admin):
    admin.post("/api/plans", json={"user_id": USER, "goal": "balanced", "kcal_target": 2000})
    admin.put(f"/api/plans/{USER}/3/dinner", json={"food_id": "grilled_fish_tacos", "source": "swap"})
    page = admin.get("/admin/plans")
    assert page.status_code == 200 and USER.encode() in page.data and b"Grilled Fish Tacos" in page.data
    detail = admin.get(f"/admin/plans/{USER}")
    assert detail.status_code == 200 and b"Day 7" in detail.data and b"Swap chosen" in detail.data
    assert admin.get("/admin/api/stats").get_json()["plans"] == {"users": 1, "swaps_chosen": 1, "photo_meals": 0}


def test_27_hugging_face_onnx_predictor_101_classes(tmp_path):
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    import json
    from onnx import TensorProto, helper
    from predictor import HFOnnxPredictor
    labels = sorted(FOODS)  # 101 Food-101 ids, like the real config.json
    w = np.zeros((3, 101), dtype=np.float32)
    w[0, labels.index("hamburger")] = 20.0  # reddish image -> hamburger
    graph = helper.make_graph(
        [helper.make_node("ReduceMean", ["pixel_values"], ["m"], axes=[2, 3], keepdims=0),
         helper.make_node("MatMul", ["m", "w"], ["logits"])],
        "tiny", [helper.make_tensor_value_info("pixel_values", TensorProto.FLOAT, [None, 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [None, 101])],
        [helper.make_tensor("w", TensorProto.FLOAT, w.shape, w.flatten())])
    onnx.save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=8),
              str(tmp_path / "model_quantized.onnx"))
    (tmp_path / "config.json").write_text(json.dumps({"id2label": {str(i): l for i, l in enumerate(labels)}}))
    (tmp_path / "preprocessor_config.json").write_text(json.dumps(
        {"do_rescale": True, "rescale_factor": 1 / 255, "image_mean": [0.485, 0.456, 0.406],
         "image_std": [0.229, 0.224, 0.225], "size": {"height": 224, "width": 224}}))
    p = HFOnnxPredictor(str(tmp_path))
    top = p.predict(jpeg_bytes(), k=5)
    assert p.name.endswith("(101 classes)") and len(p.labels) == 101
    assert top[0][0] == "hamburger" and abs(sum(c for _, c in top) - 1) < 0.05


OMAR = {"name": "Omar", "email": "omar@example.com", "password": "secret123", "sex": "male", "age": 21,
        "height_cm": 178, "weight_kg": 80, "activity": "light", "goal": "lose_weight"}


def sign_up(c, **extra):
    r = c.post("/api/auth/register", json=dict(OMAR, **extra))
    assert r.status_code == 201, r.get_json()
    data = r.get_json()
    return {"Authorization": "Bearer " + data["token"]}, data["user"]


def test_28_register_login_and_profile(client):
    h, user = sign_up(client)
    assert user["bmi"] == 25.2 and user["bmi_label"] == "Overweight" and user["daily_target"]["kcal"] > 1500
    assert "password_hash" not in user and OMAR["password"] not in str(user) and "scrypt" not in str(user)
    assert user["has_password"] is True and user["google"] is False
    assert client.post("/api/auth/register", json=dict(OMAR, email="OMAR@example.com")).status_code == 409
    assert client.post("/api/auth/register", json=dict(OMAR, email="x@y.co", password="short")).status_code == 400
    assert client.post("/api/auth/register", json=dict(OMAR, email="not-an-email")).status_code == 400
    assert client.post("/api/auth/login", json={"email": OMAR["email"], "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "Omar@Example.com", "password": OMAR["password"]})
    assert r.status_code == 200 and r.get_json()["token"]
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    me = client.patch("/api/me", json={"weight_kg": 76, "goal": "high_protein"}, headers=h).get_json()
    assert me["weight_kg"] == 76 and me["goal"] == "high_protein" and me["bmi"] == 24.0
    assert client.patch("/api/me", json={"height_cm": 20}, headers=h).status_code == 400


def test_29_passwords_are_hashed_and_logout_ends_the_token(client):
    h, user = sign_up(client)
    row = client.application.extensions["nutrigo"].users.get(user["id"])
    assert OMAR["password"] not in row["password_hash"] and len(row["password_hash"]) > 40
    tokens = client.application.extensions["nutrigo"].users.execute("SELECT token_hash FROM user_tokens")
    assert all(h["Authorization"][7:] != t["token_hash"] for t in tokens)  # only hashes stored
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/me", headers=h).status_code == 401


def test_30_avatar_and_meal_photos_are_private(client):
    h, user = sign_up(client)
    r = client.put("/api/me/avatar", data={"image": (io.BytesIO(jpeg_bytes()), "me.jpg")}, headers=h,
                   content_type="multipart/form-data")
    assert r.get_json()["avatar_url"].endswith("/api/me/avatar")
    assert client.get("/api/me/avatar", headers=h).mimetype == "image/jpeg"
    assert client.get("/api/me/avatar").status_code == 401
    r = client.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "m.jpg")}, headers=h,
                    content_type="multipart/form-data")
    pid = r.get_json()["photo_id"]
    assert pid and client.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "m.jpg")},
                               content_type="multipart/form-data").get_json()["photo_id"] is None
    gallery = client.get("/api/me/photos", headers=h).get_json()
    assert gallery["count"] == 1 and gallery["photos"][0]["food_id"] == "pizza"
    assert client.get(f"/api/me/photos/{pid}", headers=h).mimetype == "image/jpeg"
    h2, _ = sign_up(client, email="aya@example.com", name="Aya")
    assert client.get(f"/api/me/photos/{pid}", headers=h2).status_code == 404  # not hers
    assert client.delete(f"/api/me/photos/{pid}", headers=h).status_code == 200
    assert client.get("/api/me/photos", headers=h).get_json()["count"] == 0


def test_31_plan_belongs_to_the_signed_in_user(client):
    h, user = sign_up(client)
    r = client.post("/api/plans", json={"goal": "lose_weight", "kcal_target": 1800}, headers=h)
    assert r.status_code == 201 and r.get_json()["user_id"] == user["id"]
    assert client.get("/api/plans/me", headers=h).status_code == 200
    assert client.get("/api/plans/me").status_code == 401
    assert client.get(f"/api/plans/{user['id']}").status_code == 401
    h2, _ = sign_up(client, email="aya@example.com", name="Aya")
    assert client.get(f"/api/plans/{user['id']}", headers=h2).status_code == 403
    assert client.post("/api/plans", json={"user_id": user["id"], "kcal_target": 1800}, headers=h2).status_code == 403
    r = client.post("/api/plans/me/1/lunch/photo", data={"image": (io.BytesIO(jpeg_bytes()), "m.jpg")}, headers=h,
                    content_type="multipart/form-data")
    assert r.status_code == 200
    photos = client.get("/api/me/photos", headers=h).get_json()["photos"]
    assert photos[0]["day"] == 1 and photos[0]["meal"] == "lunch" and photos[0]["source"] == "plan"


def test_32_deleting_the_account_removes_everything(client, tmp_path):
    h, user = sign_up(client)
    client.put("/api/me/avatar", data={"image": (io.BytesIO(jpeg_bytes()), "me.jpg")}, headers=h,
               content_type="multipart/form-data")
    client.post("/api/plans", json={"kcal_target": 1800}, headers=h)
    assert os.listdir(tmp_path / "media")
    assert client.delete("/api/me", headers=h).status_code == 200
    st = client.application.extensions["nutrigo"]
    assert st.users.get(user["id"]) is None and st.plans.get(user["id"])[0] is None
    assert os.listdir(tmp_path / "media") == []
    assert client.post("/api/auth/login", json={"email": OMAR["email"], "password": OMAR["password"]}).status_code == 401


def test_33_admin_sees_users_profile_photos_and_plan(admin):
    h, user = sign_up(admin)
    admin.put("/api/me/avatar", data={"image": (io.BytesIO(jpeg_bytes()), "me.jpg")}, headers=h,
              content_type="multipart/form-data")
    admin.patch("/api/me", json={"weight_kg": 78}, headers=h)
    admin.post("/api/predict", data={"image": (io.BytesIO(jpeg_bytes()), "m.jpg")}, headers=h,
               content_type="multipart/form-data")
    admin.post("/api/plans", json={"kcal_target": 1800}, headers=h)
    page = admin.get("/admin/users")
    assert page.status_code == 200 and b"Omar" in page.data and b"omar@example.com" in page.data
    detail = admin.get(f"/admin/users/{user['id']}")
    assert detail.status_code == 200
    for text in (b"178", b"78.0", b"Weight history", b"Meal photos (1)", b"Day 7", b"Pizza"):
        assert text in detail.data, text
    assert admin.get(f"/admin/users/{user['id']}/avatar").mimetype == "image/jpeg"
    pid = admin.application.extensions["nutrigo"].users.photos(user["id"])[0]["id"]
    assert admin.get(f"/admin/users/{user['id']}/photos/{pid}").mimetype == "image/jpeg"
    assert admin.get(f"/admin/plans/{user['id']}").status_code == 200
    assert admin.get("/admin/api/stats").get_json()["accounts"]["total"] == 1
    assert admin.post(f"/admin/users/{user['id']}/delete", data={"csrf": admin.csrf}).status_code == 302
    assert admin.get(f"/admin/users/{user['id']}").status_code == 404


def test_34_change_password_logs_out_other_devices(client):
    h, user = sign_up(client)
    other = {"Authorization": "Bearer " + client.post("/api/auth/login", json={
        "email": OMAR["email"], "password": OMAR["password"]}).get_json()["token"]}
    assert client.post("/api/me/password", json={"current_password": "wrong-one", "new_password": "newsecret1"},
                       headers=h).status_code == 401
    assert client.post("/api/me/password", json={"current_password": OMAR["password"], "new_password": "short"},
                       headers=h).status_code == 400
    r = client.post("/api/me/password", json={"current_password": OMAR["password"], "new_password": "newsecret1"},
                    headers=h)
    assert r.status_code == 200
    assert client.get("/api/me", headers=other).status_code == 401  # old devices logged out
    assert client.get("/api/me", headers={"Authorization": "Bearer " + r.get_json()["token"]}).status_code == 200
    assert client.post("/api/auth/login", json={"email": OMAR["email"], "password": OMAR["password"]}).status_code == 401
    assert client.post("/api/auth/login", json={"email": OMAR["email"], "password": "newsecret1"}).status_code == 200


def test_35_links_use_https_behind_a_tunnel(client):
    r = client.get("/api/foods?q=pizza", headers={"X-Forwarded-Proto": "https", "Host": "abc.ngrok-free.app"})
    assert r.get_json()["foods"][0]["image_url"].startswith("https://abc.ngrok-free.app/api/images/pizza")


def test_36_swap_used_in_a_plan_cannot_be_deleted(admin):
    plan = admin.post("/api/plans", json={"user_id": USER, "kcal_target": 2000}).get_json()
    alts = admin.app.extensions["nutrigo"].store.alternatives
    used = next(m["food"]["food_id"] for d in plan["days"] for m in d["meals"] if m["food"]["food_id"] in alts)
    r = admin.post(f"/admin/foods/alternatives/{used}/delete", data={"csrf": admin.csrf}, follow_redirects=True)
    assert r.status_code == 200 and b"cannot be deleted" in r.data and used in alts
    assert admin.get(f"/api/plans/{USER}").status_code == 200


def test_37_daily_target_stays_sensible_at_the_extremes(client):
    from flutter_api import daily_target
    heavy = daily_target("female", 60, 120, 150, "sedentary", "lose_weight")
    assert heavy["fat_g"] * 9 >= 0.19 * heavy["kcal"] and heavy["protein_g"] < 120
    assert abs(heavy["protein_g"] * 4 + heavy["carbs_g"] * 4 + heavy["fat_g"] * 9 - heavy["kcal"]) <= 15
    small = daily_target("male", 80, 45, 150, "sedentary", "lose_weight")
    assert small["kcal"] <= small["tdee"]  # the 1500 kcal floor never goes above maintenance
    big = daily_target("male", 22, 110, 190, "very_active", "balanced")
    assert big["kcal"] > 3000 and big["plan_kcal"] == 3000
    assert client.post("/api/plans", json={"user_id": USER, "kcal_target": big["plan_kcal"]}).status_code == 201


def test_38_repeated_wrong_passwords_are_throttled(client):
    sign_up(client)
    for _ in range(10):
        assert client.post("/api/auth/login", json={"email": OMAR["email"], "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": OMAR["email"], "password": OMAR["password"]})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    for _ in range(10):
        client.post("/admin/login", data={"password": "wrong"})
    assert client.post("/admin/login", data={"password": ADMIN_PASSWORD}).status_code == 429


def test_39_no_fixed_admin_password(tmp_path, monkeypatch):
    monkeypatch.delenv("NUTRIGO_ADMIN_PASSWORD", raising=False)
    app = create_app(predictor=KerasPredictor("food_model.keras", LABELS_JSON, model=FakeResNet()),
                     db_path=str(tmp_path / "log.db"), image_dir=str(tmp_path / "img"), media_dir=str(tmp_path / "m"))
    assert app.extensions["nutrigo"].admin_password not in ("", "123456789")
    assert app.test_client().post("/admin/login", data={"password": "123456789"}).status_code == 200


def test_40_dashboard_shows_sign_ins_and_who_needs_a_plan(admin):
    h, user = sign_up(admin)
    row = f'/admin/users/{user["id"]}" style="color: inherit;"'  # the user's row in the table, not the history
    page = admin.get("/admin/users").get_data(as_text=True)
    assert "Signed up" in page and "Signed in" in page
    assert row in admin.get("/admin/users?show=no_plan").get_data(as_text=True)
    admin.post("/api/plans", json={"kcal_target": 1800}, headers=h)
    assert row not in admin.get("/admin/users?show=no_plan").get_data(as_text=True)
    assert row in admin.get("/admin/users?show=signed_in").get_data(as_text=True)
    assert admin.post("/api/auth/logout", headers=h).status_code == 200
    assert "Logged out" in admin.get("/admin/users").get_data(as_text=True)
    assert row not in admin.get("/admin/users?show=signed_in").get_data(as_text=True)


def google_app(tmp_path, monkeypatch, claims_by_token):
    """App with Google sign-in on; Google's check is replaced by a lookup table of fake tokens."""
    import users
    monkeypatch.setattr(users, "verify_google_id_token",
                        lambda token, ids: claims_by_token.get(token) if "web-client" in ids else None)
    app = create_app(predictor=KerasPredictor("food_model.keras", LABELS_JSON, model=FakeResNet()),
                     db_path=str(tmp_path / "log.db"), admin_password=ADMIN_PASSWORD, image_dir=str(tmp_path / "img"),
                     media_dir=str(tmp_path / "media"), google_client_ids={"web-client"})
    return app.test_client()


def test_41_google_sign_up_then_sign_in(tmp_path, monkeypatch):
    sara = {"sub": "g-123", "email": "sara@gmail.com", "name": "Sara Ali", "email_verified": "true"}
    c = google_app(tmp_path, monkeypatch, {"good": sara})
    r = c.post("/api/auth/google", json={"id_token": "good"})
    assert r.status_code == 201
    user = r.get_json()["user"]
    assert user["name"] == "Sara Ali" and user["email"] == "sara@gmail.com" and user["google"] and not user["has_password"]
    h = {"Authorization": "Bearer " + r.get_json()["token"]}
    assert c.get("/api/me", headers=h).status_code == 200
    r2 = c.post("/api/auth/google", json={"id_token": "good"})
    assert r2.status_code == 200 and r2.get_json()["user"]["id"] == user["id"]  # same account, not a new one
    assert c.post("/api/auth/google", json={"id_token": "forged"}).status_code == 401
    assert c.post("/api/auth/google", json={}).status_code == 400
    # no password yet: email login fails, but the user can set a first password without a current one
    assert c.post("/api/auth/login", json={"email": "sara@gmail.com", "password": "anything1"}).status_code == 401
    assert c.post("/api/me/password", json={"new_password": "newsecret1"}, headers=h).status_code == 200
    assert c.post("/api/auth/login", json={"email": "sara@gmail.com", "password": "newsecret1"}).status_code == 200


def test_42_google_links_an_existing_email_account(tmp_path, monkeypatch):
    c = google_app(tmp_path, monkeypatch, {
        "omar": {"sub": "g-omar", "email": OMAR["email"], "name": "Omar G", "email_verified": "true"},
        "other": {"sub": "g-other", "email": OMAR["email"], "name": "Omar 2", "email_verified": "true"}})
    _, user = sign_up(c)
    r = c.post("/api/auth/google", json={"id_token": "omar"})
    assert r.status_code == 200 and r.get_json()["user"]["id"] == user["id"] and r.get_json()["user"]["google"]
    assert c.post("/api/auth/google", json={"id_token": "other"}).status_code == 409
    assert c.post("/api/auth/login", json={"email": OMAR["email"], "password": OMAR["password"]}).status_code == 200


def test_43_google_sign_in_off_without_client_id(client):
    assert client.post("/api/auth/google", json={"id_token": "x"}).status_code == 503


def test_44_google_token_checks(monkeypatch):
    import io as _io
    import json as _json
    import urllib.error

    import users

    def fake_urlopen(claims):
        class Resp(_io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda url, timeout: Resp(_json.dumps(claims).encode())
    good = {"aud": "web-client", "iss": "https://accounts.google.com", "sub": "1", "email": "a@b.co",
            "email_verified": "true"}
    monkeypatch.setattr(users.urllib.request, "urlopen", fake_urlopen(good))
    assert users.verify_google_id_token("t", {"web-client"})["sub"] == "1"
    assert users.verify_google_id_token("t", {"someone-else"}) is None  # token made for another app
    for bad in ({"iss": "evil.com"}, {"email_verified": "false"}):
        monkeypatch.setattr(users.urllib.request, "urlopen", fake_urlopen(dict(good, **bad)))
        assert users.verify_google_id_token("t", {"web-client"}) is None

    def rejected(url, timeout):
        raise urllib.error.HTTPError(url, 400, "invalid_token", {}, None)
    monkeypatch.setattr(users.urllib.request, "urlopen", rejected)
    assert users.verify_google_id_token("t", {"web-client"}) is None
