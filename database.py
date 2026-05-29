import sqlite3
from datetime import datetime
from typing import List, Dict


class Database:
    def __init__(self, db_path: str = "finance.db"):
        self.db_path = db_path
        self._create_tables()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.commit()

    def init_user(self, user_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,)
            )
            conn.commit()

    def add_transaction(self, user_id: int, tx_type: str, amount: float,
                        category: str, description: str = ""):
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO transactions (user_id, type, amount, category, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, tx_type, amount, category, description)
            )
            conn.commit()

    def get_transactions(self, user_id: int, limit: int = 20) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT type, amount, category, description, created_at
                   FROM transactions WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self, user_id: int) -> Dict:
        with self._get_conn() as conn:
            income = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE user_id=? AND type='income'",
                (user_id,)
            ).fetchone()["total"]

            expense = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE user_id=? AND type='expense'",
                (user_id,)
            ).fetchone()["total"]

        return {
            "total_income": income,
            "total_expense": expense,
            "balance": income - expense
        }
