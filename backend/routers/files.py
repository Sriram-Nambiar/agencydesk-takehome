import os
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File as FastAPIFile, Form
from fastapi.responses import FileResponse
from database import get_db
from schemas import FileUploadRequest, FileApprovalRequest
from deps import get_current_user, get_membership, require_task_access, parse_uuid
from services.event_bus import dispatch_file_status_changed
from config import get_settings

router = APIRouter(tags=["Files & Approvals"])


@router.get("/files/{file_id}/download")
async def download_task_file(file_id: str, request: Request, user_id: str = Depends(get_current_user)):
    """Download a stored upload only after checking the caller's task access."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        file_id = parse_uuid(file_id, "File ID")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id, file_name, file_url, is_internal FROM task_files WHERE id = %s AND agency_id = %s",
                (file_id, agency_id),
            )
            file_row = cur.fetchone()
            if not file_row:
                raise HTTPException(status_code=404, detail="File not found")
            task = require_task_access(cur, file_row["task_id"], agency_id, membership)
            if membership["role"] == "client_user" and (task["is_internal"] or file_row["is_internal"]):
                raise HTTPException(status_code=404, detail="File not found")

        stored_url = file_row["file_url"]
        stored_name = stored_url.removeprefix("/uploads/")
        if not stored_url.startswith("/uploads/") or not stored_name or Path(stored_name).name != stored_name:
            raise HTTPException(status_code=404, detail="Stored file not found")
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        resolved_path = (upload_root / stored_name).resolve()
        if resolved_path.parent != upload_root or not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="Stored file not found")
        return FileResponse(resolved_path, filename=Path(file_row["file_name"]).name)
    finally:
        conn.close()


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


@router.post("/tasks/{task_id}/files/upload")
async def upload_task_file_multipart(
    task_id: str,
    request: Request,
    file: UploadFile = FastAPIFile(...),
    is_internal: bool = Form(False),
    user_id: str = Depends(get_current_user),
):
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Clients cannot upload files")

        with conn.cursor() as cur:
            task = require_task_access(cur, task_id, agency_id, membership)
            file_internal = True if task["is_internal"] else is_internal

            upload_dir = get_settings().UPLOAD_DIR
            os.makedirs(upload_dir, exist_ok=True)

            original_filename = file.filename or "uploaded_file"
            file_ext = os.path.splitext(original_filename)[1]
            stored_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join(upload_dir, stored_filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            file_url = f"/uploads/{stored_filename}"

            cur.execute(
                """
                INSERT INTO task_files (agency_id, task_id, uploader_id, file_name, file_url, approval_status, is_internal)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, original_filename, file_url, file_internal),
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
            if not file_row:
                raise HTTPException(status_code=404, detail="File not found or not accessible")
            if membership["role"] == "client_user" and file_row["is_internal"]:
                raise HTTPException(status_code=404, detail="File not found or not accessible")
            require_task_access(cur, file_row["task_id"], agency_id, membership)
            if membership["role"] == "agency_member":
                raise HTTPException(status_code=403, detail="Only clients and agency admins can approve files")
            internal_filter = "AND is_internal = FALSE" if membership["role"] == "client_user" else ""
            cur.execute(
                f"""
                UPDATE task_files
                SET approval_status = %s
                WHERE id = %s AND agency_id = %s {internal_filter}
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
