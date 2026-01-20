# db.py
import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "/data/encoder.db")

@contextmanager
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS encoder_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,                 -- ISO timestamp
            data_valid INTEGER NOT NULL,      -- 0/1
            bale_s INTEGER,
            bale_i INTEGER,
            bale_ready INTEGER NOT NULL,      -- 0/1
            ram_forward INTEGER NOT NULL,     -- 0/1
            encoder_raw INTEGER,
            rounds REAL,
            distance REAL,
            ram_distance REAL,

            stroke_json TEXT,                -- JSON array length 10
            q_bale_number INTEGER,
            q_bale_length REAL,
            q_stroke_json TEXT               -- JSON array length 10
        );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON encoder_samples(ts);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_samples_bale ON encoder_samples(bale_s, bale_i);")
        con.commit()

def insert_sample(
    ts: datetime,
    data_valid: bool,
    bale_s: int | None,
    bale_i: int | None,
    bale_ready: bool,
    ram_forward: bool,
    encoder_raw: int | None,
    rounds: float | None,
    distance: float | None,
    ram_distance: float | None,
    stroke_list: list[float],
    q_bale_number: int | None,
    q_bale_length: float | None,
    q_stroke_list: list[float],
):
    with connect() as con:
        con.execute("""
        INSERT INTO encoder_samples (
            ts, data_valid, bale_s, bale_i, bale_ready, ram_forward,
            encoder_raw, rounds, distance, ram_distance,
            stroke_json, q_bale_number, q_bale_length, q_stroke_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts.isoformat(timespec="seconds"),
            1 if data_valid else 0,
            bale_s, bale_i,
            1 if bale_ready else 0,
            1 if ram_forward else 0,
            encoder_raw, rounds, distance, ram_distance,
            json.dumps(stroke_list),
            q_bale_number, q_bale_length,
            json.dumps(q_stroke_list),
        ))
        con.commit()
