"""Postgres on Supabase, through the transaction pooler (port 6543).

One short-lived connection per unit of work, which suits serverless. The pooler's transaction
mode does not support prepared statements, so they are switched off."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from config import env


def connect() -> psycopg.Connection:
    return psycopg.connect(env("DATABASE_URL"), row_factory=dict_row, prepare_threshold=None,
                           connect_timeout=10, sslmode="require")


@contextmanager
def transaction():
    """A connection whose work is committed on success and rolled back on any error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
