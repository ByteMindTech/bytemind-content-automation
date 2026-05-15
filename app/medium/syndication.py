"""
Medium syndication exporter.

Builds a Medium-ready content bundle the operator can:
  1. Publish on bytemind.fr first, then import by URL via medium.com/p/import
     (recommended)
  2. Publish via the legacy self-issued integration token (optional, only
     for accounts that obtained a token before Medium closed new integrations)

⚠️  Medium's API is no longer supported for new integrations.
    https://github.com/Medium/medium-api-docs
    https://help.medium.com/hc/en-us/articles/213480228-API-Importing

The bundle is saved to:
    content/generated/medium/{slug}/
        article.md       — Markdown body with canonical URL in front-matter
        metadata.json    — Structured metadata for API publish or manual review
        README.md        — Step-by-step operator instructions
"""

from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_OUTPUT_BASE = Path("content/generated/medium")


class MediumSyndicationExporter:
    """
    Builds a complete Medium syndication bundle from enriched article data.

    No Medium API credentials required — the output is designed for URL-based
    import via Medium's import tool or for use with an existing integration
    token.
    """

    def __init__(self) -> None:
        self._canonical_base = _settings.medium_canonical_base_url.rstrip("/")
        self._website_base = _settings.website_base_url.rstrip("/")

    def build_bundle(
        self,
        *,
        slug: str,
        title: str,
        seo_title: str,
        seo_description: str,
        body_markdown: str,
        medium_intro: str,
        tags: list[str],
        hashtags: str,
        cta: str,
        category: str,
        author: str,
        published_date: str,
    ) -> Path:
        """
        Write syndication bundle to disk and return the folder path.

        The canonical URL always points to the website, never to Medium.
        """
        folder = _OUTPUT_BASE / slug
        folder.mkdir(parents=True, exist_ok=True)

        canonical_url = f"{self._canonical_base}/{slug}"
        website_url = f"{self._website_base}/blogs/{slug}"

        # Article body: prepend AI intro if available
        full_body = f"{medium_intro}\n\n{body_markdown}" if medium_intro.strip() else body_markdown

        # article.md — Markdown with front-matter for Medium import
        frontmatter = textwrap.dedent(f"""\
            ---
            title: "{seo_title or title}"
            description: "{seo_description}"
            canonical_url: "{canonical_url}"
            tags: {json.dumps(tags[:5])}
            author: "{author}"
            date: "{published_date}"
            ---
        """)
        article_md = f"{frontmatter}\n{full_body}"
        (folder / "article.md").write_text(article_md, encoding="utf-8")

        # metadata.json — structured payload (usable for token-based API publish too)
        medium_tags = [t.lower().replace(" ", "-") for t in tags[:5]]
        metadata = {
            "title": seo_title or title,
            "original_title": title,
            "seo_description": seo_description,
            "canonical_url": canonical_url,
            "website_url": website_url,
            "medium_import_url": "https://medium.com/p/import",
            "tags": medium_tags,
            "category": category,
            "author": author,
            "published_date": published_date,
            "hashtags": hashtags,
            "cta": cta,
            "medium_api_payload": {
                "title": seo_title or title,
                "contentFormat": "markdown",
                "content": full_body,
                "canonicalUrl": canonical_url,
                "tags": medium_tags,
                "publishStatus": _settings.medium_default_status,
            },
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }
        (folder / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # README.md — operator instructions
        readme = textwrap.dedent(f"""\
            # Medium Syndication — {title}

            Generated: {metadata["generated_at"]}
            Canonical URL: {canonical_url}

            ## How to publish on Medium

            ### Step 1 — Confirm article is live
            Verify the article is accessible at:
              {website_url}

            ### Step 2 — Import on Medium
            1. Go to {metadata["medium_import_url"]}
            2. Paste this URL: {website_url}
            3. Medium will import the article and automatically set the canonical URL
               back to bytemind.fr — preserving your SEO authority.

            ### Step 3 — Review and publish
            1. Review the imported content in Medium's editor
            2. Add tags: {tags}
            3. Click Publish

            ## SEO note
            Medium's import tool automatically sets rel="canonical" to the source URL.
            This means search engines credit bytemind.fr as the original source.
            Canonical URL: {canonical_url}

            ## Alternative: Paste markdown manually
            If you prefer not to use the import tool:
            1. Create a new story on Medium
            2. Copy content from article.md (below the --- front-matter)
            3. Before publishing, go to More settings → set canonical URL to: {canonical_url}
            4. Add tags and publish

            ## Legacy: Token-based API (existing tokens only)
            Medium no longer issues new integration tokens (January 2025).
            Reference: https://help.medium.com/hc/en-us/articles/213480228
            If you have an existing token, use the payload in metadata.json → medium_api_payload.
        """)
        (folder / "README.md").write_text(readme, encoding="utf-8")

        logger.info(
            "medium_syndication_bundle_created",
            slug=slug,
            folder=str(folder),
            canonical_url=canonical_url,
        )
        return folder
