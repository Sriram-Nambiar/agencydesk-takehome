from fastapi import APIRouter, Request, Depends
from database import get_db
from schemas import CommentCreateRequest
from deps import get_current_user, get_membership, require_task_access
from services.event_bus import dispatch_comment_created

router = APIRouter(prefix="/tasks", tags=["Comments"])


@router.get("/{task_id}/comments")
async def get_comments(task_id: str, request: Request, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
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


@router.post("/{task_id}/comments")
async def add_comment(task_id: str, request: Request, payload: CommentCreateRequest, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        # Force client comments to always be public
        is_internal = False if membership["role"] == "client_user" else payload.is_internal

        with conn.cursor() as cur:
            require_task_access(cur, task_id, agency_id, membership)
            cur.execute(
                """
                INSERT INTO task_comments (agency_id, task_id, author_id, content, is_internal)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agency_id, task_id, user_id, payload.content, is_internal)
            )
            comment = cur.fetchone()
            dispatch_comment_created(
                cur=cur,
                agency_id=agency_id,
                task_id=task_id,
                comment=comment,
                author_id=user_id,
                is_client=(membership["role"] == "client_user"),
            )
            conn.commit()
            return comment
    finally:
        conn.close()
