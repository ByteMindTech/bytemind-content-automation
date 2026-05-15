"""Publishing service — orchestrates website-first publishing with optional Medium syndication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.linkedin.generator import LinkedInGenerator
from app.medium.publisher import MediumPublisher
from app.medium.syndication import MediumSyndicationExporter
from app.repositories import (
    AIGenerationRepository,
    ArticleRepository,
    AuditRepository,
    PublishingRepository,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class PublishingService:
    """
    Orchestrates the website-first publishing pipeline:

    1. Pull AI-generated content from the database
    2. Record the article as published on the website (primary target)
    3. Build a Medium syndication bundle for manual import / optional API publish
    4. Save LinkedIn drafts to the filesystem
    5. Optionally attempt token-based Medium API publish (only when token is
       configured AND MEDIUM_DRY_RUN=false)
    6. Track all outcomes in publishing_history

    Publishing targets:
        "website"  — website publish + Medium bundle (default, no token required)
        "medium"   — attempt token-based Medium API publish (requires existing token)
        "all"      — website publish + bundle + token-based publish attempt
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._article_repo = ArticleRepository(session)
        self._generation_repo = AIGenerationRepository(session)
        self._publishing_repo = PublishingRepository(session)
        self._audit_repo = AuditRepository(session)
        self._medium_legacy = MediumPublisher()
        self._medium_syndication = MediumSyndicationExporter()
        self._linkedin = LinkedInGenerator()

    async def publish_article(
        self,
        article_id: uuid.UUID,
        actor: str = "system",
        publish_status: str = "draft",
        publisher: str = "website",
    ) -> dict:
        """
        Full publish pipeline.

        Returns a summary dict with keys:
            article_id, slug, website_url, syndication_bundle_path,
            medium, linkedin_drafts_folder, status
        """
        article = await self._article_repo.get_by_id(article_id)
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        if article.status not in ("enriched", "scheduled", "approved"):
            raise ValueError(
                f"Article '{article.slug}' is in status '{article.status}'. "
                "Must be 'enriched', 'scheduled', or 'approved' before publishing."
            )

        # ── Gather AI-generated content ──────────────────────────────────────
        async def _get(prompt_type: str) -> str:
            gen = await self._generation_repo.get_latest_by_type(article_id, prompt_type)
            return gen.output if gen else ""

        seo_title = await _get("seo_title")
        seo_description = await _get("seo_description")
        medium_intro = await _get("medium_intro")
        linkedin_short = await _get("linkedin_short")
        linkedin_medium = await _get("linkedin_medium")
        linkedin_technical = await _get("linkedin_technical")
        hashtags = await _get("hashtags")
        cta = await _get("cta")

        # Read source markdown body
        source = Path(article.source_path)
        body_markdown = source.read_text(encoding="utf-8") if source.exists() else article.excerpt

        canonical_base = _settings.medium_canonical_base_url.rstrip("/")
        website_url = f"{_settings.website_base_url.rstrip('/')}/blogs/{article.slug}"
        canonical_url = f"{canonical_base}/{article.slug}"

        # ── Website publish record (primary target) ───────────────────────────
        website_record = await self._publishing_repo.create(
            {
                "article_id": article_id,
                "publisher": "website",
                "external_id": article.slug,
                "url": website_url,
                "status": "published",
                "dry_run": False,
                "published_at": datetime.now(tz=timezone.utc),
            }
        )
        logger.info(
            "website_publish_recorded",
            article_id=str(article_id),
            url=website_url,
        )

        # ── Medium syndication bundle (always generated) ──────────────────────
        syndication_bundle_path: str | None = None
        try:
            bundle_folder = self._medium_syndication.build_bundle(
                slug=article.slug,
                title=article.title,
                seo_title=seo_title,
                seo_description=seo_description,
                body_markdown=body_markdown,
                medium_intro=medium_intro,
                tags=article.tags or [],
                hashtags=hashtags,
                cta=cta,
                category=article.category,
                author=article.author,
                published_date=article.date_label or datetime.now().strftime("%Y-%m-%d"),
            )
            syndication_bundle_path = str(bundle_folder)
            await self._publishing_repo.create(
                {
                    "article_id": article_id,
                    "publisher": "medium_syndication",
                    "external_id": article.slug,
                    "url": canonical_url,
                    "status": "bundle_ready",
                    "dry_run": False,
                    "published_at": datetime.now(tz=timezone.utc),
                }
            )
        except Exception as exc:
            logger.error("medium_syndication_failed", error=str(exc))

        # ── Optional: token-based Medium API publish ──────────────────────────
        medium_result: dict = {"status": "skipped", "reason": "website_first_mode"}
        want_medium_api = publisher in ("medium", "all")
        has_token = bool(_settings.medium_integration_token)

        if want_medium_api:
            if not has_token:
                medium_result = {
                    "status": "skipped",
                    "reason": (
                        "No MEDIUM_INTEGRATION_TOKEN configured. "
                        "Medium no longer issues new integration tokens. "
                        "Use the syndication bundle for manual import at "
                        "https://medium.com/me/import"
                    ),
                }
                logger.warning(
                    "medium_api_skipped_no_token",
                    article_id=str(article_id),
                )
            else:
                body_for_medium = (
                    f"{medium_intro}\n\n{body_markdown}" if medium_intro.strip() else body_markdown
                )
                try:
                    medium_result = await self._medium_legacy.publish(
                        slug=article.slug,
                        title=seo_title or article.title,
                        body_markdown=body_for_medium,
                        tags=article.tags or [],
                        canonical_slug=article.slug,
                        publish_status=publish_status,
                    )
                    await self._publishing_repo.create(
                        {
                            "article_id": article_id,
                            "publisher": "medium",
                            "external_id": medium_result.get("medium_id"),
                            "url": medium_result.get("url"),
                            "status": medium_result.get("status", "published"),
                            "dry_run": medium_result.get("dry_run", False),
                            "published_at": datetime.now(tz=timezone.utc),
                            "raw_response": medium_result.get("raw"),
                        }
                    )
                    logger.info(
                        "medium_api_publish_recorded",
                        article_id=str(article_id),
                        url=medium_result.get("url"),
                    )
                except Exception as exc:
                    medium_result = {"status": "failed", "error": str(exc)}
                    await self._publishing_repo.create(
                        {
                            "article_id": article_id,
                            "publisher": "medium",
                            "status": "failed",
                            "dry_run": False,
                            "error_message": str(exc),
                        }
                    )
                    logger.error("medium_api_publish_failed", error=str(exc))

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

        # ── Update article status ─────────────────────────────────────────────
        await self._article_repo.update_status(article_id, "published")

        await self._audit_repo.log(
            action="publish",
            actor=actor,
            resource_type="article",
            resource_id=str(article_id),
            details={
                "publisher": publisher,
                "website_url": website_url,
                "canonical_url": canonical_url,
                "syndication_bundle": syndication_bundle_path,
                "medium_status": medium_result.get("status"),
                "linkedin_folder": linkedin_folder,
            },
            success=True,
        )

        return {
            "article_id": str(article_id),
            "slug": article.slug,
            "website_url": website_url,
            "canonical_url": canonical_url,
            "syndication_bundle_path": syndication_bundle_path,
            "medium": medium_result,
            "linkedin_drafts_folder": linkedin_folder,
            "status": "published",
        }
