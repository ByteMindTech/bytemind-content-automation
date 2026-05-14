"""GET /analytics — platform metrics."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.analytics_service import AnalyticsService
from app.api.schemas import AnalyticsResponse
from app.repositories import get_db
from app.security import require_api_key

router = APIRouter()


@router.get("", response_model=AnalyticsResponse)
async def analytics_overview(
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyticsResponse:
    """Return high-level analytics: article counts, publish history, AI costs."""
    service = AnalyticsService(db)
    data = await service.overview()
    return AnalyticsResponse(**data)


@router.get("/tokens")
async def token_usage(
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    provider: str | None = Query(None),
) -> list[dict]:
    """Return daily token usage breakdown."""
    service = AnalyticsService(db)
    return await service.token_usage_by_date(since=since, until=until, provider=provider)


@router.get("/published")
async def published_articles(
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = Query(None),
    since: datetime | None = Query(None),
) -> list[dict]:
    """Return list of published articles with Medium URLs."""
    service = AnalyticsService(db)
    return await service.published_articles(category=category, since=since)
