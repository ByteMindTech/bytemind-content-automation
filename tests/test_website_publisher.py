import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.config.settings import Settings
from app.services.website_publisher import WebsitePublisher


def build_settings() -> Settings:
    return Settings.model_construct(
        jwt_secret_key="x" * 32,
        actions_api_key="y" * 32,
        database_url="postgresql+asyncpg://example",
        github_website_token="github-token",
        github_website_repo="ByteMindTech/bytemind-website",
        github_website_blog_path="src/content/blog",
    )


@pytest.mark.asyncio
@respx.mock
async def test_publish_article_creates_markdown_file_with_expected_frontmatter() -> None:
    publisher = WebsitePublisher(settings=build_settings())
    url = (
        "https://api.github.com/repos/ByteMindTech/bytemind-website/"
        "contents/src/content/blog/test-post.md"
    )
    respx.get(url).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    put_route = respx.put(url).mock(
        return_value=httpx.Response(
            201,
            json={
                "content": {
                    "sha": "file-sha-123",
                    "html_url": "https://github.com/ByteMindTech/bytemind-website/blob/main/src/content/blog/test-post.md",
                },
                "commit": {
                    "sha": "commit-sha-123",
                    "html_url": "https://github.com/ByteMindTech/bytemind-website/commit/commit-sha-123",
                },
            },
        )
    )

    source_markdown = """---
title: \"Original Title\"
difficulty: \"Advanced\"
implementationTime: \"2-4 weeks\"
readTime: \"9 min read\"
---

# Hello ByteMind

This is the article body.
"""

    result = await publisher.publish_article(
        slug="test-post",
        source_markdown=source_markdown,
        title="Original Title",
        category="ai",
        tags=["ai", "rag", "vertex-ai"],
        author="ByteMind Team",
        author_role="AI Consulting",
        excerpt="Original excerpt",
        featured=False,
        publish_date=datetime(2026, 5, 15, tzinfo=UTC),
        date_label=None,
        read_time_minutes=8,
        seo_title="SEO Title",
        seo_description="Short description for the website.",
    )

    assert result == {
        "status": "published",
        "action": "created",
        "path": "src/content/blog/test-post.md",
        "repo": "ByteMindTech/bytemind-website",
        "commit_sha": "commit-sha-123",
        "commit_url": "https://github.com/ByteMindTech/bytemind-website/commit/commit-sha-123",
        "file_sha": "file-sha-123",
        "file_url": "https://github.com/ByteMindTech/bytemind-website/blob/main/src/content/blog/test-post.md",
    }

    payload = json.loads(put_route.calls[0].request.content.decode())
    uploaded_markdown = base64.b64decode(payload["content"]).decode("utf-8")

    assert payload["message"] == "chore(blog): publish test-post via automation platform"
    assert 'title: "SEO Title"' in uploaded_markdown
    assert 'slug: "test-post"' in uploaded_markdown
    assert 'date: "2026-05-15"' in uploaded_markdown
    assert 'dateLabel: "May 15, 2026"' in uploaded_markdown
    assert 'category: "AI"' in uploaded_markdown
    assert 'categoryColor: "#4285f4"' in uploaded_markdown
    assert 'tags: ["ai", "rag", "vertex-ai"]' in uploaded_markdown
    assert 'author: "ByteMind Team"' in uploaded_markdown
    assert 'authorRole: "AI Consulting"' in uploaded_markdown
    assert 'readTime: "9 min read"' in uploaded_markdown
    assert "featured: false" in uploaded_markdown
    assert 'difficulty: "Advanced"' in uploaded_markdown
    assert 'implementationTime: "2-4 weeks"' in uploaded_markdown
    assert 'excerpt: "Short description for the website."' in uploaded_markdown
    assert uploaded_markdown.endswith("# Hello ByteMind\n\nThis is the article body.\n")


@pytest.mark.asyncio
@respx.mock
async def test_publish_article_updates_existing_file_with_sha() -> None:
    publisher = WebsitePublisher(settings=build_settings())
    url = (
        "https://api.github.com/repos/ByteMindTech/bytemind-website/"
        "contents/src/content/blog/security-patterns.md"
    )
    respx.get(url).mock(return_value=httpx.Response(200, json={"sha": "existing-sha"}))
    put_route = respx.put(url).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": {"sha": "new-file-sha", "html_url": "https://github.com/file"},
                "commit": {"sha": "new-commit-sha", "html_url": "https://github.com/commit"},
            },
        )
    )

    result = await publisher.publish_article(
        slug="security-patterns",
        source_markdown="# Heading\n\nUseful body copy.",
        title="Security Patterns",
        category="Security",
        tags=["security", "zero-trust"],
        author="",
        author_role=None,
        excerpt="Fallback excerpt",
        featured=True,
        publish_date=datetime(2026, 6, 1, tzinfo=UTC),
        date_label="Jun 1, 2026",
        read_time_minutes=11,
        seo_title="",
        seo_description="",
    )

    assert result["action"] == "updated"
    payload = json.loads(put_route.calls[0].request.content.decode())
    assert payload["sha"] == "existing-sha"

    uploaded_markdown = base64.b64decode(payload["content"]).decode("utf-8")
    assert 'author: "ByteMind Team"' in uploaded_markdown
    assert 'authorRole: "AI Consulting"' in uploaded_markdown
    assert 'readTime: "11 min read"' in uploaded_markdown
    assert "featured: true" in uploaded_markdown
    assert 'excerpt: "Fallback excerpt"' in uploaded_markdown
