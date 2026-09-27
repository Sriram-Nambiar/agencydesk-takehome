import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from database import get_db, get_connection_pool, close_connection_pool
from redis_client import get_redis_pool, close_redis_pool, ping_redis
from deps import (
    get_current_user,
    get_membership,
    require_project_access,
    require_task_access,
    parse_uuid,
    parse_optional_date,
    pwd_context,
    SECRET_KEY,
    ALGORITHM,
)
from routers import (
    auth,
    projects,
    portal,
    tasks,
    comments,
    files,
    time,
    agency,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pools on startup
    get_connection_pool()
    get_redis_pool()
    yield
    # Gracefully drain and close connection pools on shutdown
    close_connection_pool()
    close_redis_pool()


app = FastAPI(
    title="AgencyDesk API",
    description="Multi-tenant agency workspace and client portal API with strict leak-shield boundary enforcement.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0] if exc.errors() else {}
    msg = str(first_error.get("msg", "Validation error"))
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return JSONResponse(status_code=400, content={"detail": msg})


@app.get("/healthz", tags=["Health"])
def liveness_probe():
    """Liveness probe: returns 200 when application process is running."""
    return {"status": "ok", "service": "agencydesk-api"}


@app.get("/readyz", tags=["Health"])
def readiness_probe():
    """Readiness probe: validates live PostgreSQL and Redis connections."""
    db_status = "error"
    redis_status = "connected" if ping_redis() else "unreachable"
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        db_status = "connected"
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")

    return {
        "status": "ready",
        "database": db_status,
        "redis": redis_status,
    }


# Include modular routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(portal.router)
app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(files.router)
app.include_router(time.router)
app.include_router(agency.router)
