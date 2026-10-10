"""Esquema y conexión de la base de planta (SQLite). Toda fila lleva plant_id y line_id: es la clave de
aislamiento entre plantas y líneas que aplican las tools."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    plant_id TEXT NOT NULL, lines TEXT NOT NULL            -- JSON: líneas a las que tiene acceso
);
CREATE TABLE IF NOT EXISTS model_versions (
    version TEXT PRIMARY KEY, stage TEXT NOT NULL,         -- production | staging | archived
    created_at TEXT NOT NULL, notes TEXT
);
CREATE TABLE IF NOT EXISTS lines (
    plant_id TEXT NOT NULL, line_id TEXT NOT NULL, status TEXT NOT NULL,   -- RUNNING | PAUSED
    class_conf_min REAL NOT NULL, model_version TEXT NOT NULL, camera_id TEXT NOT NULL,
    updated_at TEXT NOT NULL, PRIMARY KEY (plant_id, line_id)
);
CREATE TABLE IF NOT EXISTS inference_events (
    event_id INTEGER PRIMARY KEY, ts TEXT NOT NULL, plant_id TEXT NOT NULL, line_id TEXT NOT NULL,
    shift INTEGER NOT NULL, decision TEXT NOT NULL, robot_action TEXT NOT NULL, object_id INTEGER,
    angle_deg REAL, class_confidence REAL, novelty REAL, angle_width_deg REAL,
    model_version TEXT NOT NULL, camera_id TEXT NOT NULL, grasp_ok INTEGER       -- NULL si no hubo agarre
);
CREATE INDEX IF NOT EXISTS ix_events ON inference_events (plant_id, line_id, ts);
CREATE TABLE IF NOT EXISTS camera_health (
    ts TEXT NOT NULL, plant_id TEXT NOT NULL, line_id TEXT NOT NULL, camera_id TEXT NOT NULL,
    brightness REAL NOT NULL, focus_score REAL NOT NULL, dropped_frames INTEGER NOT NULL, status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_camera ON camera_health (plant_id, line_id, ts);
CREATE TABLE IF NOT EXISTS line_events (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, plant_id TEXT NOT NULL, line_id TEXT NOT NULL,
    type TEXT NOT NULL, detail TEXT NOT NULL, actor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_cases (
    case_id TEXT PRIMARY KEY, event_id INTEGER, image_id TEXT, plant_id TEXT NOT NULL, line_id TEXT NOT NULL,
    created_at TEXT NOT NULL, status TEXT NOT NULL,          -- PENDING | RESOLVED
    reason TEXT NOT NULL, evidence TEXT NOT NULL,            -- JSON: resultado de visión que motivó el rechazo
    confirmed_object_id INTEGER, confirmed_angle_deg REAL, resolved_by TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS retraining_items (
    item_id INTEGER PRIMARY KEY, case_id TEXT NOT NULL UNIQUE, plant_id TEXT NOT NULL, line_id TEXT NOT NULL,
    object_id INTEGER NOT NULL, angle_deg REAL NOT NULL, added_by TEXT NOT NULL, added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY, plant_id TEXT NOT NULL, line_id TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL, severity TEXT NOT NULL,       -- low | medium | high | critical
    status TEXT NOT NULL,                                    -- OPEN | ESCALATED | RESOLVED
    created_by TEXT NOT NULL, created_at TEXT NOT NULL, assignee TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sku_candidates (
    candidate_id TEXT PRIMARY KEY, plant_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
    n_views INTEGER NOT NULL, max_gap_deg REAL NOT NULL, validation TEXT,   -- JSON
    created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY, action TEXT NOT NULL, args TEXT NOT NULL, plant_id TEXT NOT NULL,
    line_id TEXT, requested_by TEXT NOT NULL, session_id TEXT, created_at TEXT NOT NULL,
    status TEXT NOT NULL,                                    -- PENDING | EXECUTED | REJECTED | FAILED
    decided_by TEXT, decided_at TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY, tool TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    image_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, path TEXT NOT NULL, filename TEXT,
    plant_id TEXT NOT NULL, line_id TEXT, session_id TEXT NOT NULL, uploaded_by TEXT NOT NULL,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, session_id TEXT, user_id TEXT, role TEXT, plant_id TEXT,
    tool TEXT NOT NULL, args TEXT NOT NULL, outcome TEXT NOT NULL,   -- ok | denied | invalid | error | pending_approval
    detail TEXT, latency_ms REAL, source TEXT NOT NULL               -- agent | human
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def rows(con: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(con: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None
