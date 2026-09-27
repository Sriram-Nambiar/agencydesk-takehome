import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from config import get_settings

settings = get_settings()
DB_HOST = settings.DB_HOST
DB_NAME = settings.DB_NAME
DB_USER = settings.DB_USER
DB_PASS = settings.DB_PASS
DB_PORT = str(settings.DB_PORT)

_pool: ThreadedConnectionPool | None = None


def get_connection_pool(minconn: int | None = None, maxconn: int | None = None) -> ThreadedConnectionPool:
    global _pool
    cfg = get_settings()
    actual_min = minconn if minconn is not None else cfg.DB_MIN_CONN
    actual_max = maxconn if maxconn is not None else cfg.DB_MAX_CONN
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(
            minconn=actual_min,
            maxconn=actual_max,
            host=cfg.DB_HOST,
            dbname=cfg.DB_NAME,
            user=cfg.DB_USER,
            password=cfg.DB_PASS,
            port=cfg.DB_PORT,
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
