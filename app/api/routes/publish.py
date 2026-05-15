"""POST /publish — publish an enriched article."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PublishRequest, PublishResponse
from app.repositories import get_db
from app.security import require_api_key
from app.services.medium_import_service import MediumImportService
from app.services.publishing_service import PublishingService

router = APIRouter()


@router.post("", response_model=PublishResponse, status_code=status.HTTP_200_OK)
async def publish(
    body: PublishRequest,
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PublishResponse:
    """
    Publish an enriched article.

    Default behaviour (publisher='website'):
    - Records the article as published on the website (source of truth)
    - Generates a Medium syndication bundle at content/generated/medium/{slug}/
    - Saves LinkedIn drafts

    Use publisher='medium' or 'all' to additionally attempt a token-based
    Medium API publish (requires a pre-existing integration token — Medium no
    longer issues new tokens as of January 2025).
    """
    service = PublishingService(db)
    result = await service.publish_article(
        body.article_id,
        actor=actor,
        publish_status=body.publish_status,
        publisher=body.publisher,
    )

    medium_import_service = MediumImportService(db)
    await medium_import_service.queue_for_import(
        body.article_id,
        website_url=result["website_url"],
        canonical_url=result["canonical_url"],
    )
    if result["medium"].get("status") == "published" and result["medium"].get("url"):
        await medium_import_service.mark_as_imported(
            body.article_id,
            medium_url=result["medium"]["url"],
        )

    return PublishResponse(**result)
