"""Analytics service — aggregated metrics from the DB."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIGeneration, Article, PublishingHistory, TokenUsage


class AnalyticsService:
    """Read-only analytics queries over the content automation DB."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self) -> dict:
        """Return high-level platform summary."""
        # Article counts by status
        art_result = await self._session.execute(
            select(Article.status, func.count(Article.id)).group_by(Article.status)
        )
        article_counts = {row[0]: row[1] for row in art_result.all()}

        # Publishing counts by status
        pub_result = await self._session.execute(
            select(PublishingHistory.status, func.count(PublishingHistory.id)).group_by(
                PublishingHistory.status
            )
        )
        publish_counts = {row[0]: row[1] for row in pub_result.all()}

        # Total AI cost
        cost_result = await self._session.execute(
            select(func.sum(AIGeneration.cost_usd))
        )
        total_cost = cost_result.scalar_one_or_none() or 0.0

        # Total tokens
        tokens_result = await self._session.execute(
            select(
                func.sum(AIGeneration.tokens_input),
                func.sum(AIGeneration.tokens_output),
            )
        )
        tok_row = tokens_result.one()
        total_tokens_in = tok_row[0] or 0
        total_tokens_out = tok_row[1] or 0

        return {
            "articles": article_counts,
            "publishing": publish_counts,
            "ai": {
                "total_cost_usd": round(total_cost, 4),
                "total_tokens_input": total_tokens_in,
                "total_tokens_output": total_tokens_out,
            },
        }

    async def token_usage_by_date(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        provider: str | None = None,
    ) -> list[dict]:
        q = select(
            TokenUsage.date,
            TokenUsage.provider,
            TokenUsage.model,
            func.sum(TokenUsage.tokens_input).label("tokens_input"),
            func.sum(TokenUsage.tokens_output).label("tokens_output"),
            func.sum(TokenUsage.total_cost_usd).label("cost_usd"),
            func.sum(TokenUsage.call_count).label("calls"),
        ).group_by(TokenUsage.date, TokenUsage.provider, TokenUsage.model)

        if since:
            q = q.where(TokenUsage.date >= since)
        if until:
            q = q.where(TokenUsage.date <= until)
        if provider:
            q = q.where(TokenUsage.provider == provider)

        q = q.order_by(TokenUsage.date.desc())
        result = await self._session.execute(q)
        return [
            {
                "date": row.date.isoformat(),
                "provider": row.provider,
                "model": row.model,
                "tokens_input": row.tokens_input,
                "tokens_output": row.tokens_output,
                "cost_usd": round(row.cost_usd, 6),
                "calls": row.calls,
            }
            for row in result.all()
        ]

    async def published_articles(
        self,
        category: str | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        q = (
            select(
                Article.slug,
                Article.title,
                Article.category,
                Article.author,
                Article.publish_date,
                Article.read_time_minutes,
                PublishingHistory.url,
                PublishingHistory.published_at,
                PublishingHistory.publisher,
            )
            .join(PublishingHistory, PublishingHistory.article_id == Article.id)
            .where(PublishingHistory.status.in_(["published", "dry_run"]))
        )
        if category:
            q = q.where(Article.category == category)
        if since:
            q = q.where(PublishingHistory.published_at >= since)
        q = q.order_by(PublishingHistory.published_at.desc())

        result = await self._session.execute(q)
        return [
            {
                "slug": row.slug,
                "title": row.title,
                "category": row.category,
                "author": row.author,
                "publish_date": row.publish_date.isoformat() if row.publish_date else None,
                "read_time_minutes": row.read_time_minutes,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "publisher": row.publisher,
            }
            for row in result.all()
        ]
