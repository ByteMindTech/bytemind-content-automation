"""GET /articles — list and filter articles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ArticleResponse
from app.repositories import get_db
from app.repositories.article_repository import ArticleRepository
from app.security import require_api_key

router = APIRouter()


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None, description="Filter by status"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ArticleResponse]:
    """List all ingested articles with optional filters."""
    repo = ArticleRepository(db)
    articles = await repo.list_articles(
        status=status, category=category, limit=limit, offset=offset
    )
    return [ArticleResponse.model_validate(a) for a in articles]


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: str,
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleResponse:
    """Get a single article by ID."""
    import uuid
    from fastapi import HTTPException

    repo = ArticleRepository(db)
    article = await repo.get_by_id(uuid.UUID(article_id))
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)
