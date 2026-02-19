import sys
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# Add src to path for logging_config
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger

logger = get_logger(__name__)

from .routes import runs, workflow, settings, auth, prompts, infopigula, analytics, scheduler
from .services import auth as auth_service
from .services import scheduler as scheduler_service

# Static files directory (built frontend)
STATIC_DIR = Path(__file__).parent / "static"

# Cookie name for session
COOKIE_NAME = "session"

# Paths that don't require authentication
PUBLIC_PATHS = [
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/logout",
    "/health",
]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log every request for debugging."""
    async def dispatch(self, request: Request, call_next):
        logger.info(f"Incoming request: {request.method} {request.url.path}")
        try:
            response = await call_next(request)
            logger.info(f"Response: {response.status_code} for {request.method} {request.url.path}")
            return response
        except Exception as e:
            logger.error(f"Unhandled error during request {request.method} {request.url.path}: {str(e)}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "error": str(e)}
            )


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect API routes with session authentication."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for non-API routes (static files, frontend)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip auth for public paths
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth if authentication is disabled
        if not auth_service.is_auth_enabled():
            return await call_next(request)

        # Validate session
        token = request.cookies.get(COOKIE_NAME)
        if not auth_service.validate_session(token):
            logger.warning(f"Authentication failed for path: {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"}
            )

        return await call_next(request)


app = FastAPI(
    title="YT News Generator Dashboard",
    description="API for browsing and managing video generation runs",
    version="1.0.0",
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception caught: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)}
    )

logger.info("Starting YT News Generator Dashboard API")

# Configure CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware first to catch everything
app.add_middleware(RequestLoggingMiddleware)
# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Include routes
app.include_router(auth.router)  # Auth routes first (public)
app.include_router(runs.router)
app.include_router(workflow.router)
app.include_router(settings.router)
app.include_router(prompts.router)
app.include_router(infopigula.router)
app.include_router(analytics.router)
app.include_router(scheduler.router)


@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on startup."""
    scheduler_service.init_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler gracefully."""
    scheduler_service.shutdown_scheduler()


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve static frontend in production
if STATIC_DIR.exists():
    # Mount static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Serve index.html for all non-API routes (SPA fallback)
    @app.get("/")
    async def serve_root():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not found"}

        # Try to serve static file first
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def root():
        return {"message": "YT News Generator Dashboard API - Run in dev mode or build frontend"}
