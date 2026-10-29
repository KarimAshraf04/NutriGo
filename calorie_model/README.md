# calorie_model/

Gradient-boosting classifier (scikit-learn pipeline, `calorie_model.joblib`) that puts a Kaggle
*Fastfood Nutrition* menu item into a calorie band from its other nutrients.

- Classes: Low (< 350 kcal) · Medium (350–600) · High (≥ 600) — see `labels.json`
- Features: restaurant, total_fat, sat_fat, trans_fat, cholesterol, sodium, total_carb, fiber, sugar, protein
- Best params: learning_rate 0.05, max_depth 2, n_estimators 200

Not used by the API yet, and the notebook that trained it is not in the project.
Load with `joblib.load("calorie_model.joblib")` (needs scikit-learn).
