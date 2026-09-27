from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from deps import get_current_user, get_membership, require_project_access, parse_uuid

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("")
async def list_agency_projects(request: Request, user_id: str = Depends(get_current_user)):
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


@router.get("/{project_id}")
async def get_agency_project(project_id: str, request: Request, user_id: str = Depends(get_current_user)):
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

            # Per-project dashboard: task counts by status & hours logged
            cur.execute(
                """
                SELECT status, COUNT(*) as count
                FROM tasks
                WHERE project_id = %s AND agency_id = %s
                GROUP BY status
                """,
                (project_id, agency_id)
            )
            task_counts_by_status = {row["status"]: row["count"] for row in cur.fetchall()}
            for s in ('todo', 'in_progress', 'review', 'done'):
                task_counts_by_status.setdefault(s, 0)

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
                "task_counts_by_status": task_counts_by_status,
                "total_hours_logged": round(time_summary["total_minutes"] / 60.0, 2)
            }
    finally:
        conn.close()


@router.delete("/{project_id}/members/{member_id}")
async def remove_project_member(
    project_id: str,
    member_id: str,
    request: Request,
    unassign_active: bool = True,
    user_id: str = Depends(get_current_user)
):
    """Revoke access and return active tasks to the backlog by default."""
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
            unassigned_count = 0
            if unassign_active:
                cur.execute(
                    """
                    UPDATE tasks
                    SET assignee_id = NULL
                    WHERE project_id = %s AND agency_id = %s AND assignee_id = %s AND status != 'done'
                    """,
                    (project["id"], agency_id, member_id)
                )
                unassigned_count = cur.rowcount
            conn.commit()
            return {
                "project_id": project_id,
                "member_id": member_id,
                "access": "removed",
                "unassigned_tasks": unassigned_count
            }
    finally:
        conn.close()


@router.put("/{project_id}/members/{member_id}")
async def add_project_member(project_id: str, member_id: str, request: Request, user_id: str = Depends(get_current_user)):
    """Assign an active agency member to a project; repeating the request is safe."""
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
