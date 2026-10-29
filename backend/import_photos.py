"""Import food photos in bulk (instead of uploading them one by one in the dashboard).

    python import_photos.py                      # download the photos listed in data/food_photos.csv
    python import_photos.py --folder C:\\photos   # import <food_id>.jpg/.png/.webp files from a folder
    add --force to replace photos that already exist

data/food_photos.csv lists one free Unsplash photo for each of the 101 dishes and 50 healthier swaps
(Unsplash License: free to use, attribution appreciated, so the source page is kept). Every photo goes through the same
check and 800 px resize as a dashboard upload.
"""
import argparse
import csv
import os
import sys
import urllib.request

from images import ImageStore
from nutrition import DATA_DIR, load_alternatives, load_foods

SOURCES = os.path.join(DATA_DIR, "food_photos.csv")
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def download(url):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + "w=1000&q=85&fm=jpg",
                                 headers={"User-Agent": "NutriGo-backend/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", help="folder of <food_id>.jpg/.png/.webp files")
    ap.add_argument("--sources", default=SOURCES, help="CSV with food_id,image_url (default data/food_photos.csv)")
    ap.add_argument("--force", action="store_true", help="replace photos that already exist")
    args = ap.parse_args()

    known = set(load_foods()) | set(load_alternatives())
    images = ImageStore()
    if args.folder:
        jobs = [(os.path.splitext(f)[0], os.path.join(args.folder, f)) for f in sorted(os.listdir(args.folder))
                if f.lower().endswith(EXTENSIONS)]
    else:
        with open(args.sources, newline="", encoding="utf-8") as fh:
            jobs = [(r["food_id"], r["image_url"]) for r in csv.DictReader(fh)]

    done = skipped = failed = 0
    for food_id, src in jobs:
        if food_id not in known:
            print(f"  ? {food_id}: not a food_id in data/*.csv, skipped")
            failed += 1
            continue
        if images.find(food_id) and not args.force:
            skipped += 1
            continue
        try:
            if args.folder:
                with open(src, "rb") as fh:
                    data = fh.read()
            else:
                data = download(src)
            images.save(food_id, data)
            done += 1
            print(f"  + {food_id}")
        except Exception as e:
            failed += 1
            print(f"  ! {food_id}: {e}")
    print(f"Imported {done}, already had a photo {skipped} (use --force to replace), failed {failed}.")
    print(f"Photos are in {images.image_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
