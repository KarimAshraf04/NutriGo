"""Vercel entry point: the whole NutriGo Flask app (Flutter API under /api, dashboard under /admin).

Vercel's disk is read-only except /tmp, and /tmp is per instance and wiped when it goes cold, so
this is a demo host: accounts, plans, meal photos, the request log and admin edits do not last.
The nutrition CSVs and food photos are copied to /tmp so admin edits work until the instance stops.
Set NUTRIGO_ADMIN_PASSWORD and NUTRIGO_SECRET_KEY in the Vercel project, or the dashboard is unusable
(each instance would make its own random password and session key).
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(tempfile.gettempdir(), "nutrigo")  # /tmp/nutrigo on Vercel

for name, src in (("data", os.path.join(ROOT, "data")),
                  ("food_images", os.path.join(ROOT, "backend", "static", "food_images"))):
    dst = os.path.join(TMP, name)
    if not os.path.isdir(dst):
        shutil.copytree(src, dst)
os.environ.setdefault("NUTRIGO_DATA_DIR", os.path.join(TMP, "data"))
os.environ.setdefault("NUTRIGO_IMAGE_DIR", os.path.join(TMP, "food_images"))
os.environ.setdefault("NUTRIGO_DB", os.path.join(TMP, "nutrigo.db"))
os.environ.setdefault("NUTRIGO_MEDIA_DIR", os.path.join(TMP, "user_media"))

sys.path.insert(0, os.path.join(ROOT, "backend"))
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from app import create_app  # noqa: E402

app = create_app()
# Vercel's edge sets X-Forwarded-For to the caller, so login throttling counts per phone, not per proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
