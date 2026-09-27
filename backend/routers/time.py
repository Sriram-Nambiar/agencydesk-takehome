from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from schemas import TimeLogRequest
from deps import get_current_user, get_membership, require_task_access

router = APIRouter(prefix="/tasks", tags=["Time Tracking"])


@router.get("/{task_id}/time")
async def get_task_time_entries(task_id: str, request: Request, user_id: str = Depends(get_current_user)):
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


@router.post("/{task_id}/time")
async def log_time(task_id: str, request: Request, payload: TimeLogRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot log time")

        entry_date = payload.entry_date or datetime.utcnow().date()
        note = (payload.note or "")[:1000]
        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                INSERT INTO time_entries (agency_id, task_id, user_id, duration_minutes, note, entry_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, payload.duration_minutes, note, entry_date)
            )
            entry = cur.fetchone()
            conn.commit()
            return entry
    finally:
        conn.close()
