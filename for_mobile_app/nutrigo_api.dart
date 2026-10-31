// NutriGo API client for Flutter.
//
// Setup:  flutter pub add http
// Copy this file to lib/services/nutrigo_api.dart.
// Contract: NutriGo_API_for_Flutter.md (same folder).
//
// Example:
//   final api = NutriGoApi('https://nutrigo-tau.vercel.app');  // hosted (or http://10.0.2.2:5000 for a local PC)
//   final result = await api.predict(File(photo.path), goal: 'lose_weight');
//   Image.network(result.swaps.first.imageUrl);           // photo of the first swap
//
// Account (save api.token with flutter_secure_storage; next start: NutriGoApi(url, token: saved)):
//   final user = await api.register(name: 'Omar', email: 'omar@example.com', password: 'secret123',
//       sex: 'male', age: 21, heightCm: 178, weightKg: 80, goal: 'lose_weight');
//   // later: await api.login(email, password);  // api.token is set again
//
// Meal plan of the signed-in user ('me'):
//   var plan = await api.createPlan('me', kcalTarget: user.dailyTarget!.planKcal, goal: 'lose_weight');
//   plan.days[0].meal('lunch').food.name;                 // Day 1 lunch
//   final s = await api.mealSwaps('me', 1, 'lunch');      // swaps sized to the lunch budget
//   final day1 = await api.replaceMeal('me', 1, 'lunch', s.swaps.first.id);  // day stays on target
//   final r = await api.logMealPhoto('me', 1, 'dinner', File(photo.path));    // also saved to the gallery

import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

const nutriGoGoals = ['balanced', 'lose_weight', 'high_protein', 'low_carb', 'vegetarian'];
const nutriGoActivities = ['sedentary', 'light', 'moderate', 'active', 'very_active'];

class NutriGoException implements Exception {
  NutriGoException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  /// 503: no recognition model on the server -> open the manual food list instead.
  bool get noModel => statusCode == 503;

  @override
  String toString() => 'NutriGoException($statusCode): $message';
}

double _d(dynamic v) => (v as num?)?.toDouble() ?? 0;

/// A dish (from /api/foods) or a healthier swap. Swap-only fields are null for dishes.
class Food {
  Food.fromJson(Map<String, dynamic> j)
      : id = j['food_id'] as String,
        name = j['name'] as String,
        category = j['category'] as String? ?? '',
        serving = j['serving'] as String? ?? '',
        servingG = _d(j['serving_g']),
        kcal = _d(j['kcal']),
        proteinG = _d(j['protein_g']),
        carbsG = _d(j['carbs_g']),
        fatG = _d(j['fat_g']),
        satFatG = _d(j['sat_fat_g']),
        fibreG = _d(j['fibre_g']),
        sugarG = _d(j['sugar_g']),
        sodiumMg = _d(j['sodium_mg']),
        healthScore = (j['health_score'] as num?)?.toInt() ?? 0,
        tags = List<String>.from(j['tags'] as List? ?? const []),
        imageUrl = j['image_url'] as String? ?? '',
        hasPhoto = j['has_photo'] as bool? ?? false,
        portion = (j['portion'] as num?)?.toDouble(),
        kcalSaved = (j['kcal_saved'] as num?)?.toDouble(),
        kcalSavedPct = (j['kcal_saved_pct'] as num?)?.toInt(),
        why = List<String>.from(j['why'] as List? ?? const []);

  final String id, name, category, serving;
  final double servingG, kcal, proteinG, carbsG, fatG, satFatG, fibreG, sugarG, sodiumMg;
  final int healthScore;
  final List<String> tags;

  /// Always a usable URL: the uploaded photo, or a generated card when [hasPhoto] is false.
  final String imageUrl;
  final bool hasPhoto;

  final double? portion; // on `eaten` and on plan swaps (sized to the meal budget)
  final double? kcalSaved; // swaps only
  final int? kcalSavedPct; // swaps only
  final List<String> why; // swaps only: "-6 g saturated fat", "+16 g protein", ...
}

class Prediction {
  Prediction.fromJson(Map<String, dynamic> j)
      : id = j['food_id'] as String,
        name = j['name'] as String,
        confidence = _d(j['confidence']),
        imageUrl = j['image_url'] as String? ?? '';
  final String id, name, imageUrl;
  final double confidence; // 0-1
}

class PredictResult {
  PredictResult.fromJson(Map<String, dynamic> j)
      : photoId = (j['photo_id'] as num?)?.toInt(),
        model = j['model'] as String? ?? '',
        modelClasses = (j['model_classes'] as num?)?.toInt() ?? 0,
        predictions = (j['predictions'] as List)
            .map((p) => Prediction.fromJson(p as Map<String, dynamic>))
            .toList(),
        lowConfidence = j['low_confidence'] as bool? ?? false,
        top = j['top'] == null ? null : Food.fromJson(j['top'] as Map<String, dynamic>),
        goal = j['goal'] as String? ?? 'balanced',
        swaps = (j['swaps'] as List? ?? const [])
            .map((s) => Food.fromJson(s as Map<String, dynamic>))
            .toList();

  final String model, goal;
  final int modelClasses;

  /// Id in the user's gallery when signed in, else null.
  final int? photoId;
  final List<Prediction> predictions;

  /// true below 60 %: show a warning and let the user pick from the list.
  final bool lowConfidence;
  final Food? top;

  /// Healthier swaps (with photos) for the top guess.
  final List<Food> swaps;
}

class RecommendResult {
  RecommendResult.fromJson(Map<String, dynamic> j)
      : eaten = Food.fromJson(j['eaten'] as Map<String, dynamic>),
        goal = j['goal'] as String,
        swaps = (j['swaps'] as List)
            .map((s) => Food.fromJson(s as Map<String, dynamic>))
            .toList(),
        menuSwaps = List<Map<String, dynamic>>.from(j['menu_swaps'] as List? ?? const []),
        message = j['message'] as String?;

  final Food eaten;
  final String goal;
  final List<Food> swaps;
  final List<Map<String, dynamic>> menuSwaps;

  /// "Already a light choice..." when [swaps] is empty.
  final String? message;
}

class DailyTarget {
  DailyTarget.fromJson(Map<String, dynamic> j)
      : kcal = (j['kcal'] as num).toInt(),
        planKcal = ((j['plan_kcal'] ?? j['kcal']) as num).toInt(),
        proteinG = (j['protein_g'] as num).toInt(),
        carbsG = (j['carbs_g'] as num).toInt(),
        fatG = (j['fat_g'] as num).toInt(),
        bmr = (j['bmr'] as num).toInt(),
        tdee = (j['tdee'] as num).toInt();
  final int kcal, proteinG, carbsG, fatG, bmr, tdee;

  /// `kcal` kept inside 1200-3000: use this as kcalTarget for createPlan / updatePlan.
  final int planKcal;
}

// ---------- accounts ----------

class NutriGoUser {
  NutriGoUser.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        email = j['email'] as String,
        name = j['name'] as String,
        sex = j['sex'] as String?,
        age = (j['age'] as num?)?.toDouble(),
        heightCm = (j['height_cm'] as num?)?.toDouble(),
        weightKg = (j['weight_kg'] as num?)?.toDouble(),
        activity = j['activity'] as String?,
        goal = j['goal'] as String?,
        bmi = (j['bmi'] as num?)?.toDouble(),
        bmiLabel = j['bmi_label'] as String?,
        dailyTarget =
            j['daily_target'] == null ? null : DailyTarget.fromJson(j['daily_target'] as Map<String, dynamic>),
        avatarUrl = j['avatar_url'] as String?,
        hasPlan = j['has_plan'] as bool? ?? false;

  final String id, email, name;
  final String? sex, activity, goal, bmiLabel;
  final double? age, heightCm, weightKg, bmi;

  /// From the profile (needs sex, age, height, weight); use dailyTarget.kcal for createPlan.
  final DailyTarget? dailyTarget;

  /// Private: Image.network(avatarUrl!, headers: api.authHeaders).
  final String? avatarUrl;
  final bool hasPlan;
}

class MealPhoto {
  MealPhoto.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        foodId = j['food_id'] as String?,
        name = j['name'] as String?,
        confidence = (j['confidence'] as num?)?.toDouble(),
        day = (j['day'] as num?)?.toInt(),
        meal = j['meal'] as String?,
        taken = DateTime.fromMillisecondsSinceEpoch(((j['taken'] as num) * 1000).round()),
        url = j['url'] as String;

  final int id;
  final String? foodId, name, meal;
  final double? confidence;
  final int? day;
  final DateTime taken;
  final String url; // private: use api.authHeaders
}

// ---------- 7-day meal plan ----------

const nutriGoMeals = ['breakfast', 'lunch', 'dinner', 'snack'];

class PlanMeal {
  PlanMeal.fromJson(Map<String, dynamic> j)
      : meal = j['meal'] as String,
        source = j['source'] as String,
        portion = _d(j['portion']),
        budgetKcal = (j['budget_kcal'] as num).toInt(),
        food = Food.fromJson(j['food'] as Map<String, dynamic>);

  final String meal; // breakfast | lunch | dinner | snack
  /// plan (app's choice) | swap (user chose a swap) | manual (from the list) | photo (really eaten)
  final String source;
  final double portion;
  final int budgetKcal;

  /// Already scaled to [portion]: food.kcal is what this meal counts for.
  final Food food;
}

class PlanDay {
  PlanDay.fromJson(Map<String, dynamic> j)
      : day = (j['day'] as num).toInt(),
        targetKcal = (j['target_kcal'] as num).toInt(),
        diffKcal = (j['diff_kcal'] as num).toInt(),
        totalKcal = (j['totals']['kcal'] as num).toInt(),
        proteinG = (j['totals']['protein_g'] as num).toInt(),
        carbsG = (j['totals']['carbs_g'] as num).toInt(),
        fatG = (j['totals']['fat_g'] as num).toInt(),
        meals = (j['meals'] as List).map((m) => PlanMeal.fromJson(m as Map<String, dynamic>)).toList();

  final int day, targetKcal, diffKcal, totalKcal, proteinG, carbsG, fatG;
  final List<PlanMeal> meals;

  PlanMeal meal(String name) => meals.firstWhere((m) => m.meal == name);
}

class MealPlan {
  MealPlan.fromJson(Map<String, dynamic> j)
      : userId = j['user_id'] as String,
        goal = j['goal'] as String,
        kcalTarget = (j['kcal_target'] as num).toInt(),
        days = (j['days'] as List).map((d) => PlanDay.fromJson(d as Map<String, dynamic>)).toList();

  final String userId, goal;
  final int kcalTarget;
  final List<PlanDay> days; // Day 1 .. Day 7
}

class PlanSwaps {
  PlanSwaps.fromJson(Map<String, dynamic> j)
      : day = (j['day'] as num).toInt(),
        meal = j['meal'] as String,
        budgetKcal = (j['budget_kcal'] as num).toInt(),
        current = Food.fromJson(j['current'] as Map<String, dynamic>),
        swaps = (j['swaps'] as List).map((s) => Food.fromJson(s as Map<String, dynamic>)).toList(),
        message = j['message'] as String?;

  final int day, budgetKcal;
  final String meal;
  final Food current;
  final List<Food> swaps; // each with portion + kcal sized to the meal budget
  final String? message;
}

class PlanPhotoResult {
  PlanPhotoResult.fromJson(Map<String, dynamic> j)
      : predictions = (j['predictions'] as List)
            .map((p) => Prediction.fromJson(p as Map<String, dynamic>))
            .toList(),
        lowConfidence = j['low_confidence'] as bool? ?? false,
        day = PlanDay.fromJson(j['day'] as Map<String, dynamic>),
        swaps = (j['swaps'] as List).map((s) => Food.fromJson(s as Map<String, dynamic>)).toList();

  final List<Prediction> predictions;

  /// If true (or the guess is wrong), let the user pick the dish and call
  /// replaceMeal(..., source: 'photo').
  final bool lowConfidence;
  final PlanDay day; // updated day: the meal is the recognised dish, the rest re-sized
  final List<Food> swaps;
}

class NutriGoApi {
  NutriGoApi(this.baseUrl, {this.token, http.Client? client, this.timeout = const Duration(seconds: 30)})
      : _http = client ?? http.Client();

  /// Login token (from register / login). Save it with flutter_secure_storage and pass it here
  /// on the next start. With a token, meal photos go to the user's gallery and plan('me') works.
  String? token;

  /// Headers for private images: Image.network(photo.url, headers: api.authHeaders).
  Map<String, String> get authHeaders => _auth;
  Map<String, String> get _auth => {
        // free ngrok tunnels show a warning page instead of the API unless this header is sent
        'ngrok-skip-browser-warning': 'true',
        if (token != null) 'Authorization': 'Bearer $token',
      };
  Map<String, String> get _jsonHeaders => {'Content-Type': 'application/json', ..._auth};

  /// e.g. 'http://10.0.2.2:5000' (emulator) or 'http://192.168.1.31:5000' (phone on Wi-Fi).
  final String baseUrl;
  final Duration timeout;
  final http.Client _http;

  Uri _u(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Future<Map<String, dynamic>> status() async => _decode(await _http.get(_u('/api/status'), headers: _auth).timeout(timeout));

  /// Photo -> recognised dish, top-5 guesses and healthier swaps with photos.
  Future<PredictResult> predict(File photo, {String goal = 'balanced'}) async {
    final req = http.MultipartRequest('POST', _u('/api/predict'))
      ..headers.addAll(_auth)
      ..fields['goal'] = goal
      ..files.add(await http.MultipartFile.fromPath('image', photo.path));
    final res = await http.Response.fromStream(await _http.send(req).timeout(timeout));
    return PredictResult.fromJson(_decode(res));
  }

  Future<List<Food>> foods({String q = '', String? category}) async {
    final res = await _http
        .get(_u('/api/foods', {'q': q, if (category != null) 'category': category}), headers: _auth)
        .timeout(timeout);
    return (_decode(res)['foods'] as List).map((f) => Food.fromJson(f as Map<String, dynamic>)).toList();
  }

  Future<Food> food(String foodId) async =>
      Food.fromJson(_decode(await _http.get(_u('/api/foods/$foodId'), headers: _auth).timeout(timeout)));

  Future<RecommendResult> recommend(String foodId,
      {double portion = 1.0, String goal = 'balanced', int limit = 4}) async {
    final res = await _http
        .post(_u('/api/recommend'),
            headers: _jsonHeaders,
            body: jsonEncode({'food_id': foodId, 'portion': portion, 'goal': goal, 'limit': limit}))
        .timeout(timeout);
    return RecommendResult.fromJson(_decode(res));
  }

  Future<DailyTarget> target({
    required String sex, // 'male' | 'female'
    required num age,
    required num weightKg,
    required num heightCm,
    String activity = 'light',
    String goal = 'balanced',
  }) async {
    final res = await _http
        .post(_u('/api/target'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'sex': sex, 'age': age, 'weight_kg': weightKg, 'height_cm': heightCm,
              'activity': activity, 'goal': goal,
            }))
        .timeout(timeout);
    return DailyTarget.fromJson(_decode(res));
  }

  // ---------- 7-day meal plan ----------

  /// New 7-day plan on the user's daily kcal target (e.g. DailyTarget.kcal). Replaces an old plan.
  Future<MealPlan> createPlan(String userId, {required int kcalTarget, String goal = 'balanced'}) async {
    final res = await _http
        .post(_u('/api/plans'),
            headers: _jsonHeaders, body: jsonEncode({'user_id': userId, 'goal': goal, 'kcal_target': kcalTarget}))
        .timeout(timeout);
    return MealPlan.fromJson(_decode(res, ok: 201));
  }

  /// The user's plan, or null if they have none yet.
  Future<MealPlan?> plan(String userId) async {
    final res = await _http.get(_u('/api/plans/$userId'), headers: _auth).timeout(timeout);
    if (res.statusCode == 404) return null;
    return MealPlan.fromJson(_decode(res));
  }

  /// New target and/or goal: the whole week is re-fitted, the user's own choices stay.
  Future<MealPlan> updatePlan(String userId, {int? kcalTarget, String? goal}) async {
    final res = await _http
        .patch(_u('/api/plans/$userId'),
            headers: _jsonHeaders,
            body: jsonEncode({if (kcalTarget != null) 'kcal_target': kcalTarget, if (goal != null) 'goal': goal}))
        .timeout(timeout);
    return MealPlan.fromJson(_decode(res));
  }

  Future<void> deletePlan(String userId) async {
    _decode(await _http.delete(_u('/api/plans/$userId'), headers: _auth).timeout(timeout));
  }

  /// Healthier swaps for one meal of the plan, sized to that meal's calorie budget.
  Future<PlanSwaps> mealSwaps(String userId, int day, String meal, {int limit = 4}) async {
    final res =
        await _http.get(_u('/api/plans/$userId/$day/$meal/swaps', {'limit': '$limit'}), headers: _auth).timeout(timeout);
    return PlanSwaps.fromJson(_decode(res));
  }

  /// Put a food in a meal. source: 'swap' (chosen swap), 'manual' (from the list) or 'photo'
  /// (what they really ate). Without [portion] the server sizes swaps/manual picks to the budget.
  Future<PlanDay> replaceMeal(String userId, int day, String meal, String foodId,
      {String source = 'swap', double? portion}) async {
    final res = await _http
        .put(_u('/api/plans/$userId/$day/$meal'),
            headers: _jsonHeaders,
            body: jsonEncode({'food_id': foodId, 'source': source, if (portion != null) 'portion': portion}))
        .timeout(timeout);
    return PlanDay.fromJson(_decode(res)['day'] as Map<String, dynamic>);
  }

  /// Photo of what the user ate -> recognised and put in that meal; the day is re-sized to the target.
  Future<PlanPhotoResult> logMealPhoto(String userId, int day, String meal, File photo,
      {double portion = 1.0}) async {
    final req = http.MultipartRequest('POST', _u('/api/plans/$userId/$day/$meal/photo'))
      ..headers.addAll(_auth)
      ..fields['portion'] = '$portion'
      ..files.add(await http.MultipartFile.fromPath('image', photo.path));
    final res = await http.Response.fromStream(await _http.send(req).timeout(timeout));
    return PlanPhotoResult.fromJson(_decode(res));
  }

  // ---------- accounts ----------

  /// New account. Returns the user and keeps the login token on this client.
  Future<NutriGoUser> register({
    required String name,
    required String email,
    required String password, // at least 8 characters
    String? sex, // 'male' | 'female'
    num? age,
    num? heightCm,
    num? weightKg,
    String? activity,
    String? goal,
  }) async {
    final res = await _http
        .post(_u('/api/auth/register'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'name': name, 'email': email, 'password': password,
              if (sex != null) 'sex': sex, if (age != null) 'age': age,
              if (heightCm != null) 'height_cm': heightCm, if (weightKg != null) 'weight_kg': weightKg,
              if (activity != null) 'activity': activity, if (goal != null) 'goal': goal,
            }))
        .timeout(timeout);
    return _signedIn(_decode(res, ok: 201));
  }

  /// Throws NutriGoException(401) for a wrong email or password.
  Future<NutriGoUser> login(String email, String password) async {
    final res = await _http
        .post(_u('/api/auth/login'), headers: _jsonHeaders, body: jsonEncode({'email': email, 'password': password}))
        .timeout(timeout);
    return _signedIn(_decode(res));
  }

  Future<void> logout() async {
    await _http.post(_u('/api/auth/logout'), headers: _auth).timeout(timeout);
    token = null;
  }

  Future<NutriGoUser> me() async =>
      NutriGoUser.fromJson(_decode(await _http.get(_u('/api/me'), headers: _auth).timeout(timeout)));

  /// Change any of: name, sex, age, height_cm, weight_kg, activity, goal. Weight changes are kept as history.
  Future<NutriGoUser> updateMe(Map<String, dynamic> fields) async => NutriGoUser.fromJson(_decode(
      await _http.patch(_u('/api/me'), headers: _jsonHeaders, body: jsonEncode(fields)).timeout(timeout)));

  Future<NutriGoUser> setAvatar(File photo) async {
    final req = http.MultipartRequest('PUT', _u('/api/me/avatar'))
      ..headers.addAll(_auth)
      ..files.add(await http.MultipartFile.fromPath('image', photo.path));
    return NutriGoUser.fromJson(_decode(await http.Response.fromStream(await _http.send(req).timeout(timeout))));
  }

  /// The user's meal photos, newest first. Show with Image.network(p.url, headers: authHeaders).
  Future<List<MealPhoto>> photos() async {
    final res = await _http.get(_u('/api/me/photos'), headers: _auth).timeout(timeout);
    return (_decode(res)['photos'] as List).map((p) => MealPhoto.fromJson(p as Map<String, dynamic>)).toList();
  }

  Future<void> deletePhoto(int id) async {
    _decode(await _http.delete(_u('/api/me/photos/$id'), headers: _auth).timeout(timeout));
  }

  /// Change the password. Other devices are logged out; this client gets a new token.
  /// Throws NutriGoException(401) if [currentPassword] is wrong.
  Future<NutriGoUser> changePassword(String currentPassword, String newPassword) async {
    final res = await _http
        .post(_u('/api/me/password'),
            headers: _jsonHeaders,
            body: jsonEncode({'current_password': currentPassword, 'new_password': newPassword}))
        .timeout(timeout);
    return _signedIn(_decode(res));
  }

  /// Deletes the account, its meal plan and all its photos.
  Future<void> deleteAccount() async {
    _decode(await _http.delete(_u('/api/me'), headers: _auth).timeout(timeout));
    token = null;
  }

  NutriGoUser _signedIn(Map<String, dynamic> body) {
    token = body['token'] as String;
    return NutriGoUser.fromJson(body['user'] as Map<String, dynamic>);
  }

  Map<String, dynamic> _decode(http.Response res, {int ok = 200}) {
    Map<String, dynamic>? body;
    try {
      body = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {}
    if (res.statusCode != ok || body == null) {
      throw NutriGoException(res.statusCode, body?['error'] as String? ?? 'HTTP ${res.statusCode}');
    }
    return body;
  }
}
