"""Medium import lifecycle service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediumImport
from app.repositories import (
    AIGenerationRepository,
    ArticleRepository,
    MediumImportRepository,
)
from app.services.canonical_verifier import CanonicalVerifier


class MediumImportService:
    """Coordinates Medium import queue management and status reporting."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._article_repo = ArticleRepository(session)
        self._generation_repo = AIGenerationRepository(session)
        self._medium_import_repo = MediumImportRepository(session)

    async def queue_for_import(
        self, article_id: uuid.UUID, website_url: str, canonical_url: str
    ) -> MediumImport:
        """Queue an article for Medium import. Called automatically after publish."""
        article = await self._article_repo.get_by_id(article_id)
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        existing = await self._medium_import_repo.get_by_article_id(article_id)
        if existing is not None:
            await self._medium_import_repo.update_status(
                existing.id,
                "queued",
                website_url=website_url,
                canonical_url=canonical_url,
                medium_url=None,
                canonical_verified=False,
                canonical_found=None,
                verified_at=None,
                imported_at=None,
            )
            refreshed = await self._medium_import_repo.get_by_id(existing.id)
            assert refreshed is not None
            return refreshed

        return await self._medium_import_repo.create(
            {
                "article_id": article_id,
                "website_url": website_url,
                "canonical_url": canonical_url,
                "status": "queued",
            }
        )

    async def get_import_queue(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """Return articles ready for import with pre-built URLs and instructions."""
        if status:
            records = await self._medium_import_repo.list_by_status(status, limit=limit)
        else:
            records = await self._medium_import_repo.list_queue(limit=limit)

        queue: list[dict] = []
        for record in records:
            article = record.article
            seo_title = await self._get_seo_title(record.article_id)
            queue.append(
                {
                    "article_id": str(record.article_id),
                    "slug": article.slug,
                    "title": article.title,
                    "website_article_url": record.website_url,
                    "medium_import_url": "https://medium.com/p/import",
                    "canonical_url": record.canonical_url,
                    "status": record.status,
                    "seo_title": seo_title,
                    "tags": article.tags or [],
                    "excerpt": article.excerpt,
                    "queued_at": record.created_at,
                    "imported_at": record.imported_at,
                }
            )
        return queue

    async def mark_as_imported(self, article_id: uuid.UUID, medium_url: str) -> dict:
        """Operator marks an article as imported, provides Medium URL."""
        record = await self._medium_import_repo.get_by_article_id(article_id)
        if record is None:
            raise ValueError(f"Medium import record for article {article_id} not found")

        await self._medium_import_repo.mark_imported(record.id, medium_url)
        refreshed = await self._medium_import_repo.get_by_id(record.id)
        assert refreshed is not None
        return self._serialize_status(refreshed)

    async def verify_canonical(self, article_id: uuid.UUID) -> dict:
        """Verify canonical URL on the Medium-imported article."""
        record = await self._medium_import_repo.get_by_article_id(article_id)
        if record is None:
            raise ValueError(f"Medium import record for article {article_id} not found")
        if record.status != "imported":
            raise ValueError(f"Article {article_id} is not ready for canonical verification")
        if not record.medium_url:
            raise ValueError(f"Article {article_id} has not been marked as imported yet")

        verifier = CanonicalVerifier()
        result = await verifier.verify_canonical(record.medium_url, record.canonical_url)

        await self._medium_import_repo.mark_verified(
            record.id,
            canonical_found=result["canonical_found"] or "",
            verified=result["verified"],
        )

        refreshed = await self._medium_import_repo.get_by_id(record.id)
        assert refreshed is not None
        return self._serialize_status(refreshed)

    async def get_import_status(self, article_id: uuid.UUID) -> dict:
        """Get current import status for an article."""
        record = await self._medium_import_repo.get_by_article_id(article_id)
        if record is None:
            raise ValueError(f"Medium import record for article {article_id} not found")
        return self._serialize_status(record)

    async def _get_seo_title(self, article_id: uuid.UUID) -> str | None:
        generation = await self._generation_repo.get_latest_by_type(article_id, "seo_title")
        return generation.output if generation else None

    def _serialize_status(self, record: MediumImport) -> dict:
        return {
            "article_id": str(record.article_id),
            "status": record.status,
            "website_url": record.website_url,
            "canonical_url": record.canonical_url,
            "medium_url": record.medium_url,
            "canonical_verified": record.canonical_verified,
            "canonical_found": record.canonical_found,
            "verified_at": record.verified_at,
        }
