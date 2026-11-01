"""Lapisan database SQLite untuk aplikasi pencatat pengeluaran pribadi.

Satu database, satu pemilik. Tidak ada tabel user.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Bisa dioverride lewat environment variable DB_PATH (misal ke /tmp di Streamlit Cloud).
DB_PATH = os.getenv("DB_PATH", os.path.join(APP_DIR, "data", "kas.db"))

DEFAULT_CATEGORIES = [
    "Makan & Minum",
    "Transportasi",
    "Belanja Harian",
    "Tagihan & Utilitas",
    "Kesehatan",
    "Pendidikan",
    "Hiburan",
    "Cicilan & Utang",
    "Donasi",
    "Lainnya",
]


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None:
        return False
    return column in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_from_multiuser(conn: sqlite3.Connection) -> None:
    """Skema lama punya tabel users dan kolom user_id. Buang kolom itu.

    Data transaksi dan budget tetap dipertahankan (digabung jadi satu pemilik).
    """
    if _has_column(conn, "transactions", "user_id"):
        conn.executescript(
            """
            CREATE TABLE tx_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date     TEXT NOT NULL,
                category    TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount      INTEGER NOT NULL CHECK (amount > 0),
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO tx_new (id, tx_date, category, description, amount, created_at)
                SELECT id, tx_date, category, description, amount, created_at FROM transactions;
            DROP TABLE transactions;
            ALTER TABLE tx_new RENAME TO transactions;
            """
        )

    if _has_column(conn, "budgets", "user_id"):
        conn.executescript(
            """
            CREATE TABLE b_new (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                month    TEXT NOT NULL,
                category TEXT NOT NULL,
                amount   INTEGER NOT NULL CHECK (amount >= 0),
                UNIQUE (month, category)
            );
            INSERT OR IGNORE INTO b_new (month, category, amount)
                SELECT month, category, amount FROM budgets;
            DROP TABLE budgets;
            ALTER TABLE b_new RENAME TO budgets;
            """
        )

    conn.execute("DROP TABLE IF EXISTS users")


def init_db() -> None:
    with get_conn() as conn:
        _migrate_from_multiuser(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date     TEXT NOT NULL,
                category    TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                amount      INTEGER NOT NULL CHECK (amount > 0),
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(tx_date);

            CREATE TABLE IF NOT EXISTS budgets (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                month    TEXT NOT NULL,
                category TEXT NOT NULL,
                amount   INTEGER NOT NULL CHECK (amount >= 0),
                UNIQUE (month, category)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------- settings


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )


# ---------------------------------------------------------------- transactions


def add_transaction(
    tx_date: date | str, category: str, description: str, amount: int
) -> int:
    if amount <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    tx_date = tx_date.isoformat() if isinstance(tx_date, date) else tx_date
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO transactions (tx_date, category, description, amount)
               VALUES (?, ?, ?, ?)""",
            (tx_date, category.strip(), description.strip(), int(amount)),
        )
        return int(cur.lastrowid)


def update_transaction(
    tx_id: int, tx_date: str, category: str, description: str, amount: int
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE transactions
                  SET tx_date = ?, category = ?, description = ?, amount = ?
                WHERE id = ?""",
            (tx_date, category.strip(), description.strip(), int(amount), tx_id),
        )


def delete_transaction(tx_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))


def list_transactions(start: str | None = None, end: str | None = None):
    sql = "SELECT id, tx_date, category, description, amount FROM transactions WHERE 1=1"
    params: list = []
    if start:
        sql += " AND tx_date >= ?"
        params.append(start)
    if end:
        sql += " AND tx_date <= ?"
        params.append(end)
    sql += " ORDER BY tx_date DESC, id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def categories_in_use() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM transactions ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def merge_old_categories(mapping: dict[str, str]) -> int:
    """Gabungkan kategori lama ke kategori baru. Return jumlah baris terpengaruh."""
    changed = 0
    with get_conn() as conn:
        for old, new in mapping.items():
            if old == new or not new:
                continue
            cur = conn.execute(
                "UPDATE transactions SET category = ? WHERE category = ?", (new.strip(), old)
            )
            changed += cur.rowcount
    return changed


def delete_category(category: str) -> None:
    """Pindahkan transaksi kategori ini ke 'Lainnya', lalu hapus budgetnya."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE transactions SET category = 'Lainnya' WHERE category = ?", (category,)
        )
        conn.execute("DELETE FROM budgets WHERE category = ?", (category,))


# ---------------------------------------------------------------- budgets


def set_budget(month: str, category: str, amount: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO budgets (month, category, amount) VALUES (?, ?, ?)
               ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount""",
            (month, category.strip(), int(amount)),
        )


def delete_budget(budget_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))


def list_budgets(month: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, month, category, amount FROM budgets WHERE month = ? ORDER BY category",
            (month,),
        ).fetchall()
    return [dict(r) for r in rows]


def copy_budgets(from_month: str, to_month: str) -> int:
    """Salin semua budget satu bulan ke bulan lain. Return jumlah baris disalin."""
    rows = list_budgets(from_month)
    for r in rows:
        set_budget(to_month, r["category"], r["amount"])
    return len(rows)


def months_with_data() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT substr(tx_date, 1, 7) AS m FROM transactions
                ORDER BY m DESC"""
        ).fetchall()
    return [r["m"] for r in rows]


def months_with_budgets() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT month FROM budgets ORDER BY month DESC").fetchall()
    return [r["month"] for r in rows]
