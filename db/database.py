"""All SQLite storage for the app: settings, drawings, journal notes,
paper-trading orders/positions/trades, and the account row.

A single Database instance is shared across the app. sqlite3 connections are
created with check_same_thread=False because the live-feed thread may write
fills; access is serialized through a threading.Lock.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(APP_ROOT, "amt_app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drawings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    kind      TEXT NOT NULL,
    payload   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    ts         REAL NOT NULL,
    price      REAL,
    note       TEXT NOT NULL,
    trade_id   INTEGER,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    side       TEXT NOT NULL,
    type       TEXT NOT NULL,
    qty        REAL NOT NULL,
    limit_price REAL,
    stop_price  REAL,
    status     TEXT NOT NULL,
    created_at REAL NOT NULL,
    filled_at  REAL,
    fill_price REAL
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL,
    qty         REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price  REAL NOT NULL,
    pnl         REAL NOT NULL,
    entry_ts    REAL NOT NULL,
    exit_ts     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    starting_balance REAL NOT NULL,
    cash            REAL NOT NULL,
    realized_pnl    REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ settings
    def set_setting(self, key: str, value: Any):
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def get_setting(self, key: str, default=None):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    # ------------------------------------------------------------------ drawings
    def save_drawings(self, ticker: str, timeframe: str, drawings: list[dict]):
        with self._lock:
            self._conn.execute(
                "DELETE FROM drawings WHERE ticker=? AND timeframe=?",
                (ticker, timeframe),
            )
            self._conn.executemany(
                "INSERT INTO drawings(ticker, timeframe, kind, payload) "
                "VALUES(?, ?, ?, ?)",
                [(ticker, timeframe, d["kind"], json.dumps(d)) for d in drawings],
            )
            self._conn.commit()

    def load_drawings(self, ticker: str, timeframe: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM drawings WHERE ticker=? AND timeframe=?",
                (ticker, timeframe),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ------------------------------------------------------------------ journal
    def add_journal(self, ticker: str, ts: float, price: Optional[float],
                    note: str, trade_id: Optional[int] = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO journal(ticker, ts, price, note, trade_id, created_at)"
                " VALUES(?, ?, ?, ?, ?, ?)",
                (ticker, ts, price, note, trade_id, time.time()),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_journal(self, ticker: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM journal WHERE ticker=? ORDER BY ts", (ticker,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_journal(self, note_id: int):
        with self._lock:
            self._conn.execute("DELETE FROM journal WHERE id=?", (note_id,))
            self._conn.commit()

    # ------------------------------------------------------------------ orders
    def insert_order(self, order: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO orders(ticker, side, type, qty, limit_price, "
                "stop_price, status, created_at, filled_at, fill_price) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (order["ticker"], order["side"], order["type"], order["qty"],
                 order.get("limit_price"), order.get("stop_price"),
                 order["status"], order["created_at"],
                 order.get("filled_at"), order.get("fill_price")),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_order(self, order_id: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE orders SET {cols} WHERE id=?",
                (*fields.values(), order_id),
            )
            self._conn.commit()

    def get_orders(self, ticker: str, status: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM orders WHERE ticker=?"
        args: list[Any] = [ticker]
        if status:
            q += " AND status=?"
            args.append(status)
        q += " ORDER BY created_at"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ trades
    def insert_trade(self, trade: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO trades(ticker, side, qty, entry_price, exit_price, "
                "pnl, entry_ts, exit_ts) VALUES(?,?,?,?,?,?,?,?)",
                (trade["ticker"], trade["side"], trade["qty"],
                 trade["entry_price"], trade["exit_price"], trade["pnl"],
                 trade["entry_ts"], trade["exit_ts"]),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_trades(self, ticker: Optional[str] = None) -> list[dict]:
        if ticker:
            q, args = "SELECT * FROM trades WHERE ticker=? ORDER BY exit_ts", (ticker,)
        else:
            q, args = "SELECT * FROM trades ORDER BY exit_ts", ()
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ account
    def get_account(self, starting_balance: float) -> dict:
        with self._lock:
            row = self._conn.execute("SELECT * FROM account WHERE id=1").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO account(id, starting_balance, cash, realized_pnl)"
                    " VALUES(1, ?, ?, 0)",
                    (starting_balance, starting_balance),
                )
                self._conn.commit()
                row = self._conn.execute(
                    "SELECT * FROM account WHERE id=1").fetchone()
        return dict(row)

    def update_account(self, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE account SET {cols} WHERE id=1", tuple(fields.values()))
            self._conn.commit()

    def reset_paper_trading(self, starting_balance: float):
        with self._lock:
            self._conn.execute("DELETE FROM orders")
            self._conn.execute("DELETE FROM trades")
            self._conn.execute(
                "UPDATE account SET starting_balance=?, cash=?, realized_pnl=0 "
                "WHERE id=1", (starting_balance, starting_balance))
            self._conn.commit()
