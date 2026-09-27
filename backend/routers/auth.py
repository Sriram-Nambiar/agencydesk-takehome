import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
from jose import jwt

from database import get_db
from schemas import RegisterRequest, LoginRequest
from deps import SECRET_KEY, ALGORITHM, pwd_context, get_current_user
from rate_limiter import rate_limit
from config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

settings = get_settings()
AUTH_RATE_LIMIT_LOGIN = settings.AUTH_RATE_LIMIT_LOGIN
AUTH_RATE_LIMIT_REGISTER = settings.AUTH_RATE_LIMIT_REGISTER


@router.post("/register", dependencies=[Depends(rate_limit(limit=AUTH_RATE_LIMIT_REGISTER, window_seconds=60))])
async def register(payload: RegisterRequest):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Check user exists
            email_normalized = payload.email.strip().lower()
            cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (email_normalized,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create User
            hashed_pw = pwd_context.hash(payload.password)
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
                (email_normalized, hashed_pw, payload.full_name)
            )
            user_id = cur.fetchone()["id"]

            # Create Agency
            cur.execute("INSERT INTO agencies (name) VALUES (%s) RETURNING id", (payload.agency_name,))
            agency_id = cur.fetchone()["id"]

            # Create default starter client for the agency
            cur.execute("INSERT INTO clients (agency_id, name) VALUES (%s, %s)", (agency_id, "General Client"))

            # Create Membership as Admin
            cur.execute(
                "INSERT INTO agency_memberships (user_id, agency_id, role) VALUES (%s, %s, 'agency_admin')",
                (user_id, agency_id)
            )
            conn.commit()

            token = jwt.encode({"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": token, "user_id": user_id, "active_agency_id": agency_id}
    finally:
        conn.close()


@router.post("/login", dependencies=[Depends(rate_limit(limit=AUTH_RATE_LIMIT_LOGIN, window_seconds=60))])
async def login(payload: LoginRequest):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE lower(email) = lower(%s)", (payload.email,))
            user = cur.fetchone()
            if not user or not pwd_context.verify(payload.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            token = jwt.encode({"sub": str(user["id"]), "exp": datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)
            return {"token": token, "user_id": user["id"]}
    finally:
        conn.close()


@router.get("/me")
async def get_current_user_profile(user_id: str = Depends(get_current_user)):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, full_name, created_at FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return user
    finally:
        conn.close()


@router.get("/memberships")
async def get_user_memberships(user_id: str = Depends(get_current_user)):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.agency_id, a.name as agency_name, m.role, m.client_id
                FROM agency_memberships m
                JOIN agencies a ON a.id = m.agency_id
                WHERE m.user_id = %s AND m.removed_at IS NULL
                """,
                (user_id,)
            )
            return {"memberships": cur.fetchall()}
    finally:
        conn.close()
