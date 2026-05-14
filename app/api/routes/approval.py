"""Approval endpoints — approve/reject articles via signed JWT links."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article
from app.repositories import get_db
from app.services.email_service import EmailService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _success_page(title: str, message: str, color: str) -> str:
    """Generate a simple HTML response page."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f8f9fa;">
    <div style="text-align: center; background: white; padding: 48px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <h1 style="color: {color}; font-size: 48px; margin-bottom: 16px;">{'✅' if 'approve' in title.lower() else '❌'}</h1>
        <h2 style="color: #333;">{title}</h2>
        <p style="color: #666; line-height: 1.6;">{message}</p>
    </div>
</body>
</html>"""


@router.get("/approve/{token}", response_class=HTMLResponse)
async def approve_article(token: str) -> HTMLResponse:
    """Approve an article for publishing via signed token link."""
    payload = EmailService.decode_approval_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired approval token",
        )

    article_id = payload.get("article_id")
    action = payload.get("action")

    if action != "approve" or not article_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token payload",
        )

    # Get DB session
    from app.repositories.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(Article).where(Article.id == uuid.UUID(article_id))
        )
        article = result.scalar_one_or_none()

        if article is None:
            raise HTTPException(status_code=404, detail="Article not found")

        if article.status == "published":
            return HTMLResponse(
                _success_page("Already Published", f'"{article.title}" was already published.', "#3498db"),
                status_code=200,
            )

        if article.status not in ("awaiting_approval", "enriched", "revising"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Article is in '{article.status}' state and cannot be approved",
            )

        article.status = "approved"
        await session.commit()

        logger.info("article_approved_via_email", article_id=article_id, title=article.title)

    return HTMLResponse(
        _success_page(
            "Article Approved",
            f'"{article.title}" has been approved and will be published shortly.',
            "#27ae60",
        ),
        status_code=200,
    )


@router.get("/reject/{token}", response_class=HTMLResponse)
async def reject_article(token: str) -> HTMLResponse:
    """Reject an article via signed token link."""
    payload = EmailService.decode_approval_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired approval token",
        )

    article_id = payload.get("article_id")
    action = payload.get("action")

    if action != "reject" or not article_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token payload",
        )

    from app.repositories.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(Article).where(Article.id == uuid.UUID(article_id))
        )
        article = result.scalar_one_or_none()

        if article is None:
            raise HTTPException(status_code=404, detail="Article not found")

        if article.status == "rejected":
            return HTMLResponse(
                _success_page("Already Rejected", f'"{article.title}" was already rejected.', "#e74c3c"),
                status_code=200,
            )

        article.status = "rejected"
        await session.commit()

        logger.info("article_rejected_via_email", article_id=article_id, title=article.title)

    return HTMLResponse(
        _success_page(
            "Article Rejected",
            f'"{article.title}" has been rejected. You can re-enrich it later.',
            "#e74c3c",
        ),
        status_code=200,
    )
