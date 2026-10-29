# data/

| File | Rows | Source |
|---|---|---|
| `food101_nutrition.csv` | 101 | built by us (USDA-style averages per serving) — one row per Food-101 class |
| `healthy_alternatives.csv` | 50 | built by us — the swap catalog |
| `build_nutrition.py` | — | regenerates both CSVs |
| `food_photos.csv` | 151 | free Unsplash photo per dish and swap: image URL, source page, license (used by `backend/import_photos.py`) |
| `fastfood.csv` | 515 | **download** from Kaggle: https://www.kaggle.com/datasets/ulrikthygepedersen/fastfood-nutrition (optional; enables real menu swaps) |

Food-101 images (101,000) stay on Kaggle: https://www.kaggle.com/datasets/dansbecker/food-101
