import json
from fastapi import APIRouter, Request, HTTPException, Depends
from database import get_db
from schemas import AutomationCreateRequest, AutomationUpdateRequest
from deps import get_current_user, get_membership, parse_uuid

router = APIRouter(prefix="/automations", tags=["Automations"])


@router.get("")
async def list_automations(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """List all automation rules configured for the active agency tenant."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot view agency automations")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, agency_id, name, trigger_event, action_type, action_config, is_enabled, created_at
                FROM automations
                WHERE agency_id = %s
                ORDER BY created_at ASC
                """,
                (agency_id,)
            )
            return {"automations": cur.fetchall()}
    finally:
        conn.close()


@router.post("")
async def create_automation(
    request: Request,
    payload: AutomationCreateRequest,
    user_id: str = Depends(get_current_user),
):
    """Create a new automation rule for the agency (agency_admin only)."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins can configure automations")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO automations (agency_id, name, trigger_event, action_type, action_config, is_enabled)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    agency_id,
                    payload.name,
                    payload.trigger_event,
                    payload.action_type,
                    json.dumps(payload.action_config),
                    payload.is_enabled,
                )
            )
            created = cur.fetchone()
            conn.commit()
            return created
    finally:
        conn.close()


@router.patch("/{automation_id}")
async def update_automation(
    automation_id: str,
    request: Request,
    payload: AutomationUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Update or toggle an automation rule (agency_admin only)."""
    agency_id = request.headers.get("x-agency-id")
    auto_uuid = parse_uuid(automation_id, "Automation ID")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins can modify automations")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM automations WHERE id = %s AND agency_id = %s",
                (auto_uuid, agency_id)
            )
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Automation not found")

            new_name = payload.name if payload.name is not None else existing["name"]
            new_enabled = payload.is_enabled if payload.is_enabled is not None else existing["is_enabled"]
            new_config = json.dumps(payload.action_config) if payload.action_config is not None else json.dumps(existing["action_config"])

            cur.execute(
                """
                UPDATE automations
                SET name = %s, is_enabled = %s, action_config = %s
                WHERE id = %s AND agency_id = %s
                RETURNING *
                """,
                (new_name, new_enabled, new_config, auto_uuid, agency_id)
            )
            updated = cur.fetchone()
            conn.commit()
            return updated
    finally:
        conn.close()


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Delete an automation rule (agency_admin only)."""
    agency_id = request.headers.get("x-agency-id")
    auto_uuid = parse_uuid(automation_id, "Automation ID")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins can delete automations")

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM automations WHERE id = %s AND agency_id = %s RETURNING id",
                (auto_uuid, agency_id)
            )
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Automation not found")
            conn.commit()
            return {"success": True, "deleted_id": str(auto_uuid)}
    finally:
        conn.close()
