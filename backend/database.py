import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "agencydesk")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "devpass")
DB_PORT = os.getenv("DB_PORT", "5432")

_pool: ThreadedConnectionPool | None = None


def get_connection_pool(minconn: int = 2, maxconn: int = 20) -> ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            cursor_factory=RealDictCursor,
        )
    return _pool


def close_connection_pool():
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        _pool = None


class PooledConnectionWrapper:
    """Wrapper that intercepts .close() to return connection to the pool."""

    def __init__(self, pool: ThreadedConnectionPool, conn):
        self._pool = pool
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        if self._conn is not None:
            try:
                # Rollback any uncommitted transaction before returning to pool
                if not self._conn.closed:
                    self._conn.rollback()
                self._pool.putconn(self._conn)
            except Exception:
                pass
            finally:
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_db():
    """Acquire a pooled connection; calling .close() returns it back to the pool."""
    pool = get_connection_pool()
    raw_conn = pool.getconn()
    return PooledConnectionWrapper(pool, raw_conn)
