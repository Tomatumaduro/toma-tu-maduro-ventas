from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ttm.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','viewer')),
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS daily_sales (
              sale_date TEXT PRIMARY KEY, total_sales REAL NOT NULL,
              local_sales REAL NOT NULL, delivery_sales REAL NOT NULL,
              tickets INTEGER NOT NULL, local_tickets INTEGER NOT NULL,
              delivery_tickets INTEGER NOT NULL, cash REAL DEFAULT 0,
              card REAL DEFAULT 0, transfer REAL DEFAULT 0,
              pedidos_ya REAL DEFAULT 0, uber_eats REAL DEFAULT 0,
              rappi REAL DEFAULT 0, other_delivery REAL DEFAULT 0,
              source_file TEXT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS product_sales (
              sale_date TEXT, product_raw TEXT, product_name TEXT, channel TEXT,
              quantity REAL, source_file TEXT,
              PRIMARY KEY(sale_date, product_raw),
              FOREIGN KEY(sale_date) REFERENCES daily_sales(sale_date) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS expenses (
              id INTEGER PRIMARY KEY, expense_date TEXT, category TEXT,
              description TEXT, amount REAL, source_file TEXT
            );
            """
        )
