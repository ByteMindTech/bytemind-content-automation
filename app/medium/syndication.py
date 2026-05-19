"""
Medium syndication exporter.

Builds a Medium-ready content bundle the operator can:
  1. Import manually via medium.com/me/import (recommended)
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
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_OUTPUT_BASE = Path("content/generated/medium")


class MediumSyndicationExporter:
    """
    Builds a complete Medium syndication bundle from enriched article data.

    No Medium API credentials required — the output is designed for manual
    import OR for use with an existing integration token.
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
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        (folder / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # README.md — operator instructions
        readme = textwrap.dedent(f"""\
            # Medium Syndication Bundle — {title}

            Generated: {metadata["generated_at"]}
            Canonical URL: {canonical_url}

            ## How to publish on Medium

            ### Option A — Manual import (recommended)
            1. Log in to Medium at https://medium.com
            2. Click your profile → **Stories** → **Import a story**
            3. Paste the canonical URL: `{canonical_url}`
            4. Medium will import the article and automatically apply the canonical
               link back to your website, protecting your SEO.
            5. Review the imported content, then click **Publish**.

            ### Option B — Paste the Markdown content
            1. Log in to Medium and create a new story.
            2. Open `article.md` in this folder.
            3. Copy the content body (below the `---` front-matter block).
            4. Paste into the Medium editor.
            5. Before publishing, go to **More settings** → set the canonical URL to:
               `{canonical_url}`
            6. Add tags from `metadata.json` and publish.

            ### Option C — Token-based API (existing integration tokens only)
            Medium no longer issues new integration tokens (as of January 2025).
            Reference: https://help.medium.com/hc/en-us/articles/213480228-API-Importing

            If you already have a self-issued integration token, you can use
            the payload in `metadata.json` → `medium_api_payload` with:
                POST https://api.medium.com/v1/users/{{authorId}}/posts
                Authorization: Bearer {{your_token}}

            ## SEO note
            Always ensure the canonical URL is set to:
                {canonical_url}
            This signals to search engines that {website_url} is the original source,
            preventing duplicate-content penalties.
        """)
        (folder / "README.md").write_text(readme, encoding="utf-8")

        logger.info(
            "medium_syndication_bundle_created",
            slug=slug,
            folder=str(folder),
            canonical_url=canonical_url,
        )
        return folder
