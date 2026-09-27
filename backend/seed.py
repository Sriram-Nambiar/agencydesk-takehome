import os
import psycopg2
from passlib.context import CryptContext

# DB Configuration matching main.py
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "agencydesk")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "devpass")
DB_PORT = os.getenv("DB_PORT", "5432")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_database():
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )
    cur = conn.cursor()

    print("Cleaning up existing data...")
    cur.execute("""
        TRUNCATE agency_invites, time_entries, task_files, task_comments, tasks,
                 project_members, projects, agency_memberships, clients, agencies, users
        CASCADE;
    """)

    print("Seeding Users...")
    hashed_pw = pwd_context.hash("password123")  # Default password for all test accounts

    # 1. Alex Rivera (Demonstrates "One person, two agencies")
    cur.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
        ("alex@example.com", hashed_pw, "Alex Rivera")
    )
    alex_id = cur.fetchone()[0]

    # 2. Sarah Chen (Agency Member in Acme)
    cur.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
        ("sarah@acme.com", hashed_pw, "Sarah Chen")
    )
    sarah_id = cur.fetchone()[0]

    # 3. John Starlight (Client User for Starlight Tech)
    cur.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
        ("john@starlight.com", hashed_pw, "John Starlight")
    )
    starlight_user_id = cur.fetchone()[0]

    print("Seeding Agencies...")
    cur.execute("INSERT INTO agencies (name) VALUES ('Acme Digital Agency') RETURNING id")
    acme_id = cur.fetchone()[0]

    cur.execute("INSERT INTO agencies (name) VALUES ('Beta Media Group') RETURNING id")
    beta_id = cur.fetchone()[0]

    print("Seeding Clients...")
    cur.execute("INSERT INTO clients (agency_id, name) VALUES (%s, %s) RETURNING id", (acme_id, "Starlight Tech"))
    starlight_client_id = cur.fetchone()[0]

    cur.execute("INSERT INTO clients (agency_id, name) VALUES (%s, %s) RETURNING id", (beta_id, "Nike Retail"))
    nike_client_id = cur.fetchone()[0]

    print("Seeding Agency Memberships...")
    # Alex = agency_admin in Acme Digital Agency
    cur.execute(
        "INSERT INTO agency_memberships (user_id, agency_id, role) VALUES (%s, %s, 'agency_admin')",
        (alex_id, acme_id)
    )

    # Sarah = agency_member in Acme Digital Agency
    cur.execute(
        "INSERT INTO agency_memberships (user_id, agency_id, role) VALUES (%s, %s, 'agency_member')",
        (sarah_id, acme_id)
    )

    # John = client_user in Acme Digital Agency (Scoped to Starlight Tech)
    cur.execute(
        "INSERT INTO agency_memberships (user_id, agency_id, role, client_id) VALUES (%s, %s, 'client_user', %s)",
        (starlight_user_id, acme_id, starlight_client_id)
    )

    # EDGE CASE PROBE: Alex is also a client_user in Beta Media Group (Scoped to Nike)
    cur.execute(
        "INSERT INTO agency_memberships (user_id, agency_id, role, client_id) VALUES (%s, %s, 'client_user', %s)",
        (alex_id, beta_id, nike_client_id)
    )

    print("Seeding Projects...")
    cur.execute(
        "INSERT INTO projects (agency_id, client_id, name, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (acme_id, starlight_client_id, "Website Redesign", "Rebuilding marketing site")
    )
    acme_project_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO projects (agency_id, client_id, name, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (beta_id, nike_client_id, "Spring Campaign", "Ad campaign deliverables")
    )
    beta_project_id = cur.fetchone()[0]

    # Assign Sarah to Acme project
    cur.execute("INSERT INTO project_members (project_id, user_id) VALUES (%s, %s)", (acme_project_id, sarah_id))

    print("Seeding Tasks (Internal vs Client Visible)...")
    # Task 1: Internal only (Agency staff)
    cur.execute(
        """
        INSERT INTO tasks (agency_id, project_id, title, status, priority, assignee_id, due_date, is_internal)
        VALUES (%s, %s, %s, 'in_progress', 'high', %s, '2026-10-15', TRUE)
        RETURNING id
        """,
        (acme_id, acme_project_id, "DB Query Optimization", sarah_id)
    )
    internal_task_id = cur.fetchone()[0]

    # Task 2: Client visible
    cur.execute(
        """
        INSERT INTO tasks (agency_id, project_id, title, status, priority, assignee_id, due_date, is_internal)
        VALUES (%s, %s, %s, 'review', 'medium', %s, '2026-10-20', FALSE)
        RETURNING id
        """,
        (acme_id, acme_project_id, "Homepage Figma Mockup", sarah_id)
    )
    public_task_id = cur.fetchone()[0]

    print("Seeding Comments, Files & Time Entries...")
    # Comments (Internal vs Public)
    cur.execute(
        "INSERT INTO task_comments (agency_id, task_id, author_id, content, is_internal) VALUES (%s, %s, %s, %s, TRUE)",
        (acme_id, internal_task_id, sarah_id, "Check database indexes before deploying schema.")
    )
    cur.execute(
        "INSERT INTO task_comments (agency_id, task_id, author_id, content, is_internal) VALUES (%s, %s, %s, %s, FALSE)",
        (acme_id, public_task_id, alex_id, "Please review updated design mockups.")
    )

    # File Attachments (One pending approval)
    cur.execute(
        """
        INSERT INTO task_files (agency_id, task_id, uploader_id, file_name, file_url, approval_status, is_internal)
        VALUES (%s, %s, %s, 'homepage_v1.pdf', 'https://example.com/files/homepage_v1.pdf', 'pending', FALSE)
        """,
        (acme_id, public_task_id, sarah_id)
    )
    cur.execute(
        """
        INSERT INTO task_files (agency_id, task_id, uploader_id, file_name, file_url, approval_status, is_internal)
        VALUES (%s, %s, %s, 'internal_schema_notes.pdf', 'https://example.com/files/notes.pdf', 'approved', TRUE)
        """,
        (acme_id, internal_task_id, sarah_id)
    )

    # Time Entries
    cur.execute(
        """
        INSERT INTO time_entries (agency_id, task_id, user_id, duration_minutes, note, entry_date)
        VALUES (%s, %s, %s, 180, 'Built SQL endpoint routes', '2026-09-24')
        """,
        (acme_id, internal_task_id, sarah_id)
    )

    # Pending Invites
    cur.execute(
        """
        INSERT INTO agency_invites (agency_id, email, role, client_id, token, status, expires_at)
        VALUES (%s, 'newcontact@starlight.com', 'client_user', %s, 'invite_token_998877', 'pending', '2026-10-31')
        """,
        (acme_id, starlight_client_id)
    )

    conn.commit()
    cur.close()
    conn.close()
    print("\nDatabase seeded successfully!")
    print("Test Login Credentials (Password for all: password123):")
    print(" - Agency Admin / Dual User: alex@example.com")
    print(" - Agency Member:            sarah@acme.com")
    print(" - Client User:               john@starlight.com")

if __name__ == "__main__":
    seed_database()