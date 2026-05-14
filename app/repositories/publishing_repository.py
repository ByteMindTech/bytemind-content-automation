"""Publishing history repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PublishingHistory


class PublishingRepository:
    """Tracks Medium/mock publish events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> PublishingHistory:
        record = PublishingHistory(**data)
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_by_article(self, article_id: uuid.UUID) -> list[PublishingHistory]:
        result = await self._session.execute(
            select(PublishingHistory)
            .where(PublishingHistory.article_id == article_id)
            .order_by(PublishingHistory.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_published(
        self, article_id: uuid.UUID, publisher: str = "medium"
    ) -> PublishingHistory | None:
        result = await self._session.execute(
            select(PublishingHistory)
            .where(
                PublishingHistory.article_id == article_id,
                PublishingHistory.publisher == publisher,
                PublishingHistory.status == "published",
            )
            .order_by(PublishingHistory.published_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_by_status(self) -> dict[str, int]:
        from sqlalchemy import func

        result = await self._session.execute(
            select(PublishingHistory.status, func.count(PublishingHistory.id)).group_by(
                PublishingHistory.status
            )
        )
        return {row[0]: row[1] for row in result.all()}
