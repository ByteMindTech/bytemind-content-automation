"""AI revision service — final quality review before publishing."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AIEngine, PromptTemplate
from app.config import get_settings
from app.models import AIGeneration, Article, ArticleRevision
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()

REVISION_PROMPT_TEMPLATE = """You are a senior technical content reviewer for ByteMind, an enterprise AI & cloud consultancy.

Review the following AI-generated content for a blog article and provide a quality assessment.

## Original Article
Title: {title}
Category: {category}
Tags: {tags}

## Generated Content to Review
{generated_content}

## Review Instructions
Evaluate the generated content on these criteria:
1. **Accuracy** — No hallucinated tools, commands, or architecture claims
2. **Coherence** — Logical flow, consistent tone
3. **Brand Voice** — Professional, authoritative, enterprise-focused
4. **SEO Quality** — Relevant keywords, compelling titles
5. **Technical Depth** — Maintains precision without oversimplification

## Required Output (JSON only, no markdown fences)
{{
  "quality_score": <1-10 integer>,
  "issues": [
    {{"severity": "high|medium|low", "field": "<prompt_type>", "description": "<issue>"}}
  ],
  "suggestions": {{
    "<prompt_type>": "<specific improvement suggestion>"
  }},
  "summary": "<2-3 sentence overall assessment>"
}}
"""


class RevisionService:
    """Performs AI-powered final quality review of enriched article content."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ai = AIEngine()

    async def revise_article(self, article_id: uuid.UUID) -> ArticleRevision:
        """
        Run AI revision on all generated content for an article.
        Returns the ArticleRevision record with quality_score.
        """
        # Fetch article
        result = await self._session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        # Fetch all generations for this article
        gen_result = await self._session.execute(
            select(AIGeneration)
            .where(AIGeneration.article_id == article_id)
            .order_by(AIGeneration.created_at)
        )
        generations = gen_result.scalars().all()

        if not generations:
            raise ValueError(f"No generated content found for article {article_id}")

        # Build the generated content summary for review
        generated_content = self._format_generations(generations)

        # Build revision prompt
        prompt_text = REVISION_PROMPT_TEMPLATE.format(
            title=article.title,
            category=article.category,
            tags=", ".join(article.tags or []),
            generated_content=generated_content,
        )

        prompt = PromptTemplate(
            prompt_type="revision",
            text=prompt_text,
            max_output_tokens=1024,
        )

        # Update article status
        article.status = "revising"
        await self._session.commit()

        # Call AI for revision
        ai_result = await self._ai.generate(prompt, source_body="")

        # Parse the JSON output
        revision_data = self._parse_revision_output(ai_result.output)

        # Determine auto-approval
        quality_score = revision_data.get("quality_score", 0)
        auto_approved = quality_score >= _settings.auto_approve_threshold

        # Create revision record
        revision = ArticleRevision(
            article_id=article_id,
            quality_score=quality_score,
            auto_approved=auto_approved,
            issues=revision_data.get("issues"),
            suggestions=revision_data.get("suggestions"),
            summary=revision_data.get("summary", "Revision completed"),
            provider=ai_result.provider,
            model=ai_result.model,
            tokens_input=ai_result.tokens_input,
            tokens_output=ai_result.tokens_output,
            cost_usd=ai_result.cost_usd,
        )
        self._session.add(revision)

        # Update article status based on auto-approval
        if auto_approved:
            article.status = "approved"
            logger.info(
                "article_auto_approved",
                article_id=str(article_id),
                quality_score=quality_score,
            )
        else:
            article.status = "awaiting_approval"
            logger.info(
                "article_awaiting_approval",
                article_id=str(article_id),
                quality_score=quality_score,
            )

        await self._session.commit()
        await self._session.refresh(revision)
        return revision

    def _format_generations(self, generations: list[AIGeneration]) -> str:
        """Format all generations into a readable block for the revision prompt."""
        parts = []
        for gen in generations:
            parts.append(f"### {gen.prompt_type}\n{gen.output}\n")
        return "\n".join(parts)

    def _parse_revision_output(self, output: str) -> dict[str, Any]:
        """Parse AI revision JSON output with fallback."""
        # Strip markdown code fences if present
        cleaned = output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(cleaned)
            # Validate expected fields
            if "quality_score" not in data:
                data["quality_score"] = 5
            data["quality_score"] = max(1, min(10, int(data["quality_score"])))
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("revision_parse_failed", error=str(exc), raw_output=output[:200])
            return {
                "quality_score": 5,
                "issues": [{"severity": "low", "field": "parsing", "description": "Could not parse revision output"}],
                "suggestions": {},
                "summary": output[:500],
            }
