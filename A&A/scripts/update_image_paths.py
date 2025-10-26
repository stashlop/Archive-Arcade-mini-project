#!/usr/bin/env python3
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # project root
INSTANCE_DIRS = [
    ROOT / 'instance',                          # project-level instance
    ROOT / 'A&A' / 'instance',                  # app-level instance (common for this app)
]

SQL_BOOKS = """
UPDATE books
SET image = 'images/books/' || TRIM(image)
WHERE image IS NOT NULL
  AND TRIM(image) <> ''
  AND INSTR(TRIM(image), '/') = 0;
"""

SQL_GAMES = """
UPDATE games
SET image = 'images/games/' || TRIM(image)
WHERE image IS NOT NULL
  AND TRIM(image) <> ''
  AND INSTR(TRIM(image), '/') = 0;
"""


def update_db(db_path: Path, sql: str, table: str) -> int:
    if not db_path.exists():
        print(f"[skip] {db_path} not found; {table} not updated.")
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        # Ensure table exists; if not, skip gracefully
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            print(f"[skip] table '{table}' not found in {db_path.name}")
            return 0
        cur.execute(sql)
        conn.commit()
        print(f"[ok] {table}: {conn.total_changes} rows updated in {db_path.name}")
        return conn.total_changes
    finally:
        conn.close()


def main():
    total = 0
    for inst in INSTANCE_DIRS:
        inst.mkdir(parents=True, exist_ok=True)
        total += update_db(inst / 'books.db', SQL_BOOKS, 'books')
        total += update_db(inst / 'games.db', SQL_GAMES, 'games')
    print(f"Done. Total rows updated: {total}")

if __name__ == '__main__':
    main()
