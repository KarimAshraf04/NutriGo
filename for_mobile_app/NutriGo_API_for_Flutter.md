# NutriGo API — for the Flutter app

Two files to use in the app:
- this document (what each endpoint takes and returns)
- `nutrigo_api.dart` — a ready client: copy it to `lib/services/nutrigo_api.dart`, then `flutter pub add http`

## Connect

The backend is hosted at **`https://nutrigo-tau.vercel.app`** — use that as `baseUrl` from any phone,
emulator or web build. Check it first: `GET https://nutrigo-tau.vercel.app/api/status` → `"model_ready": true`.

Hosted on Vercel (free demo hosting), so:
- **Saved data can reset**: accounts, plans and meal photos may disappear between requests or after the server
  has been idle. If `GET /api/me` answers `401` with a token that worked before, send the user to log in /
  sign up again; if `GET /api/plans/me` answers `404`, create the plan again. Recognition, foods, swaps and
  targets need no saved data and always work.
- **Photos must be under 4.5 MB** (Vercel rejects bigger uploads with `413`). Shrink them when picking:
  `ImagePicker().pickImage(source: ImageSource.camera, maxWidth: 1600, imageQuality: 85)`.
- **The first call after an idle period takes a few seconds** while the model loads; show a spinner and keep the
  client's 30 s timeout.

To run the backend on your own PC instead (`python app.py` in `backend/`, port 5000):

| Where the app runs | `baseUrl` |
|---|---|
| Android emulator | `http://10.0.2.2:5000` |
| iOS simulator, Windows desktop, Flutter web | `http://localhost:5000` |
| Real phone (same Wi-Fi as the PC) | `http://<PC IP>:5000` — find the IP with `ipconfig` (IPv4 Address) |
| Any phone, anywhere (ngrok tunnel) | the `https://….ngrok-free.app` address ngrok prints (changes on every ngrok start unless you claim a free static domain) |

Android: always add `<uses-permission android:name="android.permission.INTERNET"/>` to `AndroidManifest.xml`
(release builds have no internet without it). Only for a local PC, because it is plain HTTP, also add
`android:usesCleartextTraffic="true"` on `<application>`; the Vercel address is https and needs nothing else.
On the PC, allow Python through Windows Firewall when asked, or a real phone cannot connect.

With ngrok, every request must carry the header `ngrok-skip-browser-warning: true`, otherwise ngrok
answers with an HTML warning page instead of JSON (`nutrigo_api.dart` sends it). ngrok URLs are https,
so no cleartext setting is needed for them.

Check the connection first: `GET /api/status` → `"model_ready": true`.

## What the app must do (so the admin dashboard sees every user)

The admin dashboard (`/admin/users`) lists every account, who is **signed in** or **logged out**, a history of
sign-ups, logins and logouts, who **needs a plan**, and each person's profile, weight, photos and 7-day plan.
It only knows what the app sends, so the app must use accounts — not anonymous ids:

1. **Start-up.** `api = NutriGoApi(baseUrl, token: <token saved in flutter_secure_storage>)`. If there is a saved
   token, call `api.me()`: success → go to Home; `401` → delete the saved token and show Login.
2. **Sign up** (`api.register(...)`) with name, email, password — or **Continue with Google**
   (`api.loginWithGoogle(idToken)`, see *Sign in with Google*) — and ask for sex, age, height, weight, activity
   and goal in the same form or right after (`api.updateMe({...})`). Without them there is no `daily_target`.
   → dashboard: *Signed up*, *Signed in*.
3. **Log in** (`api.login(email, password)`) → save `api.token` in `flutter_secure_storage`.
   → dashboard: *Logged in*, *Signed in*. Handle `401` (wrong password) and `429` (too many tries: wait).
4. **Plan.** After sign-up / login call `api.plan('me')`. If it is `null` (no plan yet) show a
   "Create my plan" button → `api.createPlan('me', kcalTarget: user.dailyTarget!.planKcal, goal: user.goal ?? 'balanced')`.
   Until then the user shows under **Need a plan** in the dashboard. When the user edits weight, activity or
   goal, call `api.updatePlan('me', kcalTarget: newUser.dailyTarget!.planKcal, goal: newUser.goal)`.
5. **Every request after login carries the token** (`nutrigo_api.dart` adds it). Use `'me'` as the plan
   user id, never a device id, so the plan belongs to the account. Each signed-in call updates *Last seen*.
6. **Meal photos.** Use `api.predict(photo)` / `api.logMealPhoto('me', day, meal, photo)` while signed in, so the
   photos land in the user's gallery and the dashboard.
7. **Log out button** → `api.logout()`, then delete the saved token. → dashboard: *Logged out*.
   (Just closing the app does not log out; tokens last 30 days.)
8. **Privacy text.** Tell users that the NutriGo team can see their profile, photos and plan.

## Photos (`image_url`)

Every food, prediction and swap object has:
- `image_url` — full URL of its photo, e.g. `http://10.0.2.2:5000/api/images/greek_yogurt_parfait?v=1793272900`.
  Show it with `Image.network(food['image_url'])`. Admins upload real photos in the dashboard; until
  then the URL returns a generated card (category colour + name), so it never breaks.
- `has_photo` — `true` when it is a real uploaded photo.

The `?v=` part changes when an admin replaces a photo, so the app does not keep a stale cached one.

## Endpoints

### `POST /api/predict` — snap a meal → dish + healthier swaps with photos
multipart/form-data: field `image` (jpg/png/webp, max 10 MB), optional field `goal`
(`balanced` default · `lose_weight` · `high_protein` · `low_carb` · `vegetarian`).
```json
{
  "model": "onnx:swin_food101 (101 classes)",
  "model_classes": 101,
  "predictions": [{"food_id": "pizza", "name": "Pizza", "confidence": 0.91,
                   "image_url": "http://…/api/images/pizza?v=0", "has_photo": false}, … 5 items],
  "low_confidence": false,
  "top": { food object of the first guess },
  "goal": "balanced",
  "swaps": [ up to 4 swap objects for the top guess (1× portion), see /api/recommend ]
}
```
- Show the top-3 guesses with confidence bars. If `low_confidence` (< 60 %) show a warning and the
  manual list (`/api/foods`).
- `swaps` lets the result screen show swap cards with photos straight away. When the user changes the
  dish, portion or goal, call `/api/recommend`.
- The model knows all 101 dishes of `/api/foods` (Swin Food-101: about 88 % right first guess and
  94 % within the top 3 on real photos). Dishes outside the list are mapped to the closest one, so
  always let the user correct it from the top-3 or the list.
- Errors: `503` no model loaded → open the manual picker · `400` not a readable image or bad `goal` ·
  `413` photo over 10 MB · `500` the model failed.

### `GET /api/foods?q=piz&category=Fast food` — manual picker
`{"count": 101, "foods": [ food, … ]}` sorted by name. Both parameters are optional.

Food object:
```json
{"food_id": "pizza", "name": "Pizza", "category": "Fast food", "serving": "2 slices", "serving_g": 220,
 "kcal": 600, "protein_g": 26, "carbs_g": 70, "fat_g": 24, "sat_fat_g": 11, "fibre_g": 4, "sugar_g": 7,
 "sodium_mg": 1300, "health_score": 42, "tags": ["bread", "cheesy", "…"],
 "image_url": "http://…/api/images/pizza?v=0", "has_photo": false}
```
`health_score` is 0–100, higher is healthier.

### `GET /api/foods/<food_id>` — one food
The food object, or `404`.

### `POST /api/recommend` — adjust portion / goal → swaps
```json
{"food_id": "pizza", "portion": 1.0, "goal": "balanced", "limit": 4}
```
`portion` 0.5–2.0 (slider) · `limit` 1–10 · `goal` as above (chips).
```json
{
  "eaten": { food object scaled to the portion, + "portion" },
  "goal": "balanced",
  "swaps": [{ food fields…, "image_url": "…", "has_photo": true,
              "kcal_saved": 240, "kcal_saved_pct": 40, "similarity": 0.61, "rank_score": 0.712,
              "why": ["-6 g saturated fat", "-580 mg sodium", "Similar: baked, bread, cheesy"] }],
  "menu_swaps": [{"restaurant": "Mcdonalds", "name": "…", "kcal": 380, "kcal_saved": 270}],
  "message": null
}
```
If `swaps` is empty, show `message` ("Already a light choice…"). `menu_swaps` is empty unless the
Kaggle fast-food menu is installed on the server. Call it again on every slider / chip change
(debounce ~250 ms) so the numbers update live.

### `POST /api/target` — daily calorie ring
```json
{"sex": "male", "age": 21, "weight_kg": 80, "height_cm": 178, "activity": "light", "goal": "lose_weight"}
```
→ `{"kcal": 1992, "plan_kcal": 1992, "protein_g": 127, "carbs_g": 249, "fat_g": 54, "bmr": 1812, "tdee": 2492, "goal": "lose_weight"}`

`plan_kcal` is `kcal` kept inside 1200–3000: send it as `kcal_target` to `POST /api/plans` (very active, heavy
users can get a `kcal` above 3000, which the plan endpoints reject). Protein is per kg of a healthy weight
(BMI 25 at most) and fat is at least 20 % of the kcal.

`activity`: `sedentary | light | moderate | active | very_active` · `sex`: `male | female` ·
`goal` as above · `age` 10–100, `weight_kg` 25–300, `height_cm` 100–250 (otherwise `400`).
This endpoint only calculates and stores nothing; for signed-in users the profile (`/api/me`) already has `daily_target`.

## 7-day meal plan

Every user has one plan: **Day 1 – Day 7 × breakfast, lunch, dinner, snack**, built on the calorie
target the user chose. Each meal has a calorie budget (target × 25 % breakfast, 35 % lunch, 30 % dinner,
10 % snack). When the user swaps a meal or uploads a photo of what they ate, that meal is replaced and
the other meals of that day that the app planned get new portions, so the **day total stays on the
user's target**.

`user_id`: for a signed-in user use **`me`** (e.g. `GET /api/plans/me`) and send the token
(see *Accounts* below); only that user can open their plan (`401` without token, `403` for someone
else's plan). `POST /api/plans` without `user_id` uses the signed-in user. Without accounts you can
still use a random id per install (6–64 letters, digits, `-` or `_`).

| Endpoint | What it does |
|---|---|
| `POST /api/plans` `{user_id, goal, kcal_target}` | builds a new plan (replaces any old one) → plan, status `201` |
| `GET /api/plans/<user_id>` | the plan, or `404` if there is none yet |
| `PATCH /api/plans/<user_id>` `{kcal_target?, goal?}` | new target or goal: planned meals are picked again, the user's own choices stay and are re-sized |
| `DELETE /api/plans/<user_id>` | deletes the plan |
| `GET /api/plans/<user_id>/<day>/<meal>/swaps?limit=4` | healthier swaps for that meal, already sized to its budget |
| `PUT /api/plans/<user_id>/<day>/<meal>` `{food_id, source, portion?}` | replace the meal → the updated day (`portion` 0.5–2.5) |
| `POST /api/plans/<user_id>/<day>/<meal>/photo` multipart `image` (+ `portion`) | recognise what was eaten, put it in that meal → day + swaps |

`day` is `1`–`7`; `meal` is `breakfast | lunch | dinner | snack`. Get `kcal_target` from
`POST /api/target` (its `plan_kcal`), or let the user type it; it must be 1200–3000.
Plan portions go from 0.5× to 2.5× (e.g. 1.5 bowls), so the day can reach the target with light foods.

### Plan object
```json
{
  "user_id": "3f1c…", "goal": "lose_weight", "kcal_target": 1800,
  "meals_per_day": ["breakfast", "lunch", "dinner", "snack"],
  "meal_share": {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.3, "snack": 0.1},
  "days": [ day, … 7 ],
  "week": {"kcal": 12700, "target_kcal": 12600}
}
```
Day object (also returned by PUT and photo):
```json
{
  "day": 1, "target_kcal": 1800, "diff_kcal": -42,
  "totals": {"kcal": 1758, "protein_g": 98, "carbs_g": 190, "fat_g": 60},
  "meals": [
    {"meal": "breakfast", "source": "plan", "portion": 2.0, "budget_kcal": 450,
     "food": { food object scaled to the portion: kcal 400, …, "image_url", "has_photo" }},
    {"meal": "lunch", "source": "photo", "portion": 1.0, "budget_kcal": 630, "food": { … pizza, 600 kcal }},
    …
  ]
}
```
`source`: `plan` (the app's choice, re-sized when the day changes) · `swap` (the user chose a swap) ·
`manual` (picked from the list) · `photo` (what they really ate). Show `food.kcal` (already × portion)
and `totals.kcal / target_kcal` as the day ring.

### Swapping a meal
1. `GET /api/plans/<user_id>/3/dinner/swaps` →
   `{"day": 3, "meal": "dinner", "budget_kcal": 540, "current": { food }, "swaps": [ swap, … ], "message": null}`.
   Each swap has `portion` and `kcal` already sized to the meal budget (never more than the current meal)
   plus `kcal_saved`, `why`, `image_url`. Swaps never repeat a food that is already in that day.
2. When the user taps one: `PUT /api/plans/<user_id>/3/dinner` with `{"food_id": "<swap food_id>", "source": "swap"}`.
   Leave out `portion` and the server sizes it to the budget. The answer is the updated day.

### Logging a meal by photo
`POST /api/plans/<user_id>/1/lunch/photo` with the photo in `image` (and `portion` if they ate half / double):
```json
{"predictions": [ top-5, like /api/predict ], "low_confidence": false,
 "day": { the updated day: lunch = the recognised dish, other planned meals re-sized },
 "swaps": [ healthier swaps for next time, sized to the lunch budget ]}
```
If the guess is wrong (or `low_confidence`), let the user pick the right dish and send
`PUT …/1/lunch` with `{"food_id": "<right dish>", "source": "photo"}` (portion 1× unless you send one).

### `GET /api/status`
```json
{"app": "NutriGo API", "model": "onnx:swin_food101 (101 classes)", "model_ready": true,
 "model_classes": ["apple_pie", "…"], "foods": 101, "alternatives": 50, "fastfood_items": 0,
 "goals": ["balanced", "high_protein", "lose_weight", "low_carb", "vegetarian"]}
```

### `GET /api/images/<food_id>`
The photo (JPEG) or the generated card (PNG). You normally just use `image_url`.

## Accounts (sign up / log in)

Email + password accounts. After register or login, send the token on **every** request:
`Authorization: Bearer <token>` (`nutrigo_api.dart` does this for you once `api.token` is set).
Tokens last 30 days; keep it with `flutter_secure_storage`, not plain shared preferences.

| Endpoint | What it does |
|---|---|
| `POST /api/auth/register` `{name, email, password, sex?, age?, height_cm?, weight_kg?, activity?, goal?}` | new account → `{token, user}`, status `201`; `409` if the email exists; password ≥ 8 characters |
| `POST /api/auth/login` `{email, password}` | → `{token, user}`; `401` "wrong email or password"; after 10 wrong tries in 15 min `429` with `Retry-After` (seconds) |
| `POST /api/auth/google` `{id_token}` | sign in **or** sign up with Google (see below) → `{token, user}`; `201` for a new account, `200` for an existing one; `401` bad token; `503` Google not set up on the server |
| `POST /api/auth/logout` | ends this token (shown as *Logged out* in the dashboard) |
| `POST /api/me/password` `{current_password, new_password}` | new password → `{token, user}`; every other device is logged out; `401` if the current password is wrong |
| `GET /api/me` | the user (below) |
| `PATCH /api/me` `{name?, sex?, age?, height_cm?, weight_kg?, activity?, goal?}` | update the profile → user; every new weight is kept as history |
| `PUT /api/me/avatar` multipart `image` | profile photo → user |
| `GET /api/me/avatar` | the profile photo (JPEG, needs the token) |
| `GET /api/me/photos` | the user's meal photos: `{"count", "photos": [{id, food_id, name, confidence, day, meal, source, taken, url}]}` |
| `GET` / `DELETE /api/me/photos/<id>` | one photo (JPEG) / delete it |
| `DELETE /api/me` | deletes the account, its plan and all its photos |

User object:
```json
{"id": "239abcef…", "email": "omar@example.com", "name": "Omar", "sex": "male", "age": 21,
 "height_cm": 178, "weight_kg": 78, "activity": "light", "goal": "lose_weight",
 "bmi": 24.6, "bmi_label": "Healthy",
 "daily_target": {"kcal": 1965, "plan_kcal": 1965, "protein_g": 125, "carbs_g": 246, "fat_g": 54, "bmr": 1792, "tdee": 2465},
 "avatar_url": "http://…/api/me/avatar", "has_plan": true, "created": 1793277000.5}
```
`google` is `true` for accounts that sign in with Google; `has_password` is `false` for a Google account
that never set a password (then `POST /api/me/password` with only `new_password` sets the first one, so
email + password login also works).

`daily_target` is null until sex, age, height and weight are filled in; use its `plan_kcal` for
`POST /api/plans`. Ranges: `age` 10–100, `height_cm` 100–250, `weight_kg` 25–300.

**Meal photos** of a signed-in user are kept in their gallery: `/api/predict` (its answer has
`photo_id`) and `POST /api/plans/me/<day>/<meal>/photo`. Profile and meal photos are private: show
them with `Image.network(url, headers: api.authHeaders)`. The admins can see users' profiles, photos
and plans in the dashboard, so tell users this in the app's privacy text.

## Sign in with Google

The app signs the user in with Google, then sends Google's **ID token** to the server. The server asks Google
whether the token is genuine and made for our app, then logs the user in. The first time it creates the account
(name and email from Google); if an account with that email already exists (made with email + password), the
Google sign-in is linked to it. It shows in the dashboard like any other sign-up / login, marked *Google*.

**1. Google Cloud (once, by the project owner)** — https://console.cloud.google.com
1. Create a project (or pick one) → **APIs & Services → OAuth consent screen**: app name *NutriGo*,
   support email, *External*; add testers' Gmail addresses while it is in *Testing*.
2. **Credentials → Create credentials → OAuth client ID**, three times:
   - **Web application** → its client id is the `serverClientId` in Flutter **and** the server's
     `NUTRIGO_GOOGLE_CLIENT_IDS`. (No redirect URIs needed.)
   - **Android** → package name from `android/app/build.gradle` (`applicationId`) and the SHA-1 from
     `cd android && ./gradlew signingReport` (debug key now; add the release / Play signing SHA-1 later).
   - **iOS** (if you ship iOS) → the bundle id.
3. Give the server the Web client id (from the `NutriGo` folder), then redeploy:
   `vercel env add NUTRIGO_GOOGLE_CLIENT_IDS production` → paste `xxxx.apps.googleusercontent.com`.
   Until that is set, `/api/auth/google` answers `503`.

**2. Flutter** — `flutter pub add google_sign_in` (version 7):
```dart
import 'package:google_sign_in/google_sign_in.dart';

const webClientId = 'xxxx.apps.googleusercontent.com'; // the *Web* client id, not the Android one

Future<NutriGoUser> signInWithGoogle(NutriGoApi api) async {
  await GoogleSignIn.instance.initialize(serverClientId: webClientId); // once, e.g. at start-up
  final account = await GoogleSignIn.instance.authenticate();          // Google's account picker
  final idToken = account.authentication.idToken;
  if (idToken == null) throw Exception('Google gave no ID token: check serverClientId');
  final user = await api.loginWithGoogle(idToken);  // api.token is set; save it like a normal login
  return user;
}
```
- iOS also needs the iOS client id: `initialize(clientId: '<iOS client id>', serverClientId: webClientId)`
  and the reversed client id as a URL scheme in `ios/Runner/Info.plist` (see the google_sign_in README).
- After the first Google sign-in the profile has no sex / age / height / weight: send the user to the
  profile form (`api.updateMe`) before the plan, exactly like after `register`.
- Log out: `api.logout()` **and** `GoogleSignIn.instance.signOut()`, so the next sign-in shows the account picker.
- `401` from `/api/auth/google` usually means the token was made for another client id: `serverClientId`
  must be the Web client id that is in `NUTRIGO_GOOGLE_CLIENT_IDS`.

## Errors

Every error is JSON `{"error": "message"}` with status `400`, `401` (sign in), `403`, `404`, `409`, `413`, `429`, `500`, `502` or `503`.
`nutrigo_api.dart` turns them into a `NutriGoException` (`statusCode` + `message`).

## Admin dashboard (not for the app)

`https://nutrigo-tau.vercel.app/admin` (or `http://<PC>:5000/admin`) — for the team: users, who is signed in,
sign-in history, who needs a plan, profiles, usage numbers, editing the food data, uploading the swap photos,
testing a photo. Admins log in with the password set on the server.
