"""Seed demo data once when a Docker deployment starts with an empty database."""
import time
import psycopg2
from psycopg2 import OperationalError, ProgrammingError

from config import get_settings
from seed import seed_database


def ensure_audit_events_table(conn):
    """Ensure audit_events table exists even on volumes initialized before audit migrations."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                actor_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id UUID NOT NULL,
                details JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_audit_events_agency_created ON audit_events(agency_id, created_at DESC);
        """)
    conn.commit()


def database_has_agencies(max_retries: int = 30, retry_delay: float = 1.0) -> bool:
    settings = get_settings()
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=settings.DB_HOST,
                dbname=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASS,
                port=settings.DB_PORT,
                connect_timeout=3,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'agencies'
                        );
                    """)
                    table_exists = cur.fetchone()[0]
                    if not table_exists:
                        print(f"Waiting for database schema initialization... (attempt {attempt}/{max_retries})")
                        time.sleep(retry_delay)
                        continue

                    ensure_audit_events_table(conn)

                    cur.execute("SELECT EXISTS (SELECT 1 FROM agencies);")
                    return bool(cur.fetchone()[0])
            finally:
                conn.close()
        except (OperationalError, ProgrammingError) as e:
            print(f"Waiting for database readiness ({e})... (attempt {attempt}/{max_retries})")
            time.sleep(retry_delay)

    raise RuntimeError("Timed out waiting for database and schema to be ready.")


if __name__ == "__main__":
    if database_has_agencies():
        print("Database already contains data; skipping demo seed.")
    else:
        print("Database is empty; adding demo data.")
        seed_database()
