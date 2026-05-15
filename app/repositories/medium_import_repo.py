"""Medium import repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import MediumImport


class MediumImportRepository:
    """Database access layer for Medium import lifecycle records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> MediumImport:
        record = MediumImport(**data)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_by_id(self, import_id: uuid.UUID) -> MediumImport | None:
        result = await self._session.execute(
            select(MediumImport)
            .options(selectinload(MediumImport.article))
            .where(MediumImport.id == import_id)
        )
        return result.scalar_one_or_none()

    async def get_by_article_id(self, article_id: uuid.UUID) -> MediumImport | None:
        result = await self._session.execute(
            select(MediumImport)
            .options(selectinload(MediumImport.article))
            .where(MediumImport.article_id == article_id)
            .order_by(MediumImport.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str, limit: int = 50) -> list[MediumImport]:
        result = await self._session.execute(
            select(MediumImport)
            .options(selectinload(MediumImport.article))
            .where(MediumImport.status == status)
            .order_by(MediumImport.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_queue(self, limit: int = 50) -> list[MediumImport]:
        result = await self._session.execute(
            select(MediumImport)
            .options(selectinload(MediumImport.article))
            .where(MediumImport.status != "verified")
            .order_by(MediumImport.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self, import_id: uuid.UUID, status: str, **kwargs: object
    ) -> None:
        await self._session.execute(
            update(MediumImport)
            .where(MediumImport.id == import_id)
            .values(status=status, updated_at=datetime.now(tz=UTC), **kwargs)
        )
        await self._session.flush()

    async def mark_imported(self, import_id: uuid.UUID, medium_url: str) -> None:
        await self.update_status(
            import_id,
            "imported",
            medium_url=medium_url,
            imported_at=datetime.now(tz=UTC),
        )

    async def mark_verified(
        self, import_id: uuid.UUID, canonical_found: str, verified: bool
    ) -> None:
        await self.update_status(
            import_id,
            "verified" if verified else "canonical_mismatch",
            canonical_verified=verified,
            canonical_found=canonical_found,
            verified_at=datetime.now(tz=UTC),
        )
