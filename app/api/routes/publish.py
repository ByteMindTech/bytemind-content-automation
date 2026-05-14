"""POST /publish — publish an enriched article."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PublishRequest, PublishResponse
from app.repositories import get_db
from app.security import require_api_key
from app.services.publishing_service import PublishingService

router = APIRouter()


@router.post("", response_model=PublishResponse, status_code=status.HTTP_200_OK)
async def publish(
    body: PublishRequest,
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PublishResponse:
    """
    Publish an enriched article to Medium (or dry-run if MEDIUM_DRY_RUN=true)
    and save LinkedIn drafts to the filesystem.
    """
    service = PublishingService(db)
    result = await service.publish_article(
        body.article_id,
        actor=actor,
        publish_status=body.publish_status,
    )
    return PublishResponse(**result)
