# NutriGo — Snap a meal, see its calories, get a healthier swap

Human–Machine Interaction course project · Larana, Inc.
Team: Karim Ashraf · Aya Fawzy · Mohamed Tarek — Supervisor: Dr. Waleed Hamdy / Eng. Asmaa Elsayed

## How it fits together

```
Flutter app  ──JSON/HTTP──►  backend/flutter_api.py   (/api/*)
                               ├─ /api/predict    → recognition model (Swin Food-101 ONNX, 101 dishes; older 11-dish ResNet50 as fallback)
                               ├─ /api/recommend  → recommender (health score + similarity + goal)
                               ├─ /api/foods      → nutrition tables (data/*.csv)
                               ├─ /api/auth, /api/me → accounts: profile, photo, meal-photo gallery
                               ├─ /api/target     → daily kcal / macro target
                               └─ /api/plans      → 7-day meal plan on that target; swaps and photos replace meals
Admin browser ────────────►  backend/admin_dashboard.py  (/admin)
                               app users and their profiles · usage stats · edit data · food photos · meal plans · try a photo
Both run in one server: backend/app.py
Offline: Kaggle Food-101 → notebooks/train_resnet50_11class_final.ipynb (ResNet50, 11 classes) → backend/models/food_model.keras + labels.json
```

## Folder map

| Folder | What's inside |
|---|---|
| `data/` | `food101_nutrition.csv` (101 dishes), `healthy_alternatives.csv` (50 swaps), `build_nutrition.py`; put Kaggle `fastfood.csv` here |
| `notebooks/` | `eda_week2.ipynb` (EDA), `train_resnet50_11class_final.ipynb` (the shipped model, 91.8%), `train_resnet50_11class.ipynb` (earlier run, 92.0%), `train_food101.ipynb` (EfficientNetB0, all 101 classes) |
| `backend/` | `flutter_api.py` (API for the app), `admin_dashboard.py` (admin web dashboard), recommender, predictor, `evaluate.py`, 35 unit tests — see `backend/README.md` |
| `for_mobile_app/` | **share this with the Flutter developer**: `NutriGo_API_for_Flutter.md` + `nutrigo_api.dart` |
| `calorie_model/` | calorie-band classifier for fast-food items (not used by the API yet) |
| `reports/` | EDA figures, `recommender_eval.csv` |

## Quick start (backend)

Windows PowerShell (full details in `backend/README.md`):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q                             # 35 tests
python evaluate.py                              # recommender numbers for slide 11
$env:NUTRIGO_ADMIN_PASSWORD = "123456789"
python app.py                                   # http://localhost:5000 opens the admin dashboard
```

Flutter: Android emulator → `http://10.0.2.2:5000`; real phone → `http://<your-PC-IP>:5000` (same Wi-Fi).
Full API contract and a ready Dart client: `for_mobile_app/`.

## 7-week plan

| Week | Phase | Deliverable | Status |
|---|---|---|---|
| 1 | Proposal & presentation | Slides | ✅ |
| 2 | Data collection & exploration | Nutrition tables + EDA | ✅ tables + notebook (add fastfood.csv) |
| 3 | Food recognition model | Trained model + accuracy | ✅ Swin Food-101 (101 dishes, 88% top-1 / 94% top-3 on our photos); own ResNet50: 11 dishes, 91.8% |
| 4 | Recommender & backend API | Flask API + unit tests | ✅ 4 endpoints + admin dashboard + food photos + 7-day meal plans, 35 tests passing |
| 5 | Interface (HMI) design | Working app | ✅ Flutter app (yours) → connect to API |
| 6 | Testing & usability study | SUS score + fixes list | ⏳ to do |
| 7 | Final app, report & demo | Final delivery | ⏳ to do |

## Current numbers

- Category averages and **450 vs 294 kcal (35% lighter)** match slide 5.
- Recommender (`python backend/evaluate.py`, balanced goal): **94/101** foods get a healthier swap,
  top swap saves **−233 kcal (−47%)** on average, **+19** health-score points.
  The 7 foods without a swap are already light (≤ 220 kcal): miso soup, edamame, sashimi, oysters,
  ceviche, beef carpaccio, seaweed salad — the API returns a "already a light choice" message.
