"""Publishing service — orchestrates Medium publish + LinkedIn draft save."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.linkedin.generator import LinkedInGenerator
from app.medium.publisher import MediumPublisher
from app.repositories import (
    AIGenerationRepository,
    ArticleRepository,
    AuditRepository,
    PublishingRepository,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PublishingService:
    """
    Orchestrates:
    1. Pull AI-generated content from DB
    2. Publish to Medium (or dry-run)
    3. Save LinkedIn drafts to filesystem
    4. Track everything in publishing_history
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._article_repo = ArticleRepository(session)
        self._generation_repo = AIGenerationRepository(session)
        self._publishing_repo = PublishingRepository(session)
        self._audit_repo = AuditRepository(session)
        self._medium = MediumPublisher()
        self._linkedin = LinkedInGenerator()

    async def publish_article(
        self,
        article_id: uuid.UUID,
        actor: str = "system",
        publish_status: str = "draft",
    ) -> dict:
        """
        Full publish pipeline: Medium + LinkedIn drafts.
        Returns a summary dict.
        """
        article = await self._article_repo.get_by_id(article_id)
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        if article.status not in ("enriched", "scheduled"):
            raise ValueError(
                f"Article '{article.slug}' is in status '{article.status}'. "
                "Must be 'enriched' or 'scheduled' before publishing."
            )

        # Gather generated content
        async def _get(prompt_type: str) -> str:
            gen = await self._generation_repo.get_latest_by_type(article_id, prompt_type)
            return gen.output if gen else ""

        medium_intro = await _get("medium_intro")
        linkedin_short = await _get("linkedin_short")
        linkedin_medium = await _get("linkedin_medium")
        linkedin_technical = await _get("linkedin_technical")
        hashtags = await _get("hashtags")
        cta = await _get("cta")

        # Read source markdown for the body
        source = Path(article.source_path)
        body_markdown = source.read_text(encoding="utf-8") if source.exists() else article.excerpt
        if medium_intro:
            body_markdown = f"{medium_intro}\n\n{body_markdown}"

        # ── Medium publish ───────────────────────────────────────────────────
        medium_result: dict = {}
        try:
            medium_result = await self._medium.publish(
                slug=article.slug,
                title=article.title,
                body_markdown=body_markdown,
                tags=article.tags or [],
                publish_status=publish_status,
            )
            pub_status = medium_result.get("status", "published")
            pub_record = await self._publishing_repo.create(
                {
                    "article_id": article_id,
                    "publisher": "medium",
                    "external_id": medium_result.get("medium_id"),
                    "url": medium_result.get("url"),
                    "status": pub_status,
                    "dry_run": medium_result.get("dry_run", False),
                    "published_at": datetime.now(tz=timezone.utc),
                    "raw_response": medium_result.get("raw"),
                }
            )
            logger.info(
                "medium_publish_recorded",
                article_id=str(article_id),
                status=pub_status,
                url=medium_result.get("url"),
            )
        except Exception as exc:
            pub_record = await self._publishing_repo.create(
                {
                    "article_id": article_id,
                    "publisher": "medium",
                    "status": "failed",
                    "dry_run": False,
                    "error_message": str(exc),
                }
            )
            logger.error("medium_publish_failed", error=str(exc))
            await self._audit_repo.log(
                action="publish",
                actor=actor,
                resource_type="article",
                resource_id=str(article_id),
                success=False,
                error_message=str(exc),
            )

        # ── LinkedIn drafts ───────────────────────────────────────────────────
        linkedin_folder: str | None = None
        if any([linkedin_short, linkedin_medium, linkedin_technical]):
            try:
                folder = self._linkedin.save_drafts(
                    slug=article.slug,
                    short=linkedin_short,
                    medium=linkedin_medium,
                    technical=linkedin_technical,
                    hashtags=hashtags,
                    cta=cta,
                    article_title=article.title,
                )
                linkedin_folder = str(folder)
            except Exception as exc:
                logger.error("linkedin_save_failed", error=str(exc))

        # ── Update article status ────────────────────────────────────────────
        new_status = "published" if medium_result.get("status") == "published" else article.status
        if medium_result.get("dry_run"):
            new_status = "enriched"  # dry-run doesn't count as published
        await self._article_repo.update_status(article_id, new_status)

        await self._audit_repo.log(
            action="publish",
            actor=actor,
            resource_type="article",
            resource_id=str(article_id),
            details={
                "medium_status": medium_result.get("status"),
                "linkedin_folder": linkedin_folder,
                "dry_run": medium_result.get("dry_run"),
            },
            success=True,
        )

        return {
            "article_id": str(article_id),
            "slug": article.slug,
            "medium": medium_result,
            "linkedin_drafts_folder": linkedin_folder,
            "status": new_status,
        }
