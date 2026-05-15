import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

import app.services.publishing_service as publishing_module
from app.api.schemas import PublishResponse
from app.services.publishing_service import PublishingService


async def build_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    website_publish_result: dict | None = None,
    website_publish_error: Exception | None = None,
    generation_values: dict[str, str] | None = None,
    medium_import_status: str = "queued",
) -> tuple[PublishingService, SimpleNamespace, AsyncMock]:
    service = PublishingService(session=MagicMock())
    article_id = uuid.uuid4()
    article = SimpleNamespace(
        id=article_id,
        slug="test-post",
        title="Original Title",
        status="approved",
        source_path="content/source/test-post.md",
        excerpt="Original excerpt",
        category="AI",
        tags=["ai", "rag"],
        author="ByteMind Team",
        author_role="AI Consulting",
        date_label="May 15, 2026",
        publish_date=datetime(2026, 5, 15, tzinfo=UTC),
        read_time_minutes=8,
        featured=False,
    )
    website_record = SimpleNamespace(raw_response=None, error_message=None)
    bundle_record = SimpleNamespace(raw_response=None, error_message=None)

    async def fake_generation(_article_id: uuid.UUID, prompt_type: str) -> SimpleNamespace | None:
        values = {
            "seo_title": "SEO Title",
            "seo_description": "SEO Description",
            **(generation_values or {}),
        }
        output = values.get(prompt_type)
        return SimpleNamespace(output=output) if output else None

    medium_import_queue = AsyncMock(return_value=SimpleNamespace(status=medium_import_status))

    class FakeMediumImportService:
        def __init__(self, session: MagicMock) -> None:
            self._session = session

        async def queue_for_import(
            self, *, article_id: uuid.UUID, website_url: str, canonical_url: str
        ) -> SimpleNamespace:
            return await medium_import_queue(
                article_id=article_id,
                website_url=website_url,
                canonical_url=canonical_url,
            )

    monkeypatch.setattr(
        "app.services.medium_import_service.MediumImportService", FakeMediumImportService
    )

    service._article_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=article),
        update_status=AsyncMock(),
    )
    service._generation_repo = SimpleNamespace(
        get_latest_by_type=AsyncMock(side_effect=fake_generation)
    )
    service._publishing_repo = SimpleNamespace(
        create=AsyncMock(side_effect=[website_record, bundle_record])
    )
    service._audit_repo = SimpleNamespace(log=AsyncMock())
    service._medium_syndication = SimpleNamespace(
        build_bundle=MagicMock(return_value=Path("content/generated/medium/test-post"))
    )
    service._linkedin = SimpleNamespace(
        save_drafts=MagicMock(return_value=Path("content/generated/linkedin/test-post"))
    )
    service._medium_legacy = SimpleNamespace(publish=AsyncMock())

    monkeypatch.setattr(publishing_module._settings, "github_website_token", "github-token")
    monkeypatch.setattr(
        publishing_module._settings,
        "website_base_url",
        "https://content.bytemind.test",
    )
    monkeypatch.setattr(
        publishing_module._settings,
        "medium_canonical_base_url",
        "https://canonical.bytemind.test",
    )
    monkeypatch.setattr(publishing_module._settings, "medium_integration_token", "")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding="utf-8": "---\ntitle: Source Title\n---\n\n# Heading\n\nBody copy.\n",
    )

    if website_publish_error is not None:
        service._website_publisher = SimpleNamespace(
            publish_article=AsyncMock(side_effect=website_publish_error)
        )
    else:
        service._website_publisher = SimpleNamespace(
            publish_article=AsyncMock(
                return_value=website_publish_result or {"status": "published"}
            )
        )

    return service, website_record, medium_import_queue


@pytest.mark.asyncio
async def test_publish_article_returns_website_commit_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, website_record, medium_import_queue = await build_service(
        monkeypatch,
        website_publish_result={
            "status": "published",
            "commit_sha": "commit-123",
            "path": "src/content/blog/test-post.md",
        },
    )

    result = await service.publish_article(uuid.uuid4())

    assert result["website_commit"] == {
        "status": "published",
        "commit_sha": "commit-123",
        "path": "src/content/blog/test-post.md",
    }
    assert website_record.raw_response == result["website_commit"]
    assert result["medium_import_url"] == "https://medium.com/p/import"
    assert result["medium_import_status"] == "queued"
    medium_import_queue.assert_awaited_once_with(
        article_id=ANY,
        website_url="https://content.bytemind.test/blogs/test-post",
        canonical_url="https://canonical.bytemind.test/test-post",
    )
    service._website_publisher.publish_article.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_article_continues_when_website_push_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, website_record, medium_import_queue = await build_service(
        monkeypatch,
        website_publish_error=RuntimeError("GitHub API failed"),
    )

    result = await service.publish_article(uuid.uuid4())

    assert result["status"] == "published"
    assert result["website_commit"] == {
        "status": "failed",
        "error": "GitHub API failed",
    }
    assert website_record.raw_response == result["website_commit"]
    assert website_record.error_message == "GitHub API failed"
    assert result["medium_import_status"] == "queued"
    assert result["medium_import_url"] == "https://medium.com/p/import"
    medium_import_queue.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_article_uses_public_medium_import_url_and_linkedin_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = await build_service(
        monkeypatch,
        generation_values={
            "linkedin_short": "Short draft",
            "linkedin_medium": "Medium draft",
            "linkedin_technical": "Technical draft",
            "hashtags": "#ai #automation",
            "cta": "Read more",
        },
    )

    result = await service.publish_article(uuid.uuid4(), publisher="medium")

    assert result["medium"]["status"] == "skipped"
    assert result["medium"]["reason"].endswith("https://medium.com/p/import")
    service._linkedin.save_drafts.assert_called_once_with(
        slug="test-post",
        short="Short draft",
        medium="Medium draft",
        technical="Technical draft",
        hashtags="#ai #automation",
        cta="Read more",
        article_title="Original Title",
        website_base_url="https://content.bytemind.test",
    )


def test_publish_response_accepts_website_commit_and_medium_import_fields() -> None:
    response = PublishResponse(
        article_id=str(uuid.uuid4()),
        slug="test-post",
        website_url="https://content.bytemind.test/blogs/test-post",
        canonical_url="https://canonical.bytemind.test/test-post",
        syndication_bundle_path="content/generated/medium/test-post",
        website_commit={"status": "published", "commit_sha": "commit-123"},
        medium={"status": "skipped"},
        medium_import_url="https://medium.com/p/import",
        medium_import_status="queued",
        linkedin_drafts_folder="content/generated/linkedin/test-post",
        status="published",
    )

    assert response.website_commit == {"status": "published", "commit_sha": "commit-123"}
    assert response.medium_import_url == "https://medium.com/p/import"
    assert response.medium_import_status == "queued"
