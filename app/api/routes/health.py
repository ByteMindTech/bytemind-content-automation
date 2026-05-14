"""GET /health endpoint."""

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.config import get_settings

router = APIRouter()
_settings = get_settings()


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """Returns platform status and configuration summary."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        environment=_settings.app_env,
        medium_dry_run=_settings.medium_dry_run,
        ai_provider=_settings.ai_provider,
    )
