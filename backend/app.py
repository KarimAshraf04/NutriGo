"""NutriGo backend (Flask): one server, two parts.

  admin_dashboard.py  /admin/*  web dashboard for admins: usage, model, data and photos
  flutter_api.py      /api/*    JSON API for the Flutter app (for_mobile_app/NutriGo_API_for_Flutter.md)

Run:  python app.py      (listens on 0.0.0.0:5000; http://localhost:5000 opens the dashboard)
Set NUTRIGO_ADMIN_PASSWORD before starting; otherwise a one-off password is printed.
"""
import os
import secrets
from types import SimpleNamespace

from flask import Flask, jsonify, redirect, url_for

import admin_dashboard
import flutter_api
from images import IMAGE_DIR, ImageStore
from nutrition import DATA_DIR
from plans import PlanStore
from predictor import load_predictor
from store import DataStore, RequestLog
from users import UserStore

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.environ.get("NUTRIGO_DB", os.path.join(HERE, "instance", "nutrigo.db"))
DEFAULT_MEDIA = os.environ.get("NUTRIGO_MEDIA_DIR", os.path.join(HERE, "instance", "user_media"))
MAX_UPLOAD_MB = 10


def create_app(predictor=None, data_dir=DATA_DIR, fastfood_path=None, db_path=None, admin_password=None,
               image_dir=IMAGE_DIR, media_dir=None):
    app = Flask(__name__)
    # behind ngrok (or any HTTPS proxy) build image / avatar links with the https scheme the phone used
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    app.secret_key = os.environ.get("NUTRIGO_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    try:
        from flask_cors import CORS  # needed only when the Flutter app runs on the web
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    except ImportError:
        pass

    password = admin_password or os.environ.get("NUTRIGO_ADMIN_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(9)
        print(f"[admin] NUTRIGO_ADMIN_PASSWORD is not set; dashboard password for this run: {password}")

    db_path = db_path or DEFAULT_DB
    app.extensions["nutrigo"] = SimpleNamespace(
        store=DataStore(data_dir, fastfood_path), images=ImageStore(image_dir),
        model=predictor if predictor is not None else load_predictor(),
        log=RequestLog(db_path), plans=PlanStore(db_path), users=UserStore(db_path, media_dir or DEFAULT_MEDIA),
        admin_password=password)

    app.register_blueprint(flutter_api.bp)
    app.register_blueprint(admin_dashboard.bp)

    @app.get("/")
    def index():
        return redirect(url_for("admin.overview"))

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": f"upload is larger than {MAX_UPLOAD_MB} MB"}), 413

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[NutriGo] admin dashboard: http://localhost:{port}/admin   Flutter API: http://<this PC's IP>:{port}/api")
    create_app().run(host="0.0.0.0", port=port, debug=False)
