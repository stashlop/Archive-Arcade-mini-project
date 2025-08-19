import sys, sqlite3, json, os

def inspect(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall()]
    print("Tables:", tables or "(none)")

    for t in tables:
        print("\n--", t)
        cur.execute(f"PRAGMA table_info({t});")
        cols = [r["name"] for r in cur.fetchall()]
        print("Columns:", cols)
        cur.execute(f"SELECT * FROM {t} LIMIT 20;")
        rows = cur.fetchall()
        for r in rows:
            print(dict(r))
        if not rows:
            print("(no rows)")
    con.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_db.py /path/to/database.db")
    else:
        inspect(sys.argv[1])