# models/

The API loads the first model it finds here at start-up:

0. **`swin_food101/`** (used now): Swin-B fine-tuned on Food-101, from Hugging Face
   `onnx-community/swin-finetuned-food101-ONNX` (Apache-2.0). Knows **all 101 dishes** of
   `data/food101_nutrition.csv`. Accuracy: 91.4–92.1 % on the Food-101 validation set (model card);
   on our 101 Unsplash dish photos (`static/food_images`): **88 % top-1, 94 % top-3**, ~0.1 s per
   photo on a laptop CPU. Runs on onnxruntime only, so App Control on Windows does not block it.
   Files: `model_quantized.onnx` (93 MB, used) and `model.onnx` (352 MB, same accuracy on our photos,
   slower), `config.json` (labels), `preprocessor_config.json` (224 px, ImageNet mean/std).

1. **`food_model.onnx` + `labels.json`** — the ResNet50 below, converted for onnxruntime.
   Use this on Windows if App Control blocks TensorFlow ("DLL load failed ... An Application Control
   policy has blocked this file"). Make it once on Google Colab:
   1. upload `food_model.keras` and `../convert_to_onnx.py`
   2. `!pip install -U "tensorflow>=2.20" tf2onnx onnx onnxruntime`
   3. `!python convert_to_onnx.py food_model.keras food_model.onnx` (it checks both models agree)
   4. download `food_model.onnx` into this folder.
2. **`food_model.keras` + `labels.json`** — our ResNet50 trained on Kaggle
   (`notebooks/train_resnet50_11class_final.ipynb`, TF 2.20): 11 Food-101 dishes, **91.8% accuracy** on the
   Food-101 test split (2,750 images). That split was also used as validation to pick the best
   checkpoint, so the number is slightly optimistic. Both files are here (191 MB model).
   Needs TensorFlow 2.20+ (saved with Keras 3.13.2).
3. `food101_model.keras` + `labels.txt` — EfficientNetB0 on all 101 dishes (`notebooks/train_food101.ipynb`).
4. Otherwise the ViT `nateraw/food` (if `transformers` is installed), else `/api/predict` returns 503.

The 11 dishes the older ResNet50 (options 1–2) knows: apple_pie, beef_carpaccio, bibimbap, cup_cakes, foie_gras,
french_fries, garlic_bread, pizza, spaghetti_carbonara, spring_rolls, strawberry_shortcake.
Any other dish → the user picks it from the list (`/api/foods`); `GET /api/status` returns `model_classes`.

Force a model with the env var `NUTRIGO_MODEL=swin|onnx|keras|vit|none`.
The admin dashboard (`/admin`) shows which model is loaded; "Try a photo" tests it.
