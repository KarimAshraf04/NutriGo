"""App accounts: email + password or Google sign-in, profile, profile photo, meal-photo gallery, weight history.

Passwords are stored as salted hashes (werkzeug scrypt/pbkdf2), never in plain text. Google accounts
have no password (empty hash, so password login fails) until the user sets one. Login gives a
random token; only its SHA-256 is stored, so a copy of the database cannot be used to sign in.
Profile and meal photos are personal data: they live in backend/instance/user_media/<user_id>/
(not under static/), and are served only to their owner (token) or to a logged-in admin.
Deleting an account removes the profile, tokens, photos, weight history and meal plan.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from werkzeug.security import check_password_hash, generate_password_hash

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
MIN_PASSWORD = 8
TOKEN_DAYS = 30
PROFILE_FIELDS = ("name", "sex", "age", "height_cm", "weight_kg", "activity", "goal")
LIMITS = {"age": (10, 100), "height_cm": (100, 250), "weight_kg": (25, 300)}
PHOTO_SIDE = 800
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_id_token(id_token, client_ids):
    """Claims (sub, email, name, ...) of a Google ID token from the app's Google Sign-In, or None.

    Google's tokeninfo endpoint checks the signature and expiry (no extra package needed); here we
    check it was made for one of our OAuth client ids, by Google, for a verified email.
    Raises OSError when Google cannot be reached."""
    url = GOOGLE_TOKENINFO + "?" + urllib.parse.urlencode({"id_token": id_token})
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            claims = json.load(resp)
    except urllib.error.HTTPError:  # 400: invalid or expired token
        return None
    if claims.get("aud") not in client_ids or claims.get("iss") not in GOOGLE_ISSUERS:
        return None
    if str(claims.get("email_verified")).lower() != "true" or not claims.get("sub") or not claims.get("email"):
        return None
    return claims


def bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None, None
    value = weight_kg / (height_cm / 100) ** 2
    label = ("Underweight" if value < 18.5 else "Healthy" if value < 25 else
             "Overweight" if value < 30 else "Obese")
    return round(value, 1), label


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _save_jpeg(data, path, side=PHOTO_SIDE):
    """Check it is an image, fix rotation, resize, drop EXIF (GPS etc.) and save as JPEG."""
    from PIL import Image, ImageOps
    Image.open(io.BytesIO(data)).verify()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((side, side))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path + ".tmp", "JPEG", quality=85)
    os.replace(path + ".tmp", path)


class UserStore:
    def __init__(self, db_path, media_dir):
        self.path, self.media_dir = db_path, media_dir
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password_hash TEXT NOT NULL,
            sex TEXT, age REAL, height_cm REAL, weight_kg REAL, activity TEXT, goal TEXT,
            has_avatar INTEGER DEFAULT 0, created REAL, last_seen REAL)""")
        self.execute("""CREATE TABLE IF NOT EXISTS user_tokens (
            token_hash TEXT PRIMARY KEY, user_id TEXT, created REAL, expires REAL)""")
        self.execute("""CREATE TABLE IF NOT EXISTS user_weights (
            id INTEGER PRIMARY KEY, user_id TEXT, ts REAL, weight_kg REAL)""")
        self.execute("""CREATE TABLE IF NOT EXISTS user_photos (
            id INTEGER PRIMARY KEY, user_id TEXT, ts REAL, food_id TEXT, confidence REAL,
            day INTEGER, meal TEXT, source TEXT)""")
        # sign-up / sign-in / sign-out history for the dashboard (no IPs, no devices)
        self.execute("""CREATE TABLE IF NOT EXISTS user_events (
            id INTEGER PRIMARY KEY, user_id TEXT, ts REAL, event TEXT)""")
        # Google account id ("sub") of users who sign in with Google; added to older databases too
        if "google_sub" not in {r["name"] for r in self.execute("PRAGMA table_info(users)")}:
            self.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        self.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub ON users (google_sub)")

    def execute(self, sql, args=()):
        with contextlib.closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, args).fetchall()
            conn.commit()
            return rows

    # ---------- accounts ----------

    def create(self, email, name, password, profile, google_sub=None):
        """New account; password None for a Google-only account."""
        now = time.time()
        uid = secrets.token_hex(16)
        fields = {k: profile.get(k) for k in PROFILE_FIELDS if k != "name"}
        self.execute("INSERT INTO users (id, email, name, password_hash, sex, age, height_cm, weight_kg, activity, goal, "
                     "created, last_seen, google_sub) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (uid, email.lower(), name, generate_password_hash(password) if password else "", fields["sex"],
                      fields["age"], fields["height_cm"], fields["weight_kg"], fields["activity"], fields["goal"],
                      now, now, google_sub))
        if fields["weight_kg"]:
            self.execute("INSERT INTO user_weights (user_id, ts, weight_kg) VALUES (?, ?, ?)",
                         (uid, now, fields["weight_kg"]))
        return uid

    def by_email(self, email):
        rows = self.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
        return dict(rows[0]) if rows else None

    def by_google(self, google_sub):
        rows = self.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,))
        return dict(rows[0]) if rows else None

    def link_google(self, uid, google_sub):
        self.execute("UPDATE users SET google_sub = ? WHERE id = ?", (google_sub, uid))

    def get(self, uid):
        rows = self.execute("SELECT * FROM users WHERE id = ?", (uid,))
        return dict(rows[0]) if rows else None

    def exists(self, uid):
        return bool(self.execute("SELECT 1 FROM users WHERE id = ?", (uid,)))

    def check_password(self, user, password):
        return bool(user["password_hash"]) and check_password_hash(user["password_hash"], password)

    def update(self, uid, fields):
        if not fields:
            return
        old = self.get(uid)
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.execute(f"UPDATE users SET {sets} WHERE id = ?", (*fields.values(), uid))
        if "weight_kg" in fields and fields["weight_kg"] and fields["weight_kg"] != old["weight_kg"]:
            self.execute("INSERT INTO user_weights (user_id, ts, weight_kg) VALUES (?, ?, ?)",
                         (uid, time.time(), fields["weight_kg"]))

    def touch(self, uid):
        self.execute("UPDATE users SET last_seen = ? WHERE id = ?", (time.time(), uid))

    def log_event(self, uid, event):
        """event: register | login | logout"""
        self.execute("INSERT INTO user_events (user_id, ts, event) VALUES (?, ?, ?)", (uid, time.time(), event))

    def delete(self, uid):
        for table in ("user_tokens", "user_weights", "user_photos", "user_events"):
            self.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
        self.execute("DELETE FROM users WHERE id = ?", (uid,))
        shutil.rmtree(self.user_dir(uid), ignore_errors=True)

    # ---------- tokens ----------

    def new_token(self, uid):
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.execute("INSERT INTO user_tokens VALUES (?, ?, ?, ?)",
                     (_token_hash(token), uid, now, now + TOKEN_DAYS * 86400))
        self.touch(uid)
        return token

    def user_for_token(self, token):
        now = time.time()
        rows = self.execute("SELECT user_id FROM user_tokens WHERE token_hash = ? AND expires > ?",
                            (_token_hash(token), now))
        if not rows:
            return None
        uid = rows[0]["user_id"]
        # every signed-in call counts as "last seen" (at most one write a minute per user)
        self.execute("UPDATE users SET last_seen = ? WHERE id = ? AND last_seen < ?", (now, uid, now - 60))
        return uid

    def revoke(self, token):
        self.execute("DELETE FROM user_tokens WHERE token_hash = ?", (_token_hash(token),))

    def set_password(self, uid, password):
        """New password; every old login token stops working."""
        self.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), uid))
        self.execute("DELETE FROM user_tokens WHERE user_id = ?", (uid,))

    # ---------- photos ----------

    def user_dir(self, uid):
        return os.path.join(self.media_dir, uid)

    def avatar_path(self, uid):
        return os.path.join(self.user_dir(uid), "avatar.jpg")

    def set_avatar(self, uid, data):
        _save_jpeg(data, self.avatar_path(uid), side=512)
        self.execute("UPDATE users SET has_avatar = 1 WHERE id = ?", (uid,))

    def add_photo(self, uid, data, food_id, confidence, day=None, meal=None, source="predict"):
        cur = self.execute("INSERT INTO user_photos (user_id, ts, food_id, confidence, day, meal, source) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                           (uid, time.time(), food_id, confidence, day, meal, source))
        pid = cur[0]["id"]
        try:
            _save_jpeg(data, self.photo_path(uid, pid))
        except Exception:
            self.execute("DELETE FROM user_photos WHERE id = ?", (pid,))
            raise
        return pid

    def photo_path(self, uid, pid):
        return os.path.join(self.user_dir(uid), "meals", f"{int(pid)}.jpg")

    def photos(self, uid, limit=200):
        return [dict(r) for r in self.execute(
            "SELECT * FROM user_photos WHERE user_id = ? ORDER BY id DESC LIMIT ?", (uid, limit))]

    def photo(self, uid, pid):
        rows = self.execute("SELECT * FROM user_photos WHERE user_id = ? AND id = ?", (uid, pid))
        return dict(rows[0]) if rows else None

    def delete_photo(self, uid, pid):
        self.execute("DELETE FROM user_photos WHERE user_id = ? AND id = ?", (uid, pid))
        with contextlib.suppress(FileNotFoundError):
            os.remove(self.photo_path(uid, pid))

    def weights(self, uid):
        return [dict(r) for r in self.execute(
            "SELECT ts, weight_kg FROM user_weights WHERE user_id = ? ORDER BY ts", (uid,))]
