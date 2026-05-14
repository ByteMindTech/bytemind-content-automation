"""Markdown frontmatter parser for ByteMindTech blog format."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import frontmatter


@dataclass
class ParsedArticle:
    """Parsed representation of a Markdown article."""

    # Frontmatter
    title: str
    slug: str
    date: datetime
    date_label: str
    category: str
    category_color: str
    tags: list[str]
    author: str
    author_role: str
    excerpt: str
    featured: bool = False
    difficulty: str | None = None
    implementation_time: str | None = None
    read_time: str | None = None

    # Extracted content
    raw_markdown: str = ""
    content_body: str = ""  # body without frontmatter block
    headings: list[dict] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    source_path: str = ""

    # Computed
    estimated_read_minutes: int = 0
    word_count: int = 0
    toc: list[dict] = field(default_factory=list)


class MarkdownParser:
    """Parse .md files with YAML frontmatter in ByteMindTech format."""

    REQUIRED_FIELDS = {
        "title", "slug", "date", "dateLabel", "category",
        "categoryColor", "tags", "author", "excerpt",
    }

    # Matches fenced code blocks: ```lang ... ```
    _CODE_BLOCK_RE = re.compile(
        r"```(\w*)\n(.*?)```", re.DOTALL
    )
    # Matches ATX headings: # H1, ## H2, ...
    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def parse_file(self, path: Path) -> ParsedArticle:
        """Parse a single .md file and return a ParsedArticle."""
        raw = path.read_text(encoding="utf-8")
        return self.parse_string(raw, source_path=str(path))

    def parse_string(self, raw: str, source_path: str = "") -> ParsedArticle:
        """Parse raw Markdown string (with YAML frontmatter) into ParsedArticle."""
        post = frontmatter.loads(raw)
        meta = post.metadata
        body = post.content

        self._validate_metadata(meta)

        # Parse date — accept datetime or ISO string
        date_val = meta["date"]
        if isinstance(date_val, datetime):
            publish_date = date_val
        else:
            publish_date = datetime.fromisoformat(str(date_val))

        headings = self._extract_headings(body)
        code_blocks = self._extract_code_blocks(body)
        words = len(body.split())
        est_minutes = max(1, round(words / 200))
        toc = self._build_toc(headings)

        return ParsedArticle(
            title=meta["title"],
            slug=meta["slug"],
            date=publish_date,
            date_label=meta.get("dateLabel", ""),
            category=meta["category"],
            category_color=meta.get("categoryColor", "#00d4ff"),
            tags=meta.get("tags", []),
            author=meta["author"],
            author_role=meta.get("authorRole", ""),
            excerpt=meta["excerpt"],
            featured=bool(meta.get("featured", False)),
            difficulty=meta.get("difficulty"),
            implementation_time=meta.get("implementationTime"),
            read_time=meta.get("readTime"),
            raw_markdown=raw,
            content_body=body,
            headings=headings,
            code_blocks=code_blocks,
            source_path=source_path,
            estimated_read_minutes=est_minutes,
            word_count=words,
            toc=toc,
        )

    def _validate_metadata(self, meta: dict) -> None:
        """Raise ValueError if required frontmatter fields are missing."""
        missing = self.REQUIRED_FIELDS - set(meta.keys())
        if missing:
            raise ValueError(f"Missing required frontmatter fields: {sorted(missing)}")

    def _extract_headings(self, body: str) -> list[dict]:
        return [
            {"level": len(m.group(1)), "text": m.group(2).strip()}
            for m in self._HEADING_RE.finditer(body)
        ]

    def _extract_code_blocks(self, body: str) -> list[dict]:
        return [
            {"language": m.group(1) or "text", "code": m.group(2)}
            for m in self._CODE_BLOCK_RE.finditer(body)
        ]

    def _build_toc(self, headings: list[dict]) -> list[dict]:
        """Build a flat ToC list with anchor slugs from headings."""
        toc = []
        for h in headings:
            anchor = re.sub(r"[^\w\s-]", "", h["text"].lower())
            anchor = re.sub(r"[\s]+", "-", anchor).strip("-")
            toc.append({"level": h["level"], "text": h["text"], "anchor": anchor})
        return toc
