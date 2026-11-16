"""SQLite storage and seed data for the Dispatch Assistant (all data is fictional)."""
import os
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("DISPATCH_DB", Path(__file__).resolve().parent.parent / "data" / "dispatch.db"))

# Fixed simulated clock so results are repeatable.
SIM_NOW = datetime(2026, 11, 16, 17, 0)

SCHEMA = """
DROP TABLE IF EXISTS shoppers;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS pending_actions;
DROP TABLE IF EXISTS audit_log;
CREATE TABLE shoppers (
  id TEXT PRIMARY KEY, name TEXT, store TEXT,
  status TEXT,              -- available | busy | offline
  items_per_hour INTEGER
);
CREATE TABLE orders (
  id TEXT PRIMARY KEY, customer TEXT, store TEXT,
  status TEXT,              -- queued | shopping | delivering | delivered | fallback
  items_total INTEGER, items_picked INTEGER,
  value_usd REAL, promised_by TEXT, shopper_id TEXT
);
CREATE TABLE pending_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, order_id TEXT,
  shopper_id TEXT, reason TEXT, status TEXT, created_at TEXT
);
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT,
  action TEXT, order_id TEXT, detail TEXT
);
"""

STORES = ["Lincoln Park", "Edina", "Maple Grove"]


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def seed():
    """Create a fresh database with fictional shoppers and orders."""
    rnd = random.Random(42)
    con = connect()
    con.executescript(SCHEMA)
    shoppers = [
        ("S1", "Ava", "Lincoln Park", "busy", 60), ("S2", "Ben", "Lincoln Park", "available", 75),
        ("S3", "Cara", "Lincoln Park", "busy", 45), ("S4", "Dev", "Edina", "busy", 70),
        ("S5", "Eli", "Edina", "offline", 65), ("S6", "Fay", "Maple Grove", "busy", 50),
        ("S7", "Gus", "Maple Grove", "busy", 80), ("S8", "Hana", "Lincoln Park", "available", 55),
    ]
    con.executemany("INSERT INTO shoppers VALUES (?,?,?,?,?)", shoppers)
    busy = {"Lincoln Park": ["S1", "S3"], "Edina": ["S4"], "Maple Grove": ["S6", "S7"]}
    orders = []
    for i in range(1, 26):
        store = STORES[i % 3]
        items = rnd.randint(8, 60)
        status = rnd.choice(["queued", "shopping", "shopping", "delivering", "delivered"])
        picked = 0 if status == "queued" else (items if status in ("delivering", "delivered") else rnd.randint(0, items))
        shopper = None if status == "queued" else rnd.choice(busy[store])
        promised = SIM_NOW + timedelta(minutes=rnd.randint(-5, 90))
        orders.append((f"O{1000+i}", f"Customer {i}", store, status, items, picked,
                       round(rnd.uniform(25, 260), 2), promised.isoformat(timespec="minutes"), shopper))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", orders)
    con.commit()
    con.close()


if __name__ == "__main__":
    seed()
    print(f"Seeded {DB_PATH}")
