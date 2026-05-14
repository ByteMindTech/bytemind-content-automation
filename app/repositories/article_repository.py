"""Article repository — CRUD and status management."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article


class ArticleRepository:
    """Database access layer for Article model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> Article:
        article = Article(**data)
        self._session.add(article)
        await self._session.flush()
        return article

    async def get_by_id(self, article_id: uuid.UUID) -> Article | None:
        result = await self._session.get(Article, article_id)
        return result

    async def get_by_slug(self, slug: str) -> Article | None:
        result = await self._session.execute(
            select(Article).where(Article.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_articles(
        self,
        status: str | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Article]:
        q = select(Article).order_by(Article.created_at.desc())
        if status:
            q = q.where(Article.status == status)
        if category:
            q = q.where(Article.category == category)
        q = q.limit(limit).offset(offset)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update_status(self, article_id: uuid.UUID, status: str) -> None:
        await self._session.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(status=status, updated_at=datetime.utcnow())
        )

    async def exists_by_slug(self, slug: str) -> bool:
        result = await self._session.execute(
            select(Article.id).where(Article.slug == slug)
        )
        return result.scalar_one_or_none() is not None

    async def count_by_status(self) -> dict[str, int]:
        """Return article count grouped by status."""
        from sqlalchemy import func

        result = await self._session.execute(
            select(Article.status, func.count(Article.id)).group_by(Article.status)
        )
        return {row[0]: row[1] for row in result.all()}
