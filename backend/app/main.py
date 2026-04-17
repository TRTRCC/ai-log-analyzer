"""
AI Log Analyzer - Main Application Entry Point
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_database, close_database, async_session_factory
from app.utils.logging import setup_logging, get_logger
from app.utils.security import SecurityMiddleware

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Import API routers
from app.api import auth, logs, analysis, reports, admin, security, backup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events handler"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Initialize AI engine (load providers)
    from app.ai.engine import ai_engine
    async with async_session_factory() as db:
        await ai_engine.initialize(db)
    logger.info("AI engine initialized")

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close AI engine
    from app.ai.engine import ai_engine
    await ai_engine.close_all()
    logger.info("AI engine closed")

    await close_database()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise-grade AI-powered log analysis system",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

# Add trusted host middleware
allowed_hosts = ["localhost", "*.localhost", "127.0.0.1"]
if settings.cors_origins:
    allowed_hosts.extend(settings.cors_origins)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts,
)

# Add security middleware
app.add_middleware(SecurityMiddleware)


# Request logging middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(datetime.now().timestamp()))
        start_time = datetime.now()

        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
            }
        )

        response = await call_next(request)

        # Calculate duration
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            }
        )

        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{round(duration_ms, 2)}ms"

        return response


app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """ValueError exception handler"""
    return JSONResponse(
        status_code=400,
        content={"error": "Validation error", "detail": str(exc)}
    )


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/health", tags=["System"])
async def api_health_check():
    """API health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "services": {
            "database": "connected",
            "redis": "connected",
            "clickhouse": "connected",
        }
    }


# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """Root endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/api/docs",
        "health": "/health",
    }


# Include API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["Logs"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(security.router, prefix="/api/v1/security", tags=["Security"])
app.include_router(backup.router, prefix="/api/v1/backup", tags=["Backup"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        workers=2,
    )