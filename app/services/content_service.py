"""Content enrichment service — orchestrates parsing + AI generation + approval."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AIEngine, PromptBuilder
from app.repositories import AIGenerationRepository, ArticleRepository, AuditRepository
from app.utils.logging import get_logger
from app.utils.markdown_parser import MarkdownParser, ParsedArticle

logger = get_logger(__name__)


class ContentService:
    """
    Orchestrates the full content lifecycle:
    parse → validate → persist → enrich with AI.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._article_repo = ArticleRepository(session)
        self._generation_repo = AIGenerationRepository(session)
        self._audit_repo = AuditRepository(session)
        self._parser = MarkdownParser()
        self._prompt_builder = PromptBuilder()
        self._ai = AIEngine()

    async def ingest_file(
        self, path: Path, actor: str = "system"
    ) -> tuple[uuid.UUID, bool]:
        """
        Parse and persist an article from a .md file.

        Returns (article_id, is_new).
        If the slug already exists, returns the existing ID without re-inserting.
        """
        parsed = self._parser.parse_file(path)
        return await self.ingest_parsed(parsed, actor=actor)

    async def ingest_from_string(
        self, raw: str, source_path: str = "", actor: str = "system"
    ) -> tuple[uuid.UUID, bool]:
        parsed = self._parser.parse_string(raw, source_path=source_path)
        return await self.ingest_parsed(parsed, actor=actor)

    async def ingest_parsed(
        self, parsed: ParsedArticle, actor: str = "system"
    ) -> tuple[uuid.UUID, bool]:
        # Duplicate slug guard
        if await self._article_repo.exists_by_slug(parsed.slug):
            existing = await self._article_repo.get_by_slug(parsed.slug)
            assert existing is not None
            logger.info("article_already_ingested", slug=parsed.slug, id=str(existing.id))
            return existing.id, False

        article = await self._article_repo.create(
            {
                "slug": parsed.slug,
                "title": parsed.title,
                "category": parsed.category,
                "tags": parsed.tags,
                "author": parsed.author,
                "author_role": parsed.author_role,
                "excerpt": parsed.excerpt,
                "source_path": parsed.source_path,
                "date_label": parsed.date_label,
                "publish_date": parsed.date,
                "read_time_minutes": parsed.estimated_read_minutes,
                "word_count": parsed.word_count,
                "featured": parsed.featured,
                "status": "pending",
            }
        )

        await self._audit_repo.log(
            action="ingest",
            actor=actor,
            resource_type="article",
            resource_id=str(article.id),
            details={"slug": parsed.slug, "title": parsed.title},
        )
        logger.info("article_ingested", slug=parsed.slug, id=str(article.id))
        return article.id, True

    async def enrich_article(
        self, article_id: uuid.UUID, actor: str = "system"
    ) -> list[str]:
        """
        Run full AI enrichment pipeline on a persisted article.
        Returns list of generated prompt_types.
        """
        article = await self._article_repo.get_by_id(article_id)
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        await self._article_repo.update_status(article_id, "processing")

        # Rebuild ParsedArticle from DB fields for prompts (body not stored in DB)
        # We need the actual markdown — re-read from source_path
        source = Path(article.source_path)
        if source.exists():
            parsed = self._parser.parse_file(source)
        else:
            logger.warning("source_path_missing", path=article.source_path)
            # Fallback: build minimal ParsedArticle from DB
            parsed = ParsedArticle(
                title=article.title,
                slug=article.slug,
                date=article.publish_date or datetime.now(tz=timezone.utc),
                date_label=article.date_label or "",
                category=article.category,
                category_color="#00d4ff",
                tags=article.tags or [],
                author=article.author,
                author_role=article.author_role or "",
                excerpt=article.excerpt,
                content_body=article.excerpt,  # best we have
            )

        prompts = self._prompt_builder.build_all(parsed)
        generated_types: list[str] = []

        # Run all AI prompts concurrently (semaphore-limited inside AIEngine)
        results = await self._ai.generate_batch(prompts, source_body=parsed.content_body)

        for result in results:
            try:
                await self._generation_repo.create(
                    {
                        "article_id": article_id,
                        "provider": result.provider,
                        "model": result.model,
                        "prompt_type": result.prompt_type,
                        "prompt_text": "",  # not stored to save space
                        "output": result.output,
                        "output_validated": result.output_validated,
                        "tokens_input": result.tokens_input,
                        "tokens_output": result.tokens_output,
                        "cost_usd": result.cost_usd,
                        "latency_ms": result.latency_ms,
                        "retry_count": result.retry_count,
                    }
                )

                await self._generation_repo.record_token_usage(
                    date=datetime.now(tz=timezone.utc),
                    provider=result.provider,
                    model=result.model,
                    prompt_type=result.prompt_type,
                    tokens_input=result.tokens_input,
                    tokens_output=result.tokens_output,
                    cost_usd=result.cost_usd,
                )

                generated_types.append(result.prompt_type)

                if not result.output_validated:
                    logger.warning(
                        "ai_output_validation_failed",
                        prompt_type=result.prompt_type,
                        issues=result.validation_issues,
                    )

            except Exception as exc:
                logger.error(
                    "ai_generation_persist_failed",
                    prompt_type=result.prompt_type,
                    error=str(exc),
                )
                await self._audit_repo.log(
                    action="generate",
                    actor=actor,
                    resource_type="ai_generation",
                    resource_id=str(article_id),
                    details={"prompt_type": result.prompt_type, "error": str(exc)},
                    success=False,
                    error_message=str(exc),
                )
                continue

        final_status = "enriched" if generated_types else "failed"
        await self._article_repo.update_status(article_id, final_status)

        await self._audit_repo.log(
            action="generate",
            actor=actor,
            resource_type="article",
            resource_id=str(article_id),
            details={"generated_types": generated_types},
            success=bool(generated_types),
        )

        logger.info(
            "enrichment_complete",
            article_id=str(article_id),
            generated=len(generated_types),
            status=final_status,
        )

        # Trigger revision + approval workflow if enrichment succeeded
        if generated_types:
            await self._run_approval_workflow(article_id)

        return generated_types

    async def _run_approval_workflow(self, article_id: uuid.UUID) -> None:
        """Run AI revision → email notification approval flow."""
        from app.services.email_service import EmailService
        from app.services.revision_service import RevisionService

        try:
            revision_service = RevisionService(self._session)
            revision = await revision_service.revise_article(article_id)

            # If auto-approved, skip email
            if revision.auto_approved:
                logger.info(
                    "article_auto_approved_skipping_email",
                    article_id=str(article_id),
                    quality_score=revision.quality_score,
                )
                return

            # Send approval email
            article = await self._article_repo.get_by_id(article_id)
            if article:
                email_service = EmailService()
                await email_service.send_approval_email(article, revision)

        except Exception as exc:
            logger.error(
                "approval_workflow_failed",
                article_id=str(article_id),
                error=str(exc),
            )
            # Don't fail the enrichment if approval workflow fails
            await self._article_repo.update_status(article_id, "enriched")
