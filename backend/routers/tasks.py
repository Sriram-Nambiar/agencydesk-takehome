from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from schemas import TaskCreateRequest, TaskStatusUpdateRequest, TaskVisibilityUpdateRequest
from deps import get_current_user, get_membership, require_project_access, require_task_access
from services.event_bus import dispatch_task_created, dispatch_task_status_changed
from services.audit import record_audit_event

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("")
async def create_task(request: Request, payload: TaskCreateRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot create tasks")

        with conn.cursor() as cur:
            project = require_project_access(cur, payload.project_id, agency_id, membership)
            assignee_id = str(payload.assignee_id) if payload.assignee_id else None
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
            cur.execute(
                """
                INSERT INTO tasks (agency_id, project_id, title, status, priority, assignee_id, due_date, is_internal)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    agency_id,
                    project["id"],
                    payload.title,
                    payload.status,
                    payload.priority,
                    assignee_id,
                    payload.due_date,
                    payload.is_internal
                )
            )
            task = cur.fetchone()
            dispatch_task_created(cur, agency_id, task, user_id)
            conn.commit()
            return task
    finally:
        conn.close()


@router.patch("/{task_id}/status")
async def update_task_status(task_id: str, request: Request, payload: TaskStatusUpdateRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot change task status")

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                "UPDATE tasks SET status = %s WHERE id = %s AND agency_id = %s RETURNING id, status",
                (payload.status, task_id, agency_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Task not found in tenant")
            dispatch_task_status_changed(cur, agency_id, task_id, payload.status, user_id)
            conn.commit()
            return updated
    finally:
        conn.close()


@router.patch("/{task_id}/visibility")
async def update_task_visibility(
    task_id: str,
    request: Request,
    payload: TaskVisibilityUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Toggle whether a task is internal (agency-only) or client-visible."""
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot change task visibility")

        with conn.cursor() as cur:
            task = require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                UPDATE tasks
                SET is_internal = %s
                WHERE id = %s AND agency_id = %s
                RETURNING id, is_internal
                """,
                (payload.is_internal, task_id, agency_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Task not found in tenant")

            # Cascade: if task made internal, ensure child comments and files are forced internal
            if payload.is_internal:
                cur.execute(
                    "UPDATE task_comments SET is_internal = TRUE WHERE task_id = %s AND agency_id = %s",
                    (task_id, agency_id)
                )
                cur.execute(
                    "UPDATE task_files SET is_internal = TRUE WHERE task_id = %s AND agency_id = %s",
                    (task_id, agency_id)
                )

            record_audit_event(
                cur,
                agency_id=agency_id,
                actor_id=user_id,
                action="task.visibility_changed",
                entity_type="task",
                entity_id=task_id,
                details={"from_internal": task["is_internal"], "to_internal": payload.is_internal},
            )

            conn.commit()
            return updated
    finally:
        conn.close()
