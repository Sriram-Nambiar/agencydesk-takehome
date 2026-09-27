from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from schemas import FileUploadRequest, FileApprovalRequest
from deps import get_current_user, get_membership, require_task_access, parse_uuid
from services.event_bus import dispatch_file_status_changed

router = APIRouter(tags=["Files & Approvals"])


@router.get("/tasks/{task_id}/files")
async def get_task_files(task_id: str, request: Request, user_id: str = Depends(get_current_user)):
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


@router.post("/tasks/{task_id}/files")
async def upload_task_file(task_id: str, request: Request, payload: FileUploadRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Clients cannot upload files")

        with conn.cursor() as cur:
            task = require_task_access(cur, task_id, agency_id, membership)
            is_internal = True if task["is_internal"] else payload.is_internal
            cur.execute(
                """
                INSERT INTO task_files (agency_id, task_id, uploader_id, file_name, file_url, approval_status, is_internal)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, payload.file_name, payload.file_url, is_internal)
            )
            file_entry = cur.fetchone()
            conn.commit()
            return file_entry
    finally:
        conn.close()


@router.patch("/files/{file_id}/approval")
async def update_file_approval(file_id: str, request: Request, payload: FileApprovalRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
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
                (payload.approval_status, file_id, agency_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="File not found or not accessible")
            dispatch_file_status_changed(
                cur=cur,
                agency_id=agency_id,
                file_id=str(file_id),
                approval_status=payload.approval_status,
                actor_id=user_id,
            )
            conn.commit()
            return updated
    finally:
        conn.close()
