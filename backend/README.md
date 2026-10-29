# backend/

One Flask server with two parts:

| File | URL | Who uses it |
|---|---|---|
| `flutter_api.py` | `/api/*` | the Flutter app — contract + Dart client in `../for_mobile_app/` |
| `admin_dashboard.py` | `/admin/*` | admins in a browser — usage, model check, data editing, food photos |
| `app.py` | `/` | starts both; `/` opens the dashboard, `GET /api/status` is the status JSON |

Shared code: `store.py` (nutrition tables + request log), `users.py` (app accounts), `plans.py` (7-day meal plans), `images.py` (food photos), `predictor.py` (photo model),
`recommender.py`, `nutrition.py`, `evaluate.py`. Dashboard pages are in `templates/admin/`.

## Run (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:NUTRIGO_ADMIN_PASSWORD = "choose-a-password"
python app.py
```

- Flutter API: `http://localhost:5000/api/...` (phone on the same Wi-Fi: `http://<PC IP>:5000`)
- Dashboard: `http://localhost:5000/admin` → log in with `NUTRIGO_ADMIN_PASSWORD`
  (if it is not set, a one-off password is printed when the server starts)
- Tests: `python -m pytest -q` → 33 passed

On Windows with App Control, start tools through `python -m ...` (pip, pytest) because the
`.exe` launchers in `.venv\Scripts` can be blocked.

## Admin dashboard

| Page | What it shows |
|---|---|
| Overview | API requests (24 h / total), error rate, latency, photos recognised + average and low confidence, requests per day, most photographed dishes, most requested swaps, goals chosen, per-endpoint table, model status, recommender coverage (live `evaluate.py` numbers) |
| Data | the 101 dishes and 50 swaps: search, filter, edit, add, upload a photo for each; swaps can be deleted. Saves to `data/*.csv`, the Flutter API uses the change at once. Re-running `data/build_nutrition.py` overwrites these edits. |
| Requests | last 200 API calls, filter by endpoint or errors |
| Try a photo | upload a meal photo → model guesses, nutrition, and the healthier swaps with their photos (not logged) |
| `/admin/api/stats` | the overview numbers as JSON, e.g. for a future admin screen in Flutter |

The request log is SQLite at `backend/instance/nutrigo.db` (change with `NUTRIGO_DB`). It stores
endpoint, status, latency, dish, confidence, goal and swap count — never photos or the age /
weight / height sent to `/api/target`.

## App accounts and the Users page

People sign up in the app with name, email and password (`/api/auth/register`, `/api/auth/login`).
Passwords are stored as salted hashes and login tokens only as SHA-256 hashes. The profile holds sex,
age, height, weight (every change is kept as history), activity, goal, a profile photo, and BMI and
daily calorie target are calculated from it. Meal photos a signed-in user takes in the app are kept
in their gallery, and their meal plan is tied to their account.

The dashboard's **Users** page lists everyone; click a person for their profile, weight chart, meal
photos and 7-day plan, or to delete the account. Personal files are in `backend/instance/user_media/`
(not under `static/`) and are served only to the user (token) or a logged-in admin. The `instance/`
folder holds personal data: keep it out of zips you share and don't commit it.

## 7-day meal plans

Each app user (an anonymous `user_id` the app makes) gets a plan: Day 1–7 × breakfast, lunch, dinner,
snack, on the calorie target they chose (1200–3000 kcal). Meal budgets are 25 / 35 / 30 / 10 % of
the target. Meals are picked from the 50 healthier swaps (vegetarian plans also use the lighter
vegetarian dishes) with a 0.5–2.5× portion that fits the budget, and no food twice within 3 days.

When the user chooses a swap, picks a food or uploads a photo of what they ate, that meal is replaced
(a swap is sized to the budget and never above what it replaces; a photo counts as eaten) and the
day's other planned meals are re-sized so the day stays on target. A new target re-plans the week but
keeps the user's own choices. Tested accuracy (worst day of 40 random plans): within ~8 % up to
2400 kcal, ~14 % at 3000; vegetarian within ~7 % up to 1800 kcal, ~12 % at 2400.
Plans are stored in the same SQLite file as the request log. The **Plans** page shows every plan as a
7-day grid and which swaps and photos replaced which meals.

## Food photos

Each dish and swap can have a photo. Upload it on its edit page (Data → click the name → Photo).
It is checked, resized to 800 px and saved as `backend/static/food_images/<food_id>.jpg`.
The Flutter app gets it through `image_url` in every food / swap / prediction object
(`GET /api/images/<food_id>`). Until a photo is uploaded, that URL returns a generated card with the
name and category colour. Overview shows how many swaps still need a photo.

All 101 dishes and 50 swaps have a free Unsplash photo (sources and links in `data/food_photos.csv`, Unsplash License).
Bulk import: `python import_photos.py` downloads that list again (`--force` replaces existing photos);
`python import_photos.py --folder C:\photos` imports your own `<food_id>.jpg/.png/.webp` files.

## Recognition model

`backend/models/README.md`. If TensorFlow is blocked on Windows ("An Application Control policy has
blocked this file"), convert the model once on Google Colab with `convert_to_onnx.py` and put
`food_model.onnx` in `backend/models/`; the API then runs it with onnxruntime, no TensorFlow needed.

## Settings (environment variables)

| Variable | Default |
|---|---|
| `NUTRIGO_ADMIN_PASSWORD` | random, printed at start-up |
| `NUTRIGO_SECRET_KEY` | random per start (admins are logged out on restart) |
| `NUTRIGO_MODEL` | `auto` (Swin 101 dishes) — or `swin`, `onnx`, `keras`, `vit`, `none` |
| `NUTRIGO_DB` | `backend/instance/nutrigo.db` |
| `NUTRIGO_IMAGE_DIR` | `backend/static/food_images` |
| `NUTRIGO_MEDIA_DIR` | `backend/instance/user_media` (profile + meal photos) |
| `NUTRIGO_DATA_DIR` | `data/` |
| `PORT` | `5000` |
