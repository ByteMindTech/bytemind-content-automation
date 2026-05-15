"""API routers package."""

from fastapi import APIRouter

from app.api.routes import (
    analytics,
    approval,
    articles,
    generate,
    health,
    medium_import,
    monitoring,
    publish,
    schedule,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(generate.router, prefix="/generate", tags=["generation"])
api_router.include_router(publish.router, prefix="/publish", tags=["publishing"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["scheduling"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(medium_import.router, prefix="/medium-import", tags=["medium-import"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(approval.router, prefix="/approval", tags=["approval"])
api_router.include_router(monitoring.router, prefix="/metrics", tags=["monitoring"])

__all__ = ["api_router"]
