"""Student ID sign-in, the meal log and goal weight.  Run:  pytest -q  (from backend/)"""
from test_nutrigo import client  # noqa: F401  (pytest fixture)


def test_student_id_first_time_creates_account_then_logs_in(client):  # noqa: F811
    r = client.post("/api/auth/student/check", json={"student_id": "20231234"})
    assert r.status_code == 200 and r.get_json()["exists"] is False
    r = client.post("/api/auth/student", json={"student_id": "20231234", "password": "short"})
    assert r.status_code == 400
    r = client.post("/api/auth/student", json={"student_id": "20231234", "password": "secret123", "name": "Mona"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["created"] is True and body["user"]["student_id"] == "20231234" and body["user"]["name"] == "Mona"
    assert client.post("/api/auth/student/check", json={"student_id": "20231234"}).get_json()["exists"] is True
    r = client.post("/api/auth/student", json={"student_id": "20231234", "password": "wrongpass1"})
    assert r.status_code == 401
    r = client.post("/api/auth/student", json={"student_id": "20231234", "password": "secret123"})
    assert r.status_code == 200 and r.get_json()["created"] is False
    token = r.get_json()["token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).get_json()
    assert me["student_id"] == "20231234"
    assert client.post("/api/auth/student", json={"student_id": "a b"}).status_code == 400


def test_meal_log(client):  # noqa: F811
    assert client.get("/api/me/meals").status_code == 401
    token = client.post("/api/auth/register", json={"name": "A", "email": "a@b.co", "password": "secret123"}) \
        .get_json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/me/meals", headers=h).get_json()["count"] == 0
    bad = client.post("/api/me/meals", headers=h, json={"date": "2026-11-01", "time": "9", "slot": "Lunch",
                                                         "name": "x", "kcal": 1})
    assert bad.status_code == 400
    r = client.post("/api/me/meals", headers=h, json={
        "date": "2026-11-01", "time": "13:05", "slot": "lunch", "name": "Grilled chicken", "kcal": 350.4,
        "food_id": "grilled_chicken", "saved_kcal": 300, "swapped_from": "Hamburger", "protein_g": 40})
    assert r.status_code == 201
    m = r.get_json()
    assert m["slot"] == "Lunch" and m["kcal"] == 350 and m["saved_kcal"] == 300
    client.post("/api/me/meals", headers=h, json={"date": "2026-10-20", "time": "08:00", "slot": "Breakfast",
                                                   "name": "Ful", "kcal": 400})
    all_ = client.get("/api/me/meals", headers=h).get_json()
    assert all_["count"] == 2 and all_["meals"][0]["name"] == "Grilled chicken"
    assert client.get("/api/me/meals?since=2026-10-25", headers=h).get_json()["count"] == 1
    assert client.delete(f"/api/me/meals/{m['id']}", headers=h).status_code == 200
    assert client.get("/api/me/meals", headers=h).get_json()["count"] == 1
    assert client.delete("/api/me", headers=h).status_code == 200


def test_goal_and_start_weight(client):  # noqa: F811
    r = client.post("/api/auth/register", json={"name": "A", "email": "w@b.co", "password": "secret123",
                                                 "weight_kg": 90, "goal_weight_kg": 80})
    h = {"Authorization": f"Bearer {r.get_json()['token']}"}
    u = r.get_json()["user"]
    assert u["goal_weight_kg"] == 80 and u["start_weight_kg"] == 90
    u = client.patch("/api/me", headers=h, json={"weight_kg": 87}).get_json()
    assert u["weight_kg"] == 87 and u["start_weight_kg"] == 90
    assert client.patch("/api/me", headers=h, json={"goal_weight_kg": 10}).status_code == 400
