import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
from jose import jwt
from database import get_db
from schemas import InviteCreateRequest, InviteAcceptRequest, ClientCreateRequest
from deps import get_current_user, get_membership, pwd_context, SECRET_KEY, ALGORITHM
from services.audit import record_audit_event

router = APIRouter(tags=["Agency & Invites"])


@router.get("/agency/members")
async def get_agency_members(request: Request, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot view agency staff directory")
        with conn.cursor() as cur:
            member_filter = "AND EXISTS (SELECT 1 FROM project_members pm1 JOIN project_members pm2 ON pm1.project_id = pm2.project_id WHERE pm1.user_id = %s AND pm2.user_id = m.user_id)" if membership["role"] == "agency_member" else ""
            cur.execute(
                f"""
                SELECT u.id, u.full_name, u.email, m.role
                FROM agency_memberships m
                JOIN users u ON m.user_id = u.id
                WHERE m.agency_id = %s AND m.removed_at IS NULL AND m.role IN ('agency_admin', 'agency_member') {member_filter}
                ORDER BY u.full_name ASC
                """,
                (agency_id, *([user_id] if member_filter else []))
            )
            return {"members": cur.fetchall()}
    finally:
        conn.close()


@router.get("/agency/clients")
async def get_agency_clients(request: Request, user_id: str = Depends(get_current_user)):
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        with conn.cursor() as cur:
            if membership["role"] == "client_user":
                cur.execute("SELECT id, name FROM clients WHERE id = %s AND agency_id = %s", (membership["client_id"], agency_id))
            elif membership["role"] == "agency_member":
                cur.execute("""SELECT DISTINCT c.id, c.name FROM clients c JOIN projects p ON p.client_id=c.id
                               JOIN project_members pm ON pm.project_id=p.id
                               WHERE c.agency_id=%s AND pm.user_id=%s ORDER BY c.name ASC""", (agency_id, user_id))
            else:
                cur.execute("SELECT id, name FROM clients WHERE agency_id = %s ORDER BY name ASC", (agency_id,))
            return {"clients": cur.fetchall()}
    finally:
        conn.close()


@router.post("/agency/clients")
async def create_agency_client(request: Request, payload: ClientCreateRequest, user_id: str = Depends(get_current_user)):
    """Create a new client entity in the active agency."""
    agency_id = request.headers.get("x-agency-id")
    if not agency_id:
        raise HTTPException(status_code=400, detail="Missing X-Agency-ID header")

    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] == "client_user":
            raise HTTPException(status_code=403, detail="Client users cannot create clients")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (agency_id, name)
                VALUES (%s, %s)
                RETURNING id, agency_id, name, created_at
                """,
                (agency_id, payload.name)
            )
            client = cur.fetchone()
            record_audit_event(
                cur,
                agency_id=agency_id,
                actor_id=user_id,
                action="client.created",
                entity_type="client",
                entity_id=client["id"],
                details={"name": payload.name},
            )
            conn.commit()
            return {"client": client}
    finally:
        conn.close()


@router.post("/agency/invites")
async def create_or_resend_invite(request: Request, payload: InviteCreateRequest, user_id: str = Depends(get_current_user)):
    """Create or safely resend a pending invite; only agency admins may invite."""
    agency_id = request.headers.get("x-agency-id")
    client_id = str(payload.client_id) if payload.client_id else None
    if (payload.role == "client_user") != bool(client_id):
        raise HTTPException(status_code=400, detail="Client invites require a client; staff invites must not include one")
    conn = get_db()
    try:
        membership = get_membership(conn, user_id, agency_id)
        if membership["role"] != "agency_admin":
            raise HTTPException(status_code=403, detail="Only agency admins may invite users")
        token = secrets.token_urlsafe(32)
        with conn.cursor() as cur:
            if client_id:
                cur.execute("SELECT 1 FROM clients WHERE id=%s AND agency_id=%s", (client_id, agency_id))
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail="Client must belong to this agency")
            cur.execute(
                """INSERT INTO agency_invites (agency_id, email, role, client_id, token, expires_at)
                   VALUES (%s, %s, %s, %s, %s, NOW() + INTERVAL '7 days')
                   ON CONFLICT (agency_id, lower(email)) WHERE status = 'pending'
                   DO UPDATE SET role=EXCLUDED.role, client_id=EXCLUDED.client_id, token=EXCLUDED.token,
                                 expires_at=EXCLUDED.expires_at, created_at=NOW()
                   RETURNING id, agency_id, email, role, client_id, token, expires_at""",
                (agency_id, payload.email, payload.role, client_id, token),
            )
            invite = cur.fetchone()
            conn.commit()
            return {"invite": invite}
    finally:
        conn.close()


@router.post("/invites/accept")
async def accept_invite(payload: InviteAcceptRequest):
    """Accept invite once, reusing a global identity when the email already exists."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agency_invites WHERE token=%s FOR UPDATE", (payload.token,))
            invite = cur.fetchone()
            if not invite:
                raise HTTPException(status_code=404, detail="Invite not found")
            if invite["status"] == "revoked" or (invite["status"] == "pending" and invite["expires_at"] <= datetime.now(invite["expires_at"].tzinfo)):
                raise HTTPException(status_code=410, detail="Invite expired or revoked")
            cur.execute("SELECT id, password_hash FROM users WHERE lower(email)=lower(%s)", (invite["email"],))
            user = cur.fetchone()
            if user:
                if not pwd_context.verify(payload.password, user["password_hash"]):
                    raise HTTPException(status_code=401, detail="Sign in with the existing account password to accept")
                user_id = user["id"]
            else:
                full_name = (payload.full_name or "").strip()
                if len(payload.password) < 8 or len(payload.password) > 72 or not full_name:
                    raise HTTPException(status_code=400, detail="New accounts need a name and a password of 8 to 72 characters")
                cur.execute("INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id", (invite["email"].lower(), pwd_context.hash(payload.password), full_name))
                user_id = cur.fetchone()["id"]
            cur.execute("SELECT id, role, client_id, removed_at FROM agency_memberships WHERE user_id=%s AND agency_id=%s", (user_id, invite["agency_id"]))
            existing = cur.fetchone()
            membership_id = existing["id"] if existing else None
            membership_action = None
            if existing and not existing["removed_at"]:
                if existing["role"] != invite["role"] or existing["client_id"] != invite["client_id"]:
                    raise HTTPException(status_code=409, detail="This account already has a different role in the agency")
            elif existing:
                cur.execute("UPDATE agency_memberships SET role=%s, client_id=%s, removed_at=NULL WHERE user_id=%s AND agency_id=%s RETURNING id", (invite["role"], invite["client_id"], user_id, invite["agency_id"]))
                membership_id = cur.fetchone()["id"]
                membership_action = "membership.reactivated"
            else:
                cur.execute("INSERT INTO agency_memberships (user_id, agency_id, role, client_id) VALUES (%s, %s, %s, %s) RETURNING id", (user_id, invite["agency_id"], invite["role"], invite["client_id"]))
                membership_id = cur.fetchone()["id"]
                membership_action = "membership.created"
            if membership_action:
                record_audit_event(
                    cur,
                    agency_id=invite["agency_id"],
                    actor_id=user_id,
                    action=membership_action,
                    entity_type="membership",
                    entity_id=membership_id,
                    details={"role": invite["role"], "client_id": invite["client_id"]},
                )
            if invite["status"] == "pending":
                cur.execute("UPDATE agency_invites SET status='accepted' WHERE id=%s", (invite["id"],))
            conn.commit()
            access_token = jwt.encode({"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": access_token, "user_id": user_id, "agency_id": invite["agency_id"], "role": invite["role"]}
    finally:
        conn.close()
