import sys
import os
import pytest
import psycopg2
from fastapi.testclient import TestClient

# Tests always run against a dedicated database. Never let the destructive
# seed fixture default to the developer's normal `agencydesk` database.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "agencydesk_test")
if not os.environ["DB_NAME"].endswith("_test"):
    raise RuntimeError("TEST_DB_NAME must end in _test; refusing to run against a non-test database")

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from seed import seed_database
from config import get_settings


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize and seed the isolated test database before the test session."""
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        port=settings.DB_PORT,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.users')")
            if cur.fetchone()[0] is None:
                schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
                with open(schema_path, encoding="utf-8") as schema_file:
                    cur.execute(schema_file.read())
                conn.commit()
            cur.execute("SELECT to_regclass('public.audit_events')")
            if cur.fetchone()[0] is None:
                migration_path = os.path.join(
                    os.path.dirname(__file__), "..", "migrations", "003_audit_events.sql"
                )
                with open(migration_path, encoding="utf-8") as migration_file:
                    cur.execute(migration_file.read())
                conn.commit()
    finally:
        conn.close()
    seed_database()


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    """Token for Alex Rivera (Admin in Acme, Client in Beta)."""
    res = client.post("/auth/login", json={"email": "alex@example.com", "password": "password123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return res.json()["token"]


@pytest.fixture(scope="session")
def member_token(client):
    """Token for Sarah Chen (Staff Member in Acme)."""
    res = client.post("/auth/login", json={"email": "sarah@acme.com", "password": "password123"})
    assert res.status_code == 200, f"Member login failed: {res.text}"
    return res.json()["token"]


@pytest.fixture(scope="session")
def client_token(client):
    """Token for John Starlight (Client User for Starlight Tech in Acme)."""
    res = client.post("/auth/login", json={"email": "john@starlight.com", "password": "password123"})
    assert res.status_code == 200, f"Client user login failed: {res.text}"
    return res.json()["token"]


@pytest.fixture(scope="session")
def agencies(client, admin_token):
    """Fetch seeded agency IDs."""
    res = client.get("/auth/memberships", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    memberships = res.json()["memberships"]
    acme_id = next(m["agency_id"] for m in memberships if m["agency_name"] == "Acme Digital Agency")
    beta_id = next(m["agency_id"] for m in memberships if m["agency_name"] == "Beta Media Group")
    return {"acme": acme_id, "beta": beta_id}


@pytest.fixture
def admin_acme_headers(admin_token, agencies):
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-Agency-ID": agencies["acme"],
    }


@pytest.fixture
def admin_beta_headers(admin_token, agencies):
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-Agency-ID": agencies["beta"],
    }


@pytest.fixture
def member_acme_headers(member_token, agencies):
    return {
        "Authorization": f"Bearer {member_token}",
        "X-Agency-ID": agencies["acme"],
    }


@pytest.fixture
def client_acme_headers(client_token, agencies):
    return {
        "Authorization": f"Bearer {client_token}",
        "X-Agency-ID": agencies["acme"],
    }


@pytest.fixture
def sample_entities(client, admin_acme_headers):
    """Return seeded Acme project, internal task, and client-visible task."""
    res = client.get("/projects", headers=admin_acme_headers)
    assert res.status_code == 200
    projects = res.json()["projects"]
    project = next(p for p in projects if p["name"] == "Website Redesign")

    detail_res = client.get(f"/projects/{project['id']}", headers=admin_acme_headers)
    assert detail_res.status_code == 200
    tasks = detail_res.json()["tasks"]

    internal_task = next(t for t in tasks if t["is_internal"])
    public_task = next(t for t in tasks if not t["is_internal"])

    return {
        "project": project,
        "internal_task": internal_task,
        "public_task": public_task,
    }


@pytest.fixture(scope="session")
def alex_user_id(client, admin_token):
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    return res.json()["id"]


@pytest.fixture(scope="session")
def sarah_user_id(client, member_token):
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {member_token}"})
    return res.json()["id"]


@pytest.fixture(scope="session")
def john_user_id(client, client_token):
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {client_token}"})
    return res.json()["id"]


@pytest.fixture
def sample_client(client, admin_acme_headers):
    res = client.get("/agency/clients", headers=admin_acme_headers)
    assert res.status_code == 200
    clients = res.json()["clients"]
    return next(c for c in clients if c["name"] == "Starlight Tech")
