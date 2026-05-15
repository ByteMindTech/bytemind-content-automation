"""Push enriched website articles to the ByteMindTech GitHub repository."""

from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

import frontmatter
import httpx

from app.config import Settings, get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

CATEGORY_COLORS: dict[str, str] = {
    "AI": "#4285f4",
    "Data Engineering": "#34a853",
    "Cloud": "#fbbc05",
    "Security": "#ea4335",
    "DevOps": "#ff6d01",
    "General": "#9aa0a6",
}

_CATEGORY_ALIASES: dict[str, str] = {
    "ai": "AI",
    "ai & enterprise intelligence": "AI",
    "cloud": "Cloud",
    "cloud & gcp architecture": "Cloud",
    "cloud & infrastructure": "Cloud",
    "data": "Data Engineering",
    "data engineering": "Data Engineering",
    "devops": "DevOps",
    "general": "General",
    "security": "Security",
}

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"


class WebsitePublisher:
    """Publish Markdown articles into the website repository via GitHub's Contents API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._owner, self._repo = self._parse_repo(self._settings.github_website_repo)

    async def publish_article(
        self,
        *,
        slug: str,
        source_markdown: str,
        title: str,
        category: str,
        tags: list[str],
        author: str,
        author_role: str | None,
        excerpt: str,
        featured: bool,
        publish_date: datetime | None,
        date_label: str | None,
        read_time_minutes: int | None,
        seo_title: str = "",
        seo_description: str = "",
    ) -> dict[str, Any]:
        """Create or update the website Markdown file for a published article."""
        token = self._settings.github_website_token.strip()
        if not token:
            raise ValueError("github_website_token is not configured")

        body, metadata = self._parse_source_markdown(source_markdown)
        published_on = self._resolve_publish_date(publish_date, metadata.get("date"))
        website_markdown = self._build_markdown(
            slug=slug,
            title=seo_title or title,
            body=body,
            category=self._normalize_category(
                self._string_value(metadata.get("category"), category or "General")
            ),
            tags=self._normalize_tags(metadata.get("tags"), tags),
            author=self._string_value(metadata.get("author"), author or "ByteMind Team"),
            author_role=self._string_value(
                metadata.get("authorRole"), author_role or "AI Consulting"
            ),
            excerpt=self._resolve_excerpt(
                seo_description=seo_description,
                source_excerpt=metadata.get("excerpt"),
                fallback_excerpt=excerpt,
                body=body,
                title=seo_title or title,
            ),
            featured=featured,
            publish_date=published_on,
            date_label=self._resolve_date_label(
                date_label,
                metadata.get("dateLabel"),
                published_on,
            ),
            read_time=self._resolve_read_time(
                metadata.get("readTime"), read_time_minutes=read_time_minutes, body=body
            ),
            difficulty=self._string_value(metadata.get("difficulty")),
            implementation_time=self._string_value(metadata.get("implementationTime")),
        )
        target_path = self._target_path(slug)
        encoded_content = base64.b64encode(website_markdown.encode("utf-8")).decode("utf-8")
        commit_message = f"chore(blog): publish {slug} via automation platform"

        async with httpx.AsyncClient(
            headers=self._headers(token),
            timeout=30.0,
        ) as client:
            existing_sha = await self._get_existing_sha(client, target_path)
            response = await client.put(
                self._contents_url(target_path),
                json={
                    "message": commit_message,
                    "content": encoded_content,
                    **({"sha": existing_sha} if existing_sha else {}),
                },
            )

        self._raise_for_status(response, operation="publish website article")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub publish response was not a JSON object")

        content_info = payload.get("content") if isinstance(payload.get("content"), dict) else {}
        commit_info = payload.get("commit") if isinstance(payload.get("commit"), dict) else {}
        action = "updated" if existing_sha else "created"
        result = {
            "status": "published",
            "action": action,
            "path": target_path,
            "repo": self._settings.github_website_repo,
            "commit_sha": self._string_value(commit_info.get("sha")),
            "commit_url": self._string_value(commit_info.get("html_url")),
            "file_sha": self._string_value(content_info.get("sha")),
            "file_url": self._string_value(content_info.get("html_url")),
        }
        logger.info(
            "website_repo_publish_succeeded",
            slug=slug,
            path=target_path,
            repo=self._settings.github_website_repo,
            action=action,
            commit_sha=result["commit_sha"],
        )
        return result

    def _target_path(self, slug: str) -> str:
        base_path = self._settings.github_website_blog_path.strip("/")
        return f"{base_path}/{slug}.md" if base_path else f"{slug}.md"

    def _build_markdown(
        self,
        *,
        slug: str,
        title: str,
        body: str,
        category: str,
        tags: list[str],
        author: str,
        author_role: str,
        excerpt: str,
        featured: bool,
        publish_date: date,
        date_label: str,
        read_time: str,
        difficulty: str,
        implementation_time: str,
    ) -> str:
        category_color = self._category_color(category)
        body_content = body.lstrip("\n") or excerpt
        frontmatter_block = "\n".join(
            [
                "---",
                f"title: {self._yaml_string(title)}",
                f"slug: {self._yaml_string(slug)}",
                f"date: {self._yaml_string(publish_date.isoformat())}",
                f"dateLabel: {self._yaml_string(date_label)}",
                f"category: {self._yaml_string(category)}",
                f"categoryColor: {self._yaml_string(category_color)}",
                f"tags: {json.dumps(tags, ensure_ascii=False)}",
                f"author: {self._yaml_string(author)}",
                f"authorRole: {self._yaml_string(author_role)}",
                f"readTime: {self._yaml_string(read_time)}",
                f"featured: {'true' if featured else 'false'}",
                f"difficulty: {self._yaml_string(difficulty)}",
                f"implementationTime: {self._yaml_string(implementation_time)}",
                f"excerpt: {self._yaml_string(excerpt)}",
                "---",
            ]
        )
        return f"{frontmatter_block}\n\n{body_content.rstrip()}\n"

    async def _get_existing_sha(self, client: httpx.AsyncClient, target_path: str) -> str | None:
        response = await client.get(self._contents_url(target_path))
        if response.status_code == 404:
            return None

        self._raise_for_status(response, operation="fetch website article")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub file lookup response was not a JSON object")

        sha = payload.get("sha")
        if not isinstance(sha, str) or not sha:
            raise RuntimeError("GitHub file lookup did not return a file sha")
        return sha

    def _contents_url(self, target_path: str) -> str:
        quoted_path = quote(target_path, safe="/")
        return f"{_GITHUB_API_BASE}/repos/{self._owner}/{self._repo}/contents/{quoted_path}"

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        }

    def _raise_for_status(self, response: httpx.Response, *, operation: str) -> None:
        if not response.is_error:
            return

        detail = "Unknown GitHub API error"
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                detail = message.strip()

        raise RuntimeError(
            f"GitHub API failed to {operation} ({response.status_code}): {detail}"
        )

    def _parse_source_markdown(self, source_markdown: str) -> tuple[str, dict[str, Any]]:
        if not source_markdown.strip():
            return "", {}

        try:
            post = frontmatter.loads(source_markdown)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("website_source_parse_failed", error=str(exc))
            return source_markdown, {}

        return post.content, dict(post.metadata)

    def _resolve_publish_date(self, publish_date: datetime | None, source_date: Any) -> date:
        if publish_date is not None:
            return publish_date.date()

        parsed_source_date = self._coerce_date(source_date)
        if parsed_source_date is not None:
            return parsed_source_date

        return datetime.now(tz=UTC).date()

    def _resolve_date_label(
        self,
        fallback: str | None,
        source_label: Any,
        publish_date: date,
    ) -> str:
        source = self._string_value(source_label)
        if source:
            return source

        if fallback:
            return fallback

        return publish_date.strftime("%B %d, %Y").replace(" 0", " ")

    def _resolve_read_time(
        self,
        source_read_time: Any,
        *,
        read_time_minutes: int | None,
        body: str,
    ) -> str:
        source = self._string_value(source_read_time)
        if source:
            return source

        if read_time_minutes is not None and read_time_minutes > 0:
            return f"{read_time_minutes} min read"

        words = len(body.split())
        minutes = max(1, round(words / 200))
        return f"{minutes} min read"

    def _resolve_excerpt(
        self,
        *,
        seo_description: str,
        source_excerpt: Any,
        fallback_excerpt: str,
        body: str,
        title: str,
    ) -> str:
        if seo_description.strip():
            return seo_description.strip()

        source = self._string_value(source_excerpt)
        if source:
            return source

        if fallback_excerpt.strip():
            return fallback_excerpt.strip()

        paragraphs = [
            paragraph.strip()
            for paragraph in body.split("\n\n")
            if paragraph.strip() and not paragraph.strip().startswith("#")
        ]
        if paragraphs:
            return paragraphs[0][:200]

        return title

    def _normalize_category(self, value: str) -> str:
        normalized = value.strip() or "General"
        return _CATEGORY_ALIASES.get(normalized.casefold(), normalized)

    def _category_color(self, category: str) -> str:
        resolved = _CATEGORY_ALIASES.get(category.casefold(), category)
        return CATEGORY_COLORS.get(resolved, CATEGORY_COLORS["General"])

    def _normalize_tags(self, source_tags: Any, fallback_tags: list[str]) -> list[str]:
        if isinstance(source_tags, list):
            raw_tags = [self._string_value(tag) for tag in source_tags]
        elif isinstance(source_tags, str):
            raw_tags = [segment.strip() for segment in source_tags.split(",")]
        else:
            raw_tags = [self._string_value(tag) for tag in fallback_tags]

        normalized: list[str] = []
        seen: set[str] = set()
        for tag in raw_tags:
            if not tag:
                continue
            if tag in seen:
                continue
            normalized.append(tag)
            seen.add(tag)
        return normalized

    def _coerce_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
            except ValueError:
                return None
        return None

    def _string_value(self, value: Any, default: str = "") -> str:
        if isinstance(value, str):
            return value.strip() or default
        if value is None:
            return default
        text = str(value).strip()
        return text or default

    def _yaml_string(self, value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _parse_repo(self, repo: str) -> tuple[str, str]:
        try:
            owner, name = repo.strip().split("/", maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                "github_website_repo must be formatted as '<owner>/<repo>'"
            ) from exc

        if not owner or not name:
            raise ValueError("github_website_repo must include both owner and repo")
        return owner, name
