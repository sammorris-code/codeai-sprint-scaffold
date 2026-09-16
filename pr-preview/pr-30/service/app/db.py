"""One connection pool, and the row shape the whole app uses."""
import os

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

pool = ConnectionPool(DSN, min_size=1, max_size=8, open=False,
                      kwargs={"row_factory": dict_row})


def rows(sql, params=None):
    with pool.connection() as conn:
        return conn.execute(sql, params or {}).fetchall()


def one(sql, params=None):
    result = rows(sql, params)
    return result[0] if result else None


def execute(sql, params=None):
    with pool.connection() as conn:
        cur = conn.execute(sql, params or {})
        return cur.fetchall() if cur.description else []
