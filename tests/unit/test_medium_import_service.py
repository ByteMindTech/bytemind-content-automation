"""Unit tests for Medium import service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.medium_import_service import MediumImportService


@pytest.mark.asyncio
async def test_get_import_queue_builds_operator_payload() -> None:
    article_id = uuid.uuid4()
    created_at = datetime.now(tz=UTC)
    record = SimpleNamespace(
        article_id=article_id,
        website_url="https://bytemind.fr/blogs/test-article",
        canonical_url="https://bytemind.fr/blogs/test-article",
        status="queued",
        created_at=created_at,
        imported_at=None,
        article=SimpleNamespace(
            slug="test-article",
            title="Test Article",
            tags=["ai", "python"],
            excerpt="Test excerpt",
        ),
    )

    with (
        patch("app.services.medium_import_service.ArticleRepository") as article_repo_cls,
        patch("app.services.medium_import_service.AIGenerationRepository") as gen_repo_cls,
        patch("app.services.medium_import_service.MediumImportRepository") as import_repo_cls,
    ):
        article_repo_cls.return_value = AsyncMock()
        gen_repo = AsyncMock()
        gen_repo.get_latest_by_type.return_value = SimpleNamespace(output="SEO Title")
        gen_repo_cls.return_value = gen_repo
        import_repo = AsyncMock()
        import_repo.list_queue.return_value = [record]
        import_repo_cls.return_value = import_repo

        service = MediumImportService(AsyncMock())
        result = await service.get_import_queue(limit=10)

    assert result == [
        {
            "article_id": str(article_id),
            "slug": "test-article",
            "title": "Test Article",
            "website_article_url": "https://bytemind.fr/blogs/test-article",
            "medium_import_url": "https://medium.com/p/import",
            "canonical_url": "https://bytemind.fr/blogs/test-article",
            "status": "queued",
            "seo_title": "SEO Title",
            "tags": ["ai", "python"],
            "excerpt": "Test excerpt",
            "queued_at": created_at,
            "imported_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_mark_as_imported_returns_updated_status() -> None:
    article_id = uuid.uuid4()
    import_id = uuid.uuid4()
    updated_record = SimpleNamespace(
        id=import_id,
        article_id=article_id,
        status="imported",
        website_url="https://bytemind.fr/blogs/test-article",
        canonical_url="https://bytemind.fr/blogs/test-article",
        medium_url="https://medium.com/@bytemind/test-article",
        canonical_verified=False,
        canonical_found=None,
        verified_at=None,
    )

    with (
        patch("app.services.medium_import_service.ArticleRepository") as article_repo_cls,
        patch("app.services.medium_import_service.AIGenerationRepository") as gen_repo_cls,
        patch("app.services.medium_import_service.MediumImportRepository") as import_repo_cls,
    ):
        article_repo_cls.return_value = AsyncMock()
        gen_repo_cls.return_value = AsyncMock()
        import_repo = AsyncMock()
        import_repo.get_by_article_id.return_value = SimpleNamespace(id=import_id)
        import_repo.get_by_id.return_value = updated_record
        import_repo_cls.return_value = import_repo

        service = MediumImportService(AsyncMock())
        result = await service.mark_as_imported(article_id, updated_record.medium_url)

    import_repo.mark_imported.assert_awaited_once_with(import_id, updated_record.medium_url)
    assert result["article_id"] == str(article_id)
    assert result["status"] == "imported"
    assert result["medium_url"] == updated_record.medium_url


@pytest.mark.asyncio
async def test_verify_canonical_returns_updated_status() -> None:
    article_id = uuid.uuid4()
    import_id = uuid.uuid4()
    medium_url = "https://medium.com/@bytemind/test-article"
    canonical_url = "https://bytemind.fr/blogs/test-article"
    verified_record = SimpleNamespace(
        id=import_id,
        article_id=article_id,
        status="verified",
        website_url=canonical_url,
        canonical_url=canonical_url,
        medium_url=medium_url,
        canonical_verified=True,
        canonical_found=canonical_url,
        verified_at=datetime.now(tz=UTC),
    )

    with (
        patch("app.services.medium_import_service.ArticleRepository") as article_repo_cls,
        patch("app.services.medium_import_service.AIGenerationRepository") as gen_repo_cls,
        patch("app.services.medium_import_service.MediumImportRepository") as import_repo_cls,
        patch("app.services.medium_import_service.CanonicalVerifier") as verifier_cls,
    ):
        article_repo_cls.return_value = AsyncMock()
        gen_repo_cls.return_value = AsyncMock()
        import_repo = AsyncMock()
        import_repo.get_by_article_id.return_value = SimpleNamespace(
            id=import_id,
            article_id=article_id,
            status="imported",
            medium_url=medium_url,
            canonical_url=canonical_url,
        )
        import_repo.get_by_id.return_value = verified_record
        import_repo_cls.return_value = import_repo
        verifier = AsyncMock()
        verifier.verify_canonical.return_value = {
            "verified": True,
            "canonical_found": canonical_url,
            "expected_canonical": canonical_url,
            "medium_url": medium_url,
            "error": None,
        }
        verifier_cls.return_value = verifier

        service = MediumImportService(AsyncMock())
        result = await service.verify_canonical(article_id)

    verifier.verify_canonical.assert_awaited_once_with(medium_url, canonical_url)
    import_repo.mark_verified.assert_awaited_once_with(
        import_id,
        canonical_found=canonical_url,
        verified=True,
    )
    assert result["status"] == "verified"
    assert result["canonical_verified"] is True
    assert result["canonical_found"] == canonical_url


@pytest.mark.asyncio
async def test_verify_canonical_requires_imported_status() -> None:
    article_id = uuid.uuid4()

    with (
        patch("app.services.medium_import_service.ArticleRepository") as article_repo_cls,
        patch("app.services.medium_import_service.AIGenerationRepository") as gen_repo_cls,
        patch("app.services.medium_import_service.MediumImportRepository") as import_repo_cls,
    ):
        article_repo_cls.return_value = AsyncMock()
        gen_repo_cls.return_value = AsyncMock()
        import_repo = AsyncMock()
        import_repo.get_by_article_id.return_value = SimpleNamespace(
            id=uuid.uuid4(),
            article_id=article_id,
            status="queued",
            medium_url=None,
            canonical_url="https://bytemind.fr/blogs/test-article",
        )
        import_repo_cls.return_value = import_repo

        service = MediumImportService(AsyncMock())
        with pytest.raises(ValueError, match="not ready for canonical verification"):
            await service.verify_canonical(article_id)
