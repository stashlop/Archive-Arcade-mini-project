"""Database connection helper shared by the raw-SQL parts of the app.

Locally the app keeps using a SQLite file (instance/arcade.db). On hosts with
an ephemeral filesystem such as Vercel, set DATABASE_URL to a PostgreSQL URL
(Neon, Supabase, Vercel Postgres, ...). In that case ``connect()`` returns a
small wrapper around a pooled psycopg connection that mimics the subset of the
sqlite3 API used in this codebase: ``?`` placeholders, ``sqlite3.Row``-style
rows, ``cursor.lastrowid``, ``PRAGMA table_info``, ``INSERT OR IGNORE`` and
``AUTOINCREMENT`` table definitions.
"""
import re
import sqlite3

from flask import current_app
from sqlalchemy import event

from models import db


def is_postgres():
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    return uri.startswith('postgres')


def connect(path=None, **kwargs):
    """Return a DB-API connection for raw SQL.

    With SQLite, the file configured for SQLAlchemy wins over ``path`` so the
    ORM and raw SQL always share one database.
    """
    if is_postgres():
        return PgConnection(db.engine)
    database = db.engine.url.database
    if database and database != ':memory:':
        path = database
    return sqlite3.connect(path, **kwargs)


def register_engine_events(engine):
    """Make sure pooled connections go back to the pool in the state the ORM expects."""
    if engine.dialect.name != 'postgresql':
        return

    @event.listens_for(engine, 'checkin')
    def _reset_autocommit(dbapi_conn, _record):
        try:
            if getattr(dbapi_conn, 'autocommit', False):
                if dbapi_conn.info.transaction_status != 0:  # not idle
                    dbapi_conn.rollback()
                dbapi_conn.autocommit = False
        except Exception:
            pass


class Row:
    """Row supporting index, key, ``dict(row)`` and tuple unpacking like sqlite3.Row."""
    __slots__ = ('_keys', '_values', '_index')

    def __init__(self, keys, values):
        self._keys = keys
        self._values = tuple(values)
        self._index = {k: i for i, k in enumerate(keys)}

    def keys(self):
        return list(self._keys)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._values[self._index[item]]
        return self._values[item]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"Row({dict(zip(self._keys, self._values))!r})"


_PRAGMA_TABLE_INFO = re.compile(r'^\s*PRAGMA\s+table_info\(\s*"?([A-Za-z0-9_]+)"?\s*\)\s*;?\s*$', re.I)
_INSERT_OR_IGNORE = re.compile(r'^\s*INSERT\s+OR\s+IGNORE\s+INTO', re.I)
_AUTOINCREMENT = re.compile(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', re.I)
_LIKE = re.compile(r'(?<![A-Za-z_])LIKE(?![A-Za-z_])', re.I)
_IFNULL = re.compile(r'(?<![A-Za-z_])IFNULL\s*\(', re.I)
_IS_INSERT = re.compile(r'^\s*INSERT\s', re.I)

_TABLE_INFO_SQL = (
    "SELECT ordinal_position - 1, column_name, data_type, "
    "CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END, column_default, 0 "
    "FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = %s "
    "ORDER BY ordinal_position"
)


def _translate(sql):
    """Translate the SQLite dialect used in this app to PostgreSQL."""
    sql = sql.replace('%', '%%').replace('?', '%s')
    sql = _AUTOINCREMENT.sub('SERIAL PRIMARY KEY', sql)
    sql = _LIKE.sub('ILIKE', sql)  # SQLite LIKE is case-insensitive
    sql = _IFNULL.sub('COALESCE(', sql)
    if _INSERT_OR_IGNORE.match(sql):
        sql = _INSERT_OR_IGNORE.sub('INSERT INTO', sql).rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return sql


def _params(params):
    if params is None:
        return ()
    # PostgreSQL won't put a Python bool into an INTEGER column
    return tuple(int(p) if isinstance(p, bool) else p for p in params)


def _row_factory(cursor):
    keys = [c.name for c in (cursor.description or [])]
    return lambda values: Row(keys, values)


class PgCursor:
    def __init__(self, conn):
        self._conn = conn
        self._cur = conn._raw.cursor(row_factory=_row_factory)
        self.lastrowid = None
        self._rows = None

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql, params=None):
        self._rows = None
        stripped = sql.strip().rstrip(';').strip()
        upper = stripped.upper()

        if upper in ('BEGIN', 'BEGIN IMMEDIATE', 'BEGIN EXCLUSIVE', 'BEGIN TRANSACTION'):
            self._cur.execute('BEGIN')
            if upper != 'BEGIN' and upper != 'BEGIN TRANSACTION':
                # SQLite's IMMEDIATE/EXCLUSIVE take the write lock up front;
                # serialize such transactions with a transaction-scoped advisory lock.
                self._cur.execute('SELECT pg_advisory_xact_lock(727274)')
            return self

        m = _PRAGMA_TABLE_INFO.match(stripped)
        if m:
            self._cur.execute(_TABLE_INFO_SQL, (m.group(1),))
            return self

        pg_sql = _translate(sql)
        returning = bool(_IS_INSERT.match(pg_sql)) and 'RETURNING' not in pg_sql.upper()
        if returning:
            pg_sql = pg_sql.rstrip().rstrip(';') + ' RETURNING id'
        self._cur.execute(pg_sql, _params(params))
        if returning:
            row = self._cur.fetchone()
            self.lastrowid = row[0] if row else None
            self._rows = []
        return self

    def executemany(self, sql, seq_of_params):
        self._rows = None
        self._cur.executemany(_translate(sql), [_params(p) for p in seq_of_params])
        return self

    def fetchone(self):
        if self._rows is not None:
            return self._rows.pop(0) if self._rows else None
        if self._cur.description is None:
            return None
        return self._cur.fetchone()

    def fetchall(self):
        if self._rows is not None:
            rows, self._rows = self._rows, []
            return rows
        if self._cur.description is None:
            return []
        return self._cur.fetchall()

    def fetchmany(self, size=1):
        return [r for r in (self.fetchone() for _ in range(size)) if r is not None]

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class PgConnection:
    """sqlite3.Connection look-alike backed by a connection from the SQLAlchemy pool.

    Runs in autocommit mode (each statement is committed on its own) unless the
    caller issues an explicit BEGIN, which matches how the raw-SQL code in this
    app uses SQLite.
    """

    def __init__(self, engine):
        self._pooled = engine.raw_connection()
        self._raw = self._pooled.driver_connection
        self._raw.autocommit = True
        self.row_factory = None  # accepted for sqlite3 compatibility; rows always support both styles

    def cursor(self):
        return PgCursor(self)

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq_of_params):
        return self.cursor().executemany(sql, seq_of_params)

    def commit(self):
        if self._raw.info.transaction_status != 0:
            self._raw.execute('COMMIT')

    def rollback(self):
        if self._raw.info.transaction_status != 0:
            self._raw.execute('ROLLBACK')

    def close(self):
        if self._pooled is None:
            return
        try:
            self.rollback()
        except Exception:
            pass
        try:
            self._pooled.close()
        finally:
            self._pooled = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
