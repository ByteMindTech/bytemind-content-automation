"""Medium import queue and status endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    MarkImportedRequest,
    MediumImportQueueItem,
    MediumImportStatusResponse,
)
from app.repositories import get_db
from app.security import require_api_key
from app.services.medium_import_service import MediumImportService

router = APIRouter()


@router.get("/queue", response_model=list[MediumImportQueueItem])
async def get_medium_import_queue(
    _actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    import_status: str | None = Query(None, alias="status", description="Filter by import status"),
    limit: int = Query(50, ge=1, le=100),
) -> list[MediumImportQueueItem]:
    """List Medium import queue entries."""
    service = MediumImportService(db)
    items = await service.get_import_queue(status=import_status, limit=limit)
    return [MediumImportQueueItem(**item) for item in items]


@router.get("/{article_id}", response_model=MediumImportStatusResponse)
async def get_medium_import_status(
    article_id: uuid.UUID,
    _actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MediumImportStatusResponse:
    """Get Medium import status for a single article."""
    service = MediumImportService(db)
    try:
        result = await service.get_import_status(article_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MediumImportStatusResponse(**result)


@router.post("/{article_id}/imported", response_model=MediumImportStatusResponse)
async def mark_medium_imported(
    article_id: uuid.UUID,
    body: MarkImportedRequest,
    _actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MediumImportStatusResponse:
    """Mark a queued article as imported on Medium."""
    service = MediumImportService(db)
    try:
        result = await service.mark_as_imported(article_id, body.medium_url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MediumImportStatusResponse(**result)


@router.post("/{article_id}/verify-canonical", response_model=MediumImportStatusResponse)
async def verify_medium_canonical(
    article_id: uuid.UUID,
    _actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MediumImportStatusResponse:
    """Verify the canonical URL on a Medium-imported article."""
    service = MediumImportService(db)
    try:
        result = await service.verify_canonical(article_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return MediumImportStatusResponse(**result)
