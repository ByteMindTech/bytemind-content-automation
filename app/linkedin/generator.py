"""LinkedIn draft generator — saves 3 content variants to disk."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

_OUTPUT_BASE = Path("content/generated/linkedin")


def _append_article_link(text: str, url: str) -> str:
    """Append the article URL to a LinkedIn draft."""
    if url in text:
        return text
    return f"{text}\n\n🔗 Read the full article: {url}"


class LinkedInGenerator:
    """
    Saves AI-generated LinkedIn content variants to the filesystem.
    Does NOT auto-publish to LinkedIn (future integration).

    Output structure:
        content/generated/linkedin/{slug}/
            short.txt
            medium.txt
            technical.txt
            hashtags.txt
            cta.txt
            article_url.txt
            metadata.json
    """

    def save_drafts(
        self,
        *,
        slug: str,
        short: str,
        medium: str,
        technical: str,
        hashtags: str,
        cta: str,
        article_title: str,
        website_base_url: str = "https://bytemind.fr",
    ) -> Path:
        """
        Save all LinkedIn variants to disk.
        Returns the folder path.
        """
        folder = _OUTPUT_BASE / slug
        folder.mkdir(parents=True, exist_ok=True)

        article_url = (
            f"{website_base_url.rstrip('/')}/blogs/{slug}"
            "?utm_source=linkedin&utm_medium=social&utm_campaign=blog"
        )
        short = _append_article_link(short, article_url)
        medium = _append_article_link(medium, article_url)
        technical = _append_article_link(technical, article_url)

        (folder / "short.txt").write_text(short, encoding="utf-8")
        (folder / "medium.txt").write_text(medium, encoding="utf-8")
        (folder / "technical.txt").write_text(technical, encoding="utf-8")
        (folder / "hashtags.txt").write_text(hashtags, encoding="utf-8")
        (folder / "cta.txt").write_text(cta, encoding="utf-8")
        (folder / "article_url.txt").write_text(article_url, encoding="utf-8")

        metadata = {
            "slug": slug,
            "article_title": article_title,
            "article_url": article_url,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "variants": ["short", "medium", "technical"],
            "utm_source": "linkedin",
            "utm_medium": "social",
            "utm_campaign": "blog",
        }
        (folder / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info("linkedin_drafts_saved", slug=slug, folder=str(folder))
        return folder

    def load_drafts(self, slug: str) -> dict[str, str]:
        """Load existing LinkedIn drafts for a given slug."""
        folder = _OUTPUT_BASE / slug
        if not folder.exists():
            raise FileNotFoundError(f"No LinkedIn drafts found for slug '{slug}'")
        return {
            "short": (folder / "short.txt").read_text(encoding="utf-8"),
            "medium": (folder / "medium.txt").read_text(encoding="utf-8"),
            "technical": (folder / "technical.txt").read_text(encoding="utf-8"),
            "hashtags": (folder / "hashtags.txt").read_text(encoding="utf-8"),
            "cta": (folder / "cta.txt").read_text(encoding="utf-8"),
        }

    def list_generated(self) -> list[str]:
        """Return slugs that have generated LinkedIn drafts."""
        if not _OUTPUT_BASE.exists():
            return []
        return [d.name for d in _OUTPUT_BASE.iterdir() if d.is_dir()]
