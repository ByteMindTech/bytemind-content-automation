"""POST /generate — ingest + AI enrich an article."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import GenerateRequest, GenerateResponse
from app.models import Article
from app.repositories import get_db
from app.security import require_api_key
from app.services.content_service import ContentService

router = APIRouter()


@router.post("", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    body: GenerateRequest,
    request: Request,
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerateResponse:
    """
    Ingest a Markdown article and run full AI enrichment.

    Provide either `source_content` (raw Markdown string) or
    `article_id` (for re-enrichment of an existing article).
    """
    service = ContentService(db)

    if body.source_content:
        article_id, is_new = await service.ingest_from_string(
            body.source_content,
            source_path=body.source_path,
            actor=actor,
        )
    elif body.article_id:
        article_id = body.article_id
        is_new = False
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either source_content or article_id must be provided.",
        )

    generated_types = await service.enrich_article(article_id, actor=actor)

    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one()

    return GenerateResponse(
        article_id=article_id,
        is_new=is_new,
        generated_types=generated_types,
        status=article.status,
    )
