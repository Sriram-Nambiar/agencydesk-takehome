import os
import secrets
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, date, timedelta
from uuid import UUID
import uuid
from dotenv import load_dotenv

load_dotenv()

# Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "agencydesk")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "devpass")
DB_PORT = os.getenv("DB_PORT", "5432")

from contextlib import asynccontextmanager
from database import get_db, get_connection_pool, close_connection_pool

SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
if not SECRET_KEY and os.getenv("ENVIRONMENT") == "production":
    raise RuntimeError("SECRET_KEY must be configured in production")
SECRET_KEY = SECRET_KEY or "dev-only-change-me-before-deploying"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pool on startup
    get_connection_pool()
    yield
    # Gracefully drain and close connection pool on shutdown
    close_connection_pool()


app = FastAPI(title="AgencyDesk Flat Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/healthz", tags=["Health"])
def liveness_probe():
    """Liveness probe: returns 200 when application process is running."""
    return {"status": "ok", "service": "agencydesk-api"}


@app.get("/readyz", tags=["Health"])
def readiness_probe():
    """Readiness probe: validates live PostgreSQL database connection."""
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


def get_current_user(request: Request):
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Token verification failed")

def get_membership(conn, user_id: str, agency_id: str):
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")
    agency_id = parse_uuid(agency_id, "Agency ID")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, role, client_id
            FROM agency_memberships
            WHERE user_id = %s AND agency_id = %s AND removed_at IS NULL
            """,
            (user_id, agency_id)
        )
        membership = cur.fetchone()
        if not membership:
            raise HTTPException(status_code=403, detail="Access denied to this agency tenant")
        return membership


def parse_uuid(value, field_name):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid UUID")


def require_project_access(cur, project_id, agency_id, membership):
    project_id = parse_uuid(project_id, "Project ID")
    cur.execute("SELECT * FROM projects WHERE id = %s AND agency_id = %s", (project_id, agency_id))
    project = cur.fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if membership["role"] == "client_user":
        if not membership["client_id"] or project["client_id"] != membership["client_id"]:
            raise HTTPException(status_code=404, detail="Project not found")
    elif membership["role"] == "agency_member":
        cur.execute("SELECT 1 FROM project_members WHERE project_id = %s AND user_id = %s", (project_id, membership["user_id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_task_access(cur, task_id, agency_id, membership):
    task_id = parse_uuid(task_id, "Task ID")
    cur.execute("SELECT project_id, is_internal FROM tasks WHERE id = %s AND agency_id = %s", (task_id, agency_id))
    task = cur.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    require_project_access(cur, task["project_id"], agency_id, membership)
    if membership["role"] == "client_user" and task["is_internal"]:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def parse_optional_date(value, field_name):
    if value in (None, ""):
        return None
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("date must use ISO format")
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid YYYY-MM-DD date")


# -------------------------------------------------------------------
# AUTH & AGENCY SWITCHING ENDPOINTS
# -------------------------------------------------------------------

@app.post("/auth/register")
async def register(request: Request):
    data = await request.json()
    raw_email = data.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    password = data.get("password")
    full_name = data.get("full_name")
    agency_name = data.get("agency_name")

    if not email or len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not isinstance(password, str) or len(password) < 8 or len(password) > 72 or not (full_name or "").strip() or not (agency_name or "").strip():
        raise HTTPException(status_code=400, detail="Missing required fields")
    full_name = full_name.strip()
    agency_name = agency_name.strip()

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Check user exists
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create User
            hashed_pw = pwd_context.hash(password)
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
                (email, hashed_pw, full_name)
            )
            user_id = cur.fetchone()["id"]

            # Create Agency
            cur.execute("INSERT INTO agencies (name) VALUES (%s) RETURNING id", (agency_name,))
            agency_id = cur.fetchone()["id"]

            # Create Membership as Admin
            cur.execute(
                "INSERT INTO agency_memberships (user_id, agency_id, role) VALUES (%s, %s, 'agency_admin')",
                (user_id, agency_id)
            )
            conn.commit()

            token = jwt.encode({"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": token, "user_id": user_id, "active_agency_id": agency_id}
    finally:
        conn.close()


@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    raw_email = data.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    password = data.get("password")
    if not email or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Email and password are required")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user or not pwd_context.verify(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            token = jwt.encode({"sub": str(user["id"]), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": token, "user_id": user["id"]}
    finally:
        conn.close()


@app.get("/auth/me")
async def get_current_user_profile(request: Request):
    user_id = get_current_user(request)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, full_name, created_at FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return user
    finally:
        conn.close()


@app.get("/auth/memberships")
async def get_user_memberships(request: Request):
    user_id = get_current_user(request)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.agency_id, a.name as agency_name, m.role, m.client_id
                FROM agency_memberships m
                JOIN agencies a ON a.id = m.agency_id
                WHERE m.user_id = %s AND m.removed_at IS NULL
                """,
                (user_id,)
            )
            return {"memberships": cur.fetchall()}
    finally:
        conn.close()


# -------------------------------------------------------------------
# AGENCY WORKSPACE VIEW (/projects/{id})
# -------------------------------------------------------------------

@app.get("/projects")
async def list_agency_projects(request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users must use /portal endpoints")

        with conn.cursor() as cur:
            project_filter = "AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.id AND pm.user_id = %s)" if membership["role"] == "agency_member" else ""
            cur.execute(
                f"""
                SELECT p.*, c.name as client_name,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s) as task_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s AND t.status = 'done') as completed_task_count,
                       (SELECT COALESCE(SUM(te.duration_minutes), 0) FROM time_entries te WHERE te.task_id IN (SELECT t.id FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s)) as total_minutes
                FROM projects p
                JOIN clients c ON c.id = p.client_id
                WHERE p.agency_id = %s {project_filter}
                ORDER BY p.created_at DESC
                """,
                (agency_id, agency_id, agency_id, agency_id, *([user_id] if project_filter else []))
            )
            projects = cur.fetchall()
            for p in projects:
                p["total_hours_logged"] = round((p.get("total_minutes") or 0) / 60.0, 2)
            return {"projects": projects}
    finally:
        conn.close()


@app.get("/projects/{project_id}")
async def get_agency_project(project_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users must use /portal endpoints")

        with conn.cursor() as cur:
            project = require_project_access(cur, project_id, agency_id, membership)

            # Fetch all tasks (both internal and client-visible)
            cur.execute(
                """
                SELECT t.*, u.full_name as assignee_name
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id = u.id
                WHERE t.project_id = %s AND t.agency_id = %s
                """,
                (project_id, agency_id)
            )
            tasks = cur.fetchall()

            # Per-project stats summary
            cur.execute(
                """
                SELECT COALESCE(SUM(duration_minutes), 0) as total_minutes
                FROM time_entries
                WHERE task_id IN (SELECT id FROM tasks WHERE project_id = %s AND agency_id = %s)
                """,
                (project_id, agency_id)
            )
            time_summary = cur.fetchone()

            return {
                "project": project,
                "tasks": tasks,
                "total_hours_logged": round(time_summary["total_minutes"] / 60.0, 2)
            }
    finally:
        conn.close()


# -------------------------------------------------------------------
# CLIENT PORTAL VIEW (/portal/projects/{id}) - LEAK SHIELD ENFORCED
# -------------------------------------------------------------------

@app.get("/portal/projects")
async def list_client_projects(request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            if membership["role"] == "client_user":
                if not membership["client_id"]:
                    return {"projects": []}
                cur.execute(
                    """
                    SELECT p.*, c.name as client_name,
                           (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s AND t.is_internal = FALSE) as task_count,
                           (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s AND t.is_internal = FALSE AND t.status = 'done') as completed_task_count
                    FROM projects p
                    JOIN clients c ON c.id = p.client_id
                    WHERE p.agency_id = %s AND p.client_id = %s
                    ORDER BY p.created_at DESC
                    """,
                    (agency_id, agency_id, agency_id, membership["client_id"])
                )
            else:
                project_filter = "AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.id AND pm.user_id = %s)" if membership["role"] == "agency_member" else ""
                cur.execute(
                    f"""
                    SELECT p.*, c.name as client_name,
                           (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s) as task_count,
                           (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.agency_id = %s AND t.status = 'done') as completed_task_count
                    FROM projects p
                    JOIN clients c ON c.id = p.client_id
                    WHERE p.agency_id = %s {project_filter}
                    ORDER BY p.created_at DESC
                    """,
                    (agency_id, agency_id, agency_id, *([user_id] if project_filter else []))
                )
            return {"projects": cur.fetchall()}
    finally:
        conn.close()


@app.get("/portal/projects/{project_id}")
async def get_client_project(project_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)

        with conn.cursor() as cur:
            project = require_project_access(cur, project_id, agency_id, membership)

            # FETCH TASKS STRICTLY FILTERING OUT INTERNAL TASKS
            cur.execute(
                """
                SELECT id, title, status, priority, due_date, created_at
                FROM tasks
                WHERE project_id = %s AND agency_id = %s AND is_internal = FALSE
                """,
                (project_id, agency_id)
            )
            client_tasks = cur.fetchall()

            return {
                "project": project,
                "tasks": client_tasks
            }
    finally:
        conn.close()


# -------------------------------------------------------------------
# TASK CREATION & STATUS UPDATES
# -------------------------------------------------------------------

@app.post("/tasks")
async def create_task(request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot create tasks")

        with conn.cursor() as cur:
            project = require_project_access(cur, data.get("project_id"), agency_id, membership)
            raw_title = data.get("title")
            title = raw_title.strip() if isinstance(raw_title, str) else ""
            if not title or len(title) > 240:
                raise HTTPException(status_code=400, detail="Task title is required and must be under 240 characters")
            if not isinstance(data.get("status", "todo"), str) or data.get("status", "todo") not in {"todo", "in_progress", "review", "done"}:
                raise HTTPException(status_code=400, detail="Invalid task status")
            if not isinstance(data.get("priority", "medium"), str) or data.get("priority", "medium") not in {"low", "medium", "high", "urgent"}:
                raise HTTPException(status_code=400, detail="Invalid task priority")
            assignee_id = data.get("assignee_id")
            if assignee_id:
                assignee_id = parse_uuid(assignee_id, "Assignee ID")
            due_date = parse_optional_date(data.get("due_date"), "Due date")
            if assignee_id:
                cur.execute("SELECT 1 FROM agency_memberships WHERE user_id=%s AND agency_id=%s AND role IN ('agency_admin','agency_member') AND removed_at IS NULL", (assignee_id, agency_id))
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail="Assignee must be an active agency member")
                cur.execute("SELECT 1 FROM project_members WHERE project_id=%s AND user_id=%s", (project["id"], assignee_id))
                if not cur.fetchone():
                    if membership["role"] != "agency_admin":
                        raise HTTPException(status_code=400, detail="Assignee must be assigned to this project")
                    cur.execute("INSERT INTO project_members (project_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (project["id"], assignee_id))
                if membership["role"] == "agency_member" and assignee_id != user_id:
                    raise HTTPException(status_code=403, detail="Members may only assign tasks to themselves")
            is_internal = data.get("is_internal", False)
            if not isinstance(is_internal, bool):
                raise HTTPException(status_code=400, detail="is_internal must be true or false")
            cur.execute(
                """
                INSERT INTO tasks (agency_id, project_id, title, status, priority, assignee_id, due_date, is_internal)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    agency_id,
                    project["id"],
                    title,
                    data.get("status", "todo"),
                    data.get("priority", "medium"),
                    assignee_id,
                    due_date,
                    is_internal
                )
            )
            task = cur.fetchone()
            conn.commit()
            return task
    finally:
        conn.close()


@app.patch("/tasks/{task_id}/status")
async def update_task_status(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()
    new_status = data.get("status")
    if not isinstance(new_status, str) or new_status not in {"todo", "in_progress", "review", "done"}:
        raise HTTPException(status_code=400, detail="Invalid task status")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot change task status")

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                "UPDATE tasks SET status = %s WHERE id = %s AND agency_id = %s RETURNING id, status",
                (new_status, task_id, agency_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Task not found in tenant")
            conn.commit()
            return updated
    finally:
        conn.close()


# -------------------------------------------------------------------
# TASK MODAL: COMMENTS, TIME ENTRIES, FILES & APPROVALS
# -------------------------------------------------------------------

@app.get("/tasks/{task_id}/comments")
async def get_comments(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            # Query filter based on role
            if membership["role"] == "client_user":
                query = """
                    SELECT c.*, u.full_name as author_name
                    FROM task_comments c
                    JOIN users u ON c.author_id = u.id
                    WHERE c.task_id = %s AND c.agency_id = %s AND c.is_internal = FALSE
                    ORDER BY c.created_at ASC
                """
            else:
                query = """
                    SELECT c.*, u.full_name as author_name
                    FROM task_comments c
                    JOIN users u ON c.author_id = u.id
                    WHERE c.task_id = %s AND c.agency_id = %s
                    ORDER BY c.created_at ASC
                """
            cur.execute(query, (task_id, agency_id))
            return {"comments": cur.fetchall()}
    finally:
        conn.close()


@app.post("/tasks/{task_id}/comments")
async def add_comment(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        raw_content = data.get("content")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        if not content or len(content) > 5000:
            raise HTTPException(status_code=400, detail="Comment must contain 1 to 5000 characters")
        is_internal = data.get("is_internal", False)
        if not isinstance(is_internal, bool):
            raise HTTPException(status_code=400, detail="is_internal must be true or false")

        # Force client comments to always be public
        if membership["role"] == "client_user":
            is_internal = False

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                INSERT INTO task_comments (agency_id, task_id, author_id, content, is_internal)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, content, is_internal)
            )
            comment = cur.fetchone()
            conn.commit()
            return comment
    finally:
        conn.close()


@app.post("/tasks/{task_id}/time")
async def log_time(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot log time")

        duration = data.get("duration_minutes")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 1440:
            raise HTTPException(status_code=400, detail="Duration must be a whole number from 1 to 1440 minutes")
        entry_date = parse_optional_date(data.get("entry_date"), "Entry date") or datetime.utcnow().date()
        note = data.get("note") or ""
        if not isinstance(note, str):
            raise HTTPException(status_code=400, detail="Note must be text")
        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                INSERT INTO time_entries (agency_id, task_id, user_id, duration_minutes, note, entry_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, duration, note[:1000], entry_date)
            )
            entry = cur.fetchone()
            conn.commit()
            return entry
    finally:
        conn.close()


@app.patch("/files/{file_id}/approval")
async def update_file_approval(file_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()
    status_choice = data.get("approval_status")

    if status_choice not in ["approved", "needs_changes"]:
        raise HTTPException(status_code=400, detail="Status must be approved or needs_changes")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            file_id = parse_uuid(file_id, "File ID")
            cur.execute("SELECT task_id, is_internal FROM task_files WHERE id = %s AND agency_id = %s", (file_id, agency_id))
            file_row = cur.fetchone()
            if not file_row or file_row["is_internal"]:
                raise HTTPException(status_code=404, detail="File not found or not accessible")
            require_task_access(cur, file_row["task_id"], agency_id, membership)
            if membership["role"] == "agency_member":
                raise HTTPException(status_code=403, detail="Only clients and agency admins can approve files")
            cur.execute(
                """
                UPDATE task_files
                SET approval_status = %s
                WHERE id = %s AND agency_id = %s AND is_internal = FALSE
                RETURNING id, approval_status
                """,
                (status_choice, file_id, agency_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="File not found or not accessible")
            conn.commit()
            return updated
    finally:
        conn.close()


@app.get("/tasks/{task_id}/files")
async def get_task_files(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            if membership["role"] == "client_user":
                query = """
                    SELECT f.*, u.full_name as uploader_name
                    FROM task_files f
                    JOIN users u ON f.uploader_id = u.id
                    WHERE f.task_id = %s AND f.agency_id = %s AND f.is_internal = FALSE
                    ORDER BY f.created_at DESC
                """
            else:
                query = """
                    SELECT f.*, u.full_name as uploader_name
                    FROM task_files f
                    JOIN users u ON f.uploader_id = u.id
                    WHERE f.task_id = %s AND f.agency_id = %s
                    ORDER BY f.created_at DESC
                """
            cur.execute(query, (task_id, agency_id))
            return {"files": cur.fetchall()}
    finally:
        conn.close()


@app.post("/tasks/{task_id}/files")
async def upload_task_file(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Clients cannot upload files")
        requested_internal = data.get("is_internal", False)
        if not isinstance(requested_internal, bool):
            raise HTTPException(status_code=400, detail="is_internal must be true or false")
        is_internal = requested_internal

        raw_file_name, raw_file_url = data.get("file_name"), data.get("file_url")
        file_name = raw_file_name.strip() if isinstance(raw_file_name, str) else ""
        file_url = raw_file_url.strip() if isinstance(raw_file_url, str) else ""
        if not file_name or len(file_name) > 255 or not file_url or len(file_url) > 2000 or not file_url.startswith(("https://", "http://")):
            raise HTTPException(status_code=400, detail="Provide a valid file name and http(s) URL")

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                INSERT INTO task_files (agency_id, task_id, uploader_id, file_name, file_url, approval_status, is_internal)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, file_name, file_url, is_internal)
            )
            file_entry = cur.fetchone()
            conn.commit()
            return file_entry
    finally:
        conn.close()


@app.get("/tasks/{task_id}/time")
async def get_task_time_entries(task_id: str, request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot view time entries")

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                SELECT te.*, u.full_name as user_name
                FROM time_entries te
                JOIN users u ON te.user_id = u.id
                WHERE te.task_id = %s AND te.agency_id = %s
                ORDER BY te.entry_date DESC, te.created_at DESC
                """,
                (task_id, agency_id)
            )
            return {"time_entries": cur.fetchall()}
    finally:
        conn.close()


@app.get("/agency/members")
async def get_agency_members(request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot view agency staff directory")
        with conn.cursor() as cur:
            member_filter = "AND EXISTS (SELECT 1 FROM project_members pm1 JOIN project_members pm2 ON pm1.project_id = pm2.project_id WHERE pm1.user_id = %s AND pm2.user_id = m.user_id)" if membership["role"] == "agency_member" else ""
            cur.execute(
                f"""
                SELECT u.id, u.full_name, u.email, m.role
                FROM agency_memberships m
                JOIN users u ON m.user_id = u.id
                WHERE m.agency_id = %s AND m.removed_at IS NULL AND m.role IN ('agency_admin', 'agency_member') {member_filter}
                ORDER BY u.full_name ASC
                """,
                (agency_id, *([user_id] if member_filter else []))
            )
            return {"members": cur.fetchall()}
    finally:
        conn.close()


@app.get("/agency/clients")
async def get_agency_clients(request: Request):
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            if membership["role"] == "client_user":
                cur.execute("SELECT id, name FROM clients WHERE id = %s AND agency_id = %s", (membership["client_id"], agency_id))
            elif membership["role"] == "agency_member":
                cur.execute("""SELECT DISTINCT c.id, c.name FROM clients c JOIN projects p ON p.client_id=c.id
                               JOIN project_members pm ON pm.project_id=p.id
                               WHERE c.agency_id=%s AND pm.user_id=%s ORDER BY c.name ASC""", (agency_id, user_id))
            else:
                cur.execute("SELECT id, name FROM clients WHERE agency_id = %s ORDER BY name ASC", (agency_id,))
            return {"clients": cur.fetchall()}
    finally:
        conn.close()


@app.delete("/projects/{project_id}/members/{member_id}")
async def remove_project_member(project_id: str, member_id: str, request: Request):
    """Revoke project access immediately while retaining task assignment history."""
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins can remove project members")
        with conn.cursor() as cur:
            project = require_project_access(cur, project_id, agency_id, membership)
            member_id = parse_uuid(member_id, "Member ID")
            cur.execute("SELECT 1 FROM agency_memberships WHERE user_id=%s AND agency_id=%s AND role='agency_member' AND removed_at IS NULL", (member_id, agency_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Agency member not found")
            cur.execute("DELETE FROM project_members WHERE project_id=%s AND user_id=%s", (project["id"], member_id))
            conn.commit()
            return {"project_id": project_id, "member_id": member_id, "access": "removed"}
    finally:
        conn.close()


@app.put("/projects/{project_id}/members/{member_id}")
async def add_project_member(project_id: str, member_id: str, request: Request):
    """Assign an active agency member to a project; repeating the request is safe."""
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins can assign project members")
        project_id = parse_uuid(project_id, "Project ID")
        member_id = parse_uuid(member_id, "Member ID")
        with conn.cursor() as cur:
            require_project_access(cur, project_id, agency_id, membership)
            cur.execute("SELECT 1 FROM agency_memberships WHERE user_id=%s AND agency_id=%s AND role='agency_member' AND removed_at IS NULL", (member_id, agency_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Active agency member not found")
            cur.execute("INSERT INTO project_members (project_id, user_id) VALUES (%s, %s) ON CONFLICT (project_id, user_id) DO NOTHING", (project_id, member_id))
            conn.commit()
            return {"project_id": project_id, "member_id": member_id, "access": "assigned"}
    finally:
        conn.close()


@app.post("/agency/invites")
async def create_or_resend_invite(request: Request):
    """Create or safely resend a pending invite; only agency admins may invite."""
    user_id = get_current_user(request)
    agency_id = request.headers.get("x-agency-id")
    data = await request.json()
    email = (data.get("email") or "").strip().lower()
    role = data.get("role")
    client_id = data.get("client_id")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not isinstance(role, str) or role not in {"agency_admin", "agency_member", "client_user"}:
        raise HTTPException(status_code=400, detail="Provide a valid email and role")
    if (role == "client_user") != bool(client_id):
        raise HTTPException(status_code=400, detail="Client invites require a client; staff invites must not include one")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins may invite users")
        token = secrets.token_urlsafe(32)
        with conn.cursor() as cur:
            if client_id:
                cur.execute("SELECT 1 FROM clients WHERE id=%s AND agency_id=%s", (client_id, agency_id))
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail="Client must belong to this agency")
            cur.execute(
                """INSERT INTO agency_invites (agency_id, email, role, client_id, token, expires_at)
                   VALUES (%s, %s, %s, %s, %s, NOW() + INTERVAL '7 days')
                   ON CONFLICT (agency_id, lower(email)) WHERE status = 'pending'
                   DO UPDATE SET role=EXCLUDED.role, client_id=EXCLUDED.client_id, token=EXCLUDED.token,
                                 expires_at=EXCLUDED.expires_at, created_at=NOW()
                   RETURNING id, agency_id, email, role, client_id, token, expires_at""",
                (agency_id, email, role, client_id, token),
            )
            invite = cur.fetchone()
            conn.commit()
            return {"invite": invite}
    finally:
        conn.close()


@app.post("/invites/accept")
async def accept_invite(request: Request):
    """Accept invite once, reusing a global identity when the email already exists."""
    data = await request.json()
    token = data.get("token")
    password = data.get("password")
    full_name = (data.get("full_name") or "").strip()
    if not isinstance(token, str) or not token or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Invite token and password are required")
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agency_invites WHERE token=%s FOR UPDATE", (token,))
            invite = cur.fetchone()
            if not invite:
                raise HTTPException(status_code=404, detail="Invite not found")
            if invite["status"] == "revoked" or (invite["status"] == "pending" and invite["expires_at"] <= datetime.now(invite["expires_at"].tzinfo)):
                raise HTTPException(status_code=410, detail="Invite expired or revoked")
            cur.execute("SELECT id, password_hash FROM users WHERE lower(email)=lower(%s)", (invite["email"],))
            user = cur.fetchone()
            if user:
                if not pwd_context.verify(password, user["password_hash"]):
                    raise HTTPException(status_code=401, detail="Sign in with the existing account password to accept")
                user_id = user["id"]
            else:
                if len(password) < 8 or len(password) > 72 or not full_name:
                    raise HTTPException(status_code=400, detail="New accounts need a name and a password of 8 to 72 characters")
                cur.execute("INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id", (invite["email"].lower(), pwd_context.hash(password), full_name))
                user_id = cur.fetchone()["id"]
            cur.execute("SELECT role, client_id, removed_at FROM agency_memberships WHERE user_id=%s AND agency_id=%s", (user_id, invite["agency_id"]))
            existing = cur.fetchone()
            if existing and not existing["removed_at"]:
                if existing["role"] != invite["role"] or existing["client_id"] != invite["client_id"]:
                    raise HTTPException(status_code=409, detail="This account already has a different role in the agency")
            elif existing:
                cur.execute("UPDATE agency_memberships SET role=%s, client_id=%s, removed_at=NULL WHERE user_id=%s AND agency_id=%s", (invite["role"], invite["client_id"], user_id, invite["agency_id"]))
            else:
                cur.execute("INSERT INTO agency_memberships (user_id, agency_id, role, client_id) VALUES (%s, %s, %s, %s)", (user_id, invite["agency_id"], invite["role"], invite["client_id"]))
            if invite["status"] == "pending":
                cur.execute("UPDATE agency_invites SET status='accepted' WHERE id=%s", (invite["id"],))
            conn.commit()
            access_token = jwt.encode({"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": access_token, "user_id": user_id, "agency_id": invite["agency_id"], "role": invite["role"]}
    finally:
        conn.close()
