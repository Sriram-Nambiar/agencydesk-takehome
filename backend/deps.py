import os
import re
from uuid import UUID
from datetime import date
from fastapi import Request, HTTPException
from passlib.context import CryptContext
from jose import jwt, JWTError

SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
if not SECRET_KEY and os.getenv("ENVIRONMENT") == "production":
    raise RuntimeError("SECRET_KEY must be configured in production")
SECRET_KEY = SECRET_KEY or "dev-only-change-me-before-deploying"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def parse_uuid(value, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid UUID")


def parse_optional_date(value, field_name: str):
    if value in (None, ""):
        return None
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("date must use ISO format")
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid YYYY-MM-DD date")


def get_current_user(request: Request) -> str:
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


def require_project_access(cur, project_id, agency_id: str, membership: dict):
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


def require_task_access(cur, task_id, agency_id: str, membership: dict):
    task_id = parse_uuid(task_id, "Task ID")
    cur.execute("SELECT project_id, is_internal FROM tasks WHERE id = %s AND agency_id = %s", (task_id, agency_id))
    task = cur.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    require_project_access(cur, task["project_id"], agency_id, membership)
    if membership["role"] == "client_user" and task["is_internal"]:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
