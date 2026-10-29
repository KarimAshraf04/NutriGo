"""State shared by the Flutter API and the admin dashboard.

DataStore   the nutrition tables, editable from the dashboard (writes the CSVs back)
RequestLog  SQLite log of Flutter API calls: endpoint, status, latency and the dish involved.
            No photos and no personal data (the /api/target body is never stored).
"""
import contextlib
import csv
import os
import sqlite3
import threading
import time

from nutrition import NUMERIC, health_score, load_table
from recommender import load_fastfood

FILES = {"foods": "food101_nutrition.csv", "alternatives": "healthy_alternatives.csv"}
COLUMNS = ["food_id", "name", "category", "serving"] + NUMERIC + ["tags"]


def _cell(row, col):
    v = row[col]
    if col == "tags":
        return ",".join(v)
    if col in NUMERIC:
        return int(v) if float(v).is_integer() else v
    return v


class DataStore:
    def __init__(self, data_dir, fastfood_path=None):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.tables = {name: load_table(self.path(name)) for name in FILES}
        fastfood_path = fastfood_path or os.path.join(data_dir, "fastfood.csv")
        self.menu = load_fastfood(fastfood_path) if os.path.exists(fastfood_path) else []

    @property
    def foods(self):
        return self.tables["foods"]

    @property
    def alternatives(self):
        return self.tables["alternatives"]

    def path(self, table):
        return os.path.join(self.data_dir, FILES[table])

    def save(self, table, row):
        """Add or replace one row (keyed by food_id) and rewrite the CSV."""
        row = dict(row, health_score=health_score(row))
        with self.lock:
            rows = dict(self.tables[table])
            rows[row["food_id"]] = row
            self._write(table, rows)

    def delete(self, table, food_id):
        with self.lock:
            rows = dict(self.tables[table])
            rows.pop(food_id, None)
            self._write(table, rows)

    def _write(self, table, rows):
        tmp = self.path(table) + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows([_cell(r, c) for c in COLUMNS] for r in rows.values())
        os.replace(tmp, self.path(table))
        self.tables[table] = rows  # swap in only after the file is safely written


class RequestLog:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY, ts REAL, endpoint TEXT, status INTEGER, ms REAL,
            food_id TEXT, confidence REAL, low_conf INTEGER, goal TEXT, n_swaps INTEGER)""")

    def execute(self, sql, args=()):
        with contextlib.closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, args).fetchall()
            conn.commit()
            return rows

    def add(self, endpoint, status, ms, food_id=None, confidence=None, low_conf=None,
            goal=None, n_swaps=None):
        self.execute(
            "INSERT INTO requests (ts, endpoint, status, ms, food_id, confidence, low_conf, goal, n_swaps)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), endpoint, status, ms, food_id, confidence, low_conf, goal, n_swaps))
