from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from deps import get_current_user, get_membership, require_project_access

router = APIRouter(prefix="/portal/projects", tags=["Client Portal"])


@router.get("")
async def list_client_projects(request: Request, user_id: str = Depends(get_current_user)):
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


@router.get("/{project_id}")
async def get_client_project(project_id: str, request: Request, user_id: str = Depends(get_current_user)):
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

            # Client dashboard: task counts strictly scoped to public client-visible deliverables
            cur.execute(
                """
                SELECT status, COUNT(*) as count
                FROM tasks
                WHERE project_id = %s AND agency_id = %s AND is_internal = FALSE
                GROUP BY status
                """,
                (project_id, agency_id)
            )
            task_counts_by_status = {row["status"]: row["count"] for row in cur.fetchall()}
            for s in ('todo', 'in_progress', 'review', 'done'):
                task_counts_by_status.setdefault(s, 0)

            return {
                "project": project,
                "tasks": client_tasks,
                "task_counts_by_status": task_counts_by_status
            }
    finally:
        conn.close()
