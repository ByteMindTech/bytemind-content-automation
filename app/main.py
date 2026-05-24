"""ByteMind Content Automation Platform — FastAPI application entry point."""

import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
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
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# ── Protected docs (HTTP Basic Auth) ─────────────────────────────────────────
_docs_security = HTTPBasic()


def _verify_docs_credentials(
    credentials: HTTPBasicCredentials = Depends(_docs_security),
) -> str:
    """Validate HTTP Basic credentials for docs access (constant-time compare)."""
    correct_user = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        _settings.docs_username.encode("utf-8"),
    )
    correct_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        _settings.docs_password.encode("utf-8"),
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/docs", include_in_schema=False)
async def docs_page(username: str = Depends(_verify_docs_credentials)):  # noqa: ARG001
    """Swagger UI — protected by HTTP Basic Auth."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title + " — Docs")


@app.get("/redoc", include_in_schema=False)
async def redoc_page(username: str = Depends(_verify_docs_credentials)):  # noqa: ARG001
    """ReDoc — protected by HTTP Basic Auth."""
    return get_redoc_html(openapi_url="/openapi.json", title=app.title + " — ReDoc")


@app.get("/openapi.json", include_in_schema=False)
async def openapi_schema(username: str = Depends(_verify_docs_credentials)):  # noqa: ARG001
    """OpenAPI schema — protected by HTTP Basic Auth."""
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
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

# ── GraphQL endpoint for Medium story management ──────────────────────────────
from app.api.graphql_stories import graphql_app  # noqa: E402

app.include_router(graphql_app, prefix="/graphql", tags=["graphql"])
