from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from deps import get_current_user, get_membership, parse_uuid
from redis_client import get_cached_unread_count, cache_unread_count, invalidate_unread_cache

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def get_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    user_id: str = Depends(get_current_user),
):
    """Retrieve notifications scoped strictly to the current user and active agency tenant."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        # Validate active tenant membership
        get_membership(conn, user_id, agency_id)

        with conn.cursor() as cur:
            if unread_only:
                cur.execute(
                    """
                    SELECT id, agency_id, user_id, title, message, type, entity_type, entity_id, is_read, created_at
                    FROM notifications
                    WHERE agency_id = %s AND user_id = %s AND is_read = FALSE
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (agency_id, user_id, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT id, agency_id, user_id, title, message, type, entity_type, entity_id, is_read, created_at
                    FROM notifications
                    WHERE agency_id = %s AND user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (agency_id, user_id, limit)
                )
            notifications = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) as unread_count FROM notifications WHERE agency_id = %s AND user_id = %s AND is_read = FALSE",
                (agency_id, user_id)
            )
            unread_count = cur.fetchone()["unread_count"]
            cache_unread_count(agency_id, str(user_id), unread_count)

            return {
                "notifications": notifications,
                "unread_count": unread_count,
            }
    finally:
        conn.close()


@router.get("/unread-count")
async def get_unread_notification_count(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Fast Redis-cached endpoint returning the current user's unread notification count."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        # Authorization must run before a cache lookup. Otherwise stale cache
        # data could survive membership revocation and bypass tenant isolation.
        get_membership(conn, user_id, agency_id)

        # 1. Attempt rapid Redis cache lookup
        cached = get_cached_unread_count(agency_id, str(user_id))
        if cached is not None:
            return {"unread_count": cached, "cached": True}

        # 2. Fall back to PostgreSQL count and populate Redis cache
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as unread_count FROM notifications WHERE agency_id = %s AND user_id = %s AND is_read = FALSE",
                (agency_id, user_id)
            )
            count = cur.fetchone()["unread_count"]
            cache_unread_count(agency_id, str(user_id), count)
            return {"unread_count": count, "cached": False}
    finally:
        conn.close()


@router.patch("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Mark a single notification as read."""
    agency_id = request.headers.get("x-agency-id")
    notif_uuid = parse_uuid(notification_id, "Notification ID")

    conn = get_db()
    try:
        get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notifications
                SET is_read = TRUE
                WHERE id = %s AND agency_id = %s AND user_id = %s
                RETURNING *
                """,
                (notif_uuid, agency_id, user_id)
            )
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Notification not found")
            conn.commit()

            invalidate_unread_cache(agency_id, str(user_id))
            return updated
    finally:
        conn.close()


@router.post("/read-all")
async def mark_all_notifications_read(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Mark all unread notifications as read for current user in the active agency."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notifications
                SET is_read = TRUE
                WHERE agency_id = %s AND user_id = %s AND is_read = FALSE
                """,
                (agency_id, user_id)
            )
            count = cur.rowcount
            conn.commit()

            invalidate_unread_cache(agency_id, str(user_id))
            cache_unread_count(agency_id, str(user_id), 0)
            return {"success": True, "marked_count": count}
    finally:
        conn.close()
