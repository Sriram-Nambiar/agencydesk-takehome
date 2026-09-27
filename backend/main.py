import os
import uuid
import logging
from time import perf_counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agencydesk.access")

from config import get_settings
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
    time as time_router,
    agency,
    notifications,
    automations,
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
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = perf_counter()
    try:
        response = await call_next(request)
        process_time_ms = (perf_counter() - start_time) * 1000
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"request_id={request_id} method={request.method} path={request.url.path} "
            f"status={response.status_code} latency_ms={process_time_ms:.2f} client_ip={client_ip}"
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    except Exception as exc:
        process_time_ms = (perf_counter() - start_time) * 1000
        client_ip = request.client.host if request.client else "unknown"
        logger.error(
            f"request_id={request_id} method={request.method} path={request.url.path} "
            f"status=500 latency_ms={process_time_ms:.2f} client_ip={client_ip} error={exc}"
        )
        raise exc


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
app.include_router(time_router.router)
app.include_router(agency.router)
app.include_router(notifications.router)
app.include_router(automations.router)

# Uploaded files are served by the authorization checked download endpoint in
# routers.files; exposing the storage directory as static content bypasses the
# task, tenant, and visibility checks.
