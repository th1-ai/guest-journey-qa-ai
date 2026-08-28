"""tools/store_ext.py - this agent's own tables: the five signal sources.

`migrate(store)` is called once, right after `Store(settings)`, exactly as
`core/store.py` documents. Everything here is I/O - the pure finding-builders
in tools/signals.py and the scorecard math in tools/scorecard.py never touch
a file or a database directly.

Each signal table is a SNAPSHOT of "what is true this week", not an
accumulating ledger (unlike, say, a financial ledger): importing a fresh CSV
replaces the previous contents. `seed_fixtures` is the demo/test path (fills
a table only if it is empty, so a hotel's own imported data is never
clobbered by `make demo`); `import_signals_csv` is the live path.
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

from core.redact import redact

SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_room_status (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL, room TEXT NOT NULL,
  status TEXT DEFAULT 'clean', ready_time TEXT
);
CREATE TABLE IF NOT EXISTS qa_touchpoints (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL, reservation_ref TEXT,
  touchpoint TEXT NOT NULL, expected_offset_hours REAL DEFAULT 0,
  sent_offset_hours REAL
);
CREATE TABLE IF NOT EXISTS qa_reviews (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL, rating REAL DEFAULT 0,
  category TEXT, text TEXT, date TEXT
);
CREATE TABLE IF NOT EXISTS qa_ota_listings (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL, channel TEXT, field TEXT,
  canonical_value TEXT, listed_value TEXT, match INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS qa_booking_flow (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL, step TEXT, seconds REAL DEFAULT 0,
  max_seconds REAL, broken INTEGER DEFAULT 0
);
"""

TABLES = ("qa_room_status", "qa_touchpoints", "qa_reviews", "qa_ota_listings",
         "qa_booking_flow")


def migrate(store) -> None:
    store.migrate(SCHEMA)


def _count(store, table: str) -> int:
    return store.db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _rid() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# fixtures (make demo, tests) - JSON in, tables filled once
# --------------------------------------------------------------------------
def seed_fixtures(store, fixtures_dir: Path) -> dict:
    """Load the bundled fixtures into the five tables, if they are empty."""
    loaded = {}
    plan = [
        ("qa_room_status", "room_status.json", _insert_room_status),
        ("qa_touchpoints", "journey_touchpoints.json", _insert_touchpoints),
        ("qa_reviews", "reviews.json", _insert_reviews),
        ("qa_ota_listings", "ota_listings.json", _insert_ota_listings),
        ("qa_booking_flow", "booking_flow_checks.json", _insert_booking_flow),
    ]
    for table, filename, inserter in plan:
        if _count(store, table) > 0:
            loaded[table] = _count(store, table)
            continue
        path = fixtures_dir / filename
        rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        inserter(store, rows)
        loaded[table] = len(rows)
    return loaded


def _insert_room_status(store, rows: list[dict]) -> None:
    for r in rows:
        store.db.execute(
            "INSERT OR IGNORE INTO qa_room_status (id, property_id, room, status, ready_time) "
            "VALUES (?,?,?,?,?)",
            (r.get("id") or _rid(), r["property_id"], r.get("room", ""),
             r.get("status", "clean"), r.get("ready_time")))


def _insert_touchpoints(store, rows: list[dict]) -> None:
    for r in rows:
        store.db.execute(
            "INSERT OR IGNORE INTO qa_touchpoints (id, property_id, reservation_ref, "
            "touchpoint, expected_offset_hours, sent_offset_hours) VALUES (?,?,?,?,?,?)",
            (r.get("id") or _rid(), r["property_id"], r.get("reservation_ref", ""),
             r.get("touchpoint", ""), r.get("expected_offset_hours", 0),
             r.get("sent_offset_hours")))


def _insert_reviews(store, rows: list[dict]) -> None:
    # A review's text is guest-written free text - redact on ingestion like
    # any other, even though a card number or IBAN here would be unusual.
    for r in rows:
        store.db.execute(
            "INSERT OR IGNORE INTO qa_reviews (id, property_id, rating, category, text, date) "
            "VALUES (?,?,?,?,?,?)",
            (r.get("id") or _rid(), r["property_id"], r.get("rating", 0),
             r.get("category", ""), redact(r.get("text", "")) or "", r.get("date", "")))


def _insert_ota_listings(store, rows: list[dict]) -> None:
    for r in rows:
        store.db.execute(
            "INSERT OR IGNORE INTO qa_ota_listings (id, property_id, channel, field, "
            "canonical_value, listed_value, match) VALUES (?,?,?,?,?,?,?)",
            (r.get("id") or _rid(), r["property_id"], r.get("channel", ""),
             r.get("field", ""), r.get("canonical_value", ""), r.get("listed_value", ""),
             1 if r.get("match", True) in (True, "true", "True", 1, "1") else 0))


def _insert_booking_flow(store, rows: list[dict]) -> None:
    for r in rows:
        store.db.execute(
            "INSERT OR IGNORE INTO qa_booking_flow (id, property_id, step, seconds, "
            "max_seconds, broken) VALUES (?,?,?,?,?,?)",
            (r.get("id") or _rid(), r["property_id"], r.get("step", ""),
             r.get("seconds", 0), r.get("max_seconds"),
             1 if r.get("broken") in (True, "true", "True", 1, "1") else 0))


# --------------------------------------------------------------------------
# live path: a hotel's own CSV exports in data/imports/ - snapshot, replaced
# in full on every import (see module docstring)
# --------------------------------------------------------------------------
def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


#: filename order shared by `import_signals_csv` (the write path) and
#: `preview_import_counts` (the read-only path `make doctor` and a dry-run
#: preview use) - see docs/how-it-works.md "The five signals".
IMPORT_FILES = ("room_status.csv", "journey_touchpoints.csv", "reviews.csv",
               "ota_listings.csv", "booking_flow_checks.csv")


def import_signals_csv(store, imports_dir: Path) -> dict:
    """Replace all five tables from `data/imports/*.csv`, if present.

    A CSV that does not exist leaves its table untouched (so importing after
    fixing just one file does not wipe the other four). Returns row counts
    for the run summary.
    """
    counts = {}
    plan = [
        ("qa_room_status", "room_status.csv", _insert_room_status),
        ("qa_touchpoints", "journey_touchpoints.csv", _insert_touchpoints),
        ("qa_reviews", "reviews.csv", _insert_reviews),
        ("qa_ota_listings", "ota_listings.csv", _insert_ota_listings),
        ("qa_booking_flow", "booking_flow_checks.csv", _insert_booking_flow),
    ]
    for table, filename, inserter in plan:
        rows = _read_csv(imports_dir / filename)
        if not rows:
            counts[table] = _count(store, table)
            continue
        store.db.execute(f"DELETE FROM {table}")
        inserter(store, rows)
        counts[table] = len(rows)
    return counts


def preview_import_counts(imports_dir: Path) -> dict[str, int]:
    """Row counts per signal CSV in `imports_dir`, via the exact same reader
    `import_signals_csv` uses (`_read_csv`) - so `make doctor`'s count always
    matches what a real import would load. Read-only: never opens the store,
    never writes a row, safe to call on a hotel's real `data/imports/` at any
    time (`make doctor`) or on a dry-run pass. A missing file counts as 0,
    same as `import_signals_csv` leaving that table untouched.
    """
    counts: dict[str, int] = {}
    for filename in IMPORT_FILES:
        try:
            counts[filename] = len(_read_csv(imports_dir / filename))
        except (OSError, UnicodeError, csv.Error):
            counts[filename] = -1   # present but unreadable - caller reports this
    return counts


# --------------------------------------------------------------------------
# loaders: table rows -> plain dicts, filtered to one property
# --------------------------------------------------------------------------
def _rows(store, table: str, property_id: str) -> list[dict]:
    cursor = store.db.execute(f"SELECT * FROM {table} WHERE property_id=?", (property_id,))
    return [dict(r) for r in cursor.fetchall()]


def load_room_status(store, property_id: str) -> list[dict]:
    return _rows(store, "qa_room_status", property_id)


def load_touchpoints(store, property_id: str) -> list[dict]:
    return _rows(store, "qa_touchpoints", property_id)


def load_reviews(store, property_id: str) -> list[dict]:
    return _rows(store, "qa_reviews", property_id)


def load_ota_listings(store, property_id: str) -> list[dict]:
    rows = _rows(store, "qa_ota_listings", property_id)
    for r in rows:
        r["match"] = bool(r.get("match"))
    return rows


def load_booking_flow(store, property_id: str) -> list[dict]:
    rows = _rows(store, "qa_booking_flow", property_id)
    for r in rows:
        r["broken"] = bool(r.get("broken"))
    return rows


def has_any_signal(store, property_id: str) -> bool:
    """True if at least one of the five tables has a row for this property."""
    return any((load_room_status(store, property_id), load_touchpoints(store, property_id),
               load_reviews(store, property_id), load_ota_listings(store, property_id),
               load_booking_flow(store, property_id)))
