"""Medium publisher — full API client with dry-run mode."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()

MEDIUM_API_BASE = "https://api.medium.com/v1"


class MediumPublisher:
    """
    Publishes articles to Medium via the Integration Token API.

    Set MEDIUM_DRY_RUN=true (default) to skip actual API calls
    during development or when no token is configured.
    """

    def __init__(self) -> None:
        self._token = _settings.medium_integration_token
        self._author_id = _settings.medium_author_id
        self._dry_run = _settings.medium_dry_run
        self._default_status = _settings.medium_default_status
        self._canonical_base = _settings.medium_canonical_base_url

    async def publish(
        self,
        *,
        slug: str,
        title: str,
        body_markdown: str,
        tags: list[str],
        canonical_slug: str | None = None,
        publish_status: str | None = None,
        scheduled_at: datetime | None = None,
    ) -> dict:
        """
        Publish an article to Medium.

        Returns a dict with keys: medium_id, url, status, dry_run.
        """
        canonical_url = (
            f"{self._canonical_base}/{canonical_slug or slug}"
        )
        html_body = self._markdown_to_html(body_markdown, title)
        payload = {
            "title": title,
            "contentFormat": "html",
            "content": html_body,
            "tags": tags[:5],  # Medium supports max 5 tags
            "canonicalUrl": canonical_url,
            "publishStatus": publish_status or self._default_status,
        }

        if self._dry_run:
            logger.info(
                "medium_dry_run",
                slug=slug,
                title=title,
                tags=tags,
                dry_run=True,
            )
            return {
                "medium_id": f"dry-run-{uuid.uuid4().hex[:8]}",
                "url": f"https://medium.com/bytemind/dry-run-{slug}",
                "status": "dry_run",
                "dry_run": True,
                "payload": payload,
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{MEDIUM_API_BASE}/users/{self._author_id}/posts",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()["data"]

        logger.info(
            "medium_published",
            slug=slug,
            medium_id=data["id"],
            url=data["url"],
        )
        return {
            "medium_id": data["id"],
            "url": data["url"],
            "status": "published",
            "dry_run": False,
            "raw": data,
        }

    async def get_author_id(self) -> str:
        """Fetch Medium author ID from the API using the integration token."""
        if self._dry_run:
            return "dry-run-author"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{MEDIUM_API_BASE}/me",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            return resp.json()["data"]["id"]

    # ── Markdown → HTML conversion ────────────────────────────────────────────

    def _markdown_to_html(self, markdown: str, title: str) -> str:
        """
        Convert Markdown to Medium-compatible HTML.

        Medium accepts a subset of HTML. We handle:
        - Headings (h1–h4)
        - Bold, italic
        - Code blocks → <pre><code>
        - Inline code
        - Blockquotes
        - Unordered / ordered lists
        - Paragraphs
        """
        lines = markdown.split("\n")
        html_lines: list[str] = [f"<h1>{title}</h1>"]
        in_code_block = False
        code_lang = ""
        code_buffer: list[str] = []
        in_list: str | None = None  # "ul" | "ol"

        for line in lines:
            # Fenced code blocks
            if line.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_lang = line[3:].strip() or "text"
                    code_buffer = []
                else:
                    in_code_block = False
                    code = "\n".join(code_buffer)
                    html_lines.append(
                        f'<pre><code class="language-{code_lang}">'
                        f"{self._escape_html(code)}</code></pre>"
                    )
                continue

            if in_code_block:
                code_buffer.append(line)
                continue

            # Close list if leaving list context
            if in_list and not (line.startswith("- ") or re.match(r"^\d+\.\s", line)):
                html_lines.append(f"</{in_list}>")
                in_list = None

            # ATX headings
            if line.startswith("#### "):
                html_lines.append(f"<h4>{self._inline(line[5:])}</h4>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{self._inline(line[4:])}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{self._inline(line[3:])}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h2>{self._inline(line[2:])}</h2>")  # demote h1
            # Blockquote
            elif line.startswith("> "):
                html_lines.append(f"<blockquote>{self._inline(line[2:])}</blockquote>")
            # Unordered list
            elif line.startswith("- "):
                if in_list != "ul":
                    if in_list:
                        html_lines.append(f"</{in_list}>")
                    html_lines.append("<ul>")
                    in_list = "ul"
                html_lines.append(f"<li>{self._inline(line[2:])}</li>")
            # Ordered list
            elif re.match(r"^\d+\.\s", line):
                if in_list != "ol":
                    if in_list:
                        html_lines.append(f"</{in_list}>")
                    html_lines.append("<ol>")
                    in_list = "ol"
                content = re.sub(r"^\d+\.\s", "", line)
                html_lines.append(f"<li>{self._inline(content)}</li>")
            # Horizontal rule
            elif line.strip() in ("---", "***", "___"):
                html_lines.append("<hr>")
            # Empty line
            elif not line.strip():
                html_lines.append("<br>")
            # Paragraph
            else:
                html_lines.append(f"<p>{self._inline(line)}</p>")

        if in_list:
            html_lines.append(f"</{in_list}>")

        return "\n".join(html_lines)

    def _inline(self, text: str) -> str:
        """Apply inline Markdown to HTML conversions."""
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # Italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        # Inline code
        text = re.sub(r"`(.+?)`", lambda m: f"<code>{self._escape_html(m.group(1))}</code>", text)
        # Links
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
