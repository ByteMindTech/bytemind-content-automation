"""ByteMind Content Automation Platform — FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api import api_router
from app.config import get_settings
from app.models import Base
from app.repositories.database import engine
from app.scheduler.scheduler import scheduler
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    logger.info(
        "startup",
        env=_settings.app_env,
        medium_dry_run=_settings.medium_dry_run,
        ai_provider=_settings.ai_provider,
    )

    # Create all tables (idempotent in dev; use Alembic in production)
    if _settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("db_tables_created_or_verified")

    # Start background scheduler
    scheduler.start()

    yield

    # Graceful shutdown
    scheduler.shutdown()
    await engine.dispose()
    logger.info("shutdown_complete")


# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[_settings.rate_limit_global])

# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(
    title="ByteMind Content Automation API",
    description=(
        "AI-powered content lifecycle automation for ByteMind — "
        "ingest, enrich, publish, and track technical articles."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router)
