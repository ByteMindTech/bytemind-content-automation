"""
Medium GraphQL Publisher — Direct API publishing using Medium's internal GraphQL endpoint.

This module bypasses Medium's deprecated public API by using the internal GraphQL
mutations that the Medium editor itself uses, authenticated via session cookies.

Capabilities:
  - Create drafts with full content (paragraphs, code blocks, headings, lists, tables)
  - Set tags (up to 5)
  - Publish posts (draft or public)
  - Bold, italic, code, and link formatting via markups

Authentication:
  - Requires Medium session cookies (uid + sid)
  - XSRF token auto-fetched per request

Medium Paragraph Types:
  1  = paragraph (p)
  3  = H3 (title - first paragraph)
  4  = H4 (subheading)
  6  = blockquote
  8  = code block (pre)
  9  = bulleted list item
  10 = ordered list item
  11 = image/embed
  13 = H2 (section heading)

Medium Markup Types:
  1  = bold
  2  = italic
  3  = link (requires href, title, rel, anchorType)
  10 = inline code
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()
COOKIES_PATH = Path(__file__).resolve().parent.parent.parent / "content" / ".medium-cookies.json"
GRAPHQL_URL = "https://medium.com/_/graphql"
DELTA_BATCH_SIZE = 50


class MediumGraphQLPublisher:
    """Publish articles to Medium via internal GraphQL API."""

    def __init__(self, cookies_path: Path | str | None = None) -> None:
        self._cookies_path = Path(cookies_path) if cookies_path else COOKIES_PATH
        self._dry_run = _settings.medium_dry_run

    def _load_cookies(self) -> dict[str, str]:
        """Load session cookies from file."""
        if not self._cookies_path.exists():
            raise FileNotFoundError(
                f"Medium cookies not found at {self._cookies_path}. "
                "Save your uid and sid cookies first."
            )
        data = json.loads(self._cookies_path.read_text())
        # Support both list-of-dicts (Playwright format) and simple dict
        if isinstance(data, list):
            return {c["name"]: c["value"] for c in data}
        return data

    def _get_session(self) -> tuple[dict[str, str], dict[str, str]]:
        """Get authenticated session with XSRF token."""
        cookies = self._load_cookies()
        # Fetch XSRF token
        r = requests.get("https://medium.com/", cookies=cookies, timeout=15)
        xsrf = r.cookies.get("xsrf", "")
        cookies["xsrf"] = xsrf
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-XSRF-Token": xsrf,
            "X-Obvious-CK": "true",
        }
        return cookies, headers

    def publish(
        self,
        *,
        title: str,
        markdown_body: str,
        tags: list[str] | None = None,
        canonical_url: str | None = None,
        publish_status: str = "draft",
    ) -> dict:
        """
        Publish a markdown article to Medium.

        Args:
            title: Article title
            markdown_body: Markdown content (without frontmatter)
            tags: Up to 5 topic tags
            canonical_url: Original article URL (for SEO)
            publish_status: "draft" or "public"

        Returns:
            Dict with: post_id, url, status, paragraphs_count
        """
        if self._dry_run:
            logger.info("medium_graphql_dry_run", title=title, tags=tags)
            return {
                "post_id": "dry-run",
                "url": f"https://medium.com/@melhosni/draft-{_slugify(title)}",
                "status": "dry_run",
                "dry_run": True,
            }

        cookies, headers = self._get_session()

        # 1. Create empty draft
        post_id = self._create_post(cookies, headers)
        logger.info("medium_post_created", post_id=post_id)

        # 2. Convert markdown to deltas and push content
        deltas = markdown_to_deltas(title, markdown_body)
        self._push_deltas(post_id, deltas, cookies, headers)
        logger.info("medium_content_saved", post_id=post_id, paragraphs=len(deltas))

        # 3. Set tags
        if tags:
            self._set_tags(post_id, tags[:5], cookies, headers)

        # 4. Publish if requested
        if publish_status == "public":
            self._publish_post(post_id, cookies, headers)

        url = f"https://medium.com/@melhosni/{post_id}"
        logger.info(
            "medium_article_published",
            post_id=post_id,
            url=url,
            status=publish_status,
        )

        return {
            "post_id": post_id,
            "url": url,
            "edit_url": f"https://medium.com/p/{post_id}/edit",
            "status": publish_status,
            "paragraphs_count": len(deltas),
            "dry_run": False,
        }

    def _create_post(self, cookies: dict, headers: dict) -> str:
        """Create an empty draft and return its ID."""
        query = (
            "mutation CreatePost($input: CreatePostInput!) "
            "{ createPost(input: $input) { id mediumUrl } }"
        )
        r = requests.post(
            GRAPHQL_URL,
            json={"operationName": "CreatePost", "variables": {"input": {}}, "query": query},
            cookies=cookies,
            headers=headers,
            timeout=15,
        )
        data = self._parse_response(r)
        return data["data"]["createPost"]["id"]

    def _push_deltas(
        self, post_id: str, deltas: list[dict], cookies: dict, headers: dict
    ) -> None:
        """Push content deltas to a post in batches."""
        query = (
            "mutation UpdatePost($responseId: ID!, $latestRev: Int!, $deltas: [Delta!]!) "
            "{ updatePostResponse(responseId: $responseId, latestRev: $latestRev, deltas: $deltas) "
            "{ __typename } }"
        )
        rev = -1
        for batch_start in range(0, len(deltas), DELTA_BATCH_SIZE):
            batch = deltas[batch_start : batch_start + DELTA_BATCH_SIZE]
            r = requests.post(
                GRAPHQL_URL,
                json={
                    "operationName": "UpdatePost",
                    "query": query,
                    "variables": {
                        "responseId": post_id,
                        "latestRev": rev,
                        "deltas": batch,
                    },
                },
                cookies=cookies,
                headers=headers,
                timeout=30,
            )
            self._parse_response(r, allow_rate_limit=True)
            rev += len(batch)
            # Small delay between batches to avoid rate limits
            if batch_start + DELTA_BATCH_SIZE < len(deltas):
                time.sleep(1)

    def _set_tags(
        self, post_id: str, tags: list[str], cookies: dict, headers: dict
    ) -> None:
        """Set topic tags on a post."""
        query = (
            "mutation SetTags($targetPostId: ID!, $tagNames: [String!]!) "
            "{ setPostTags(targetPostId: $targetPostId, tagNames: $tagNames) "
            "{ __typename } }"
        )
        r = requests.post(
            GRAPHQL_URL,
            json={
                "operationName": "SetTags",
                "query": query,
                "variables": {"targetPostId": post_id, "tagNames": tags},
            },
            cookies=cookies,
            headers=headers,
            timeout=15,
        )
        self._parse_response(r, allow_rate_limit=True)

    def _publish_post(self, post_id: str, cookies: dict, headers: dict) -> None:
        """Publish a draft post."""
        query = (
            "mutation PublishPost($postId: ID!) "
            "{ publishPost(postId: $postId) { __typename } }"
        )
        r = requests.post(
            GRAPHQL_URL,
            json={
                "operationName": "PublishPost",
                "query": query,
                "variables": {"postId": post_id},
            },
            cookies=cookies,
            headers=headers,
            timeout=15,
        )
        self._parse_response(r)

    def _parse_response(self, r: requests.Response, allow_rate_limit: bool = False) -> dict:
        """Parse Medium's JSON response (strips XSSI prefix)."""
        text = r.text
        if text.startswith("])}"):
            text = text[text.index("{"):]
        if not text:
            if r.status_code == 200:
                return {}
            raise RuntimeError(f"Medium API error: HTTP {r.status_code}")
        data = json.loads(text)
        errors = data.get("errors", [])
        if errors:
            msg = errors[0].get("message", "Unknown error")
            if allow_rate_limit and "rate limit" in msg.lower():
                logger.warning("medium_rate_limit_warning", message=msg)
                return data
            if "rate limit" in msg.lower():
                raise RuntimeError(f"Medium rate limit: {msg}")
            if "INTERNAL_SERVER_ERROR" in str(errors[0].get("extensions", {})):
                raise RuntimeError(f"Medium server error: {msg}")
            raise RuntimeError(f"Medium GraphQL error: {msg}")
        return data

    def delete_post(self, post_id: str) -> None:
        """Delete a post (cleanup helper)."""
        cookies, headers = self._get_session()
        query = (
            "mutation DeletePost($postId: ID!) "
            "{ deletePost(postId: $postId) { __typename } }"
        )
        requests.post(
            GRAPHQL_URL,
            json={
                "operationName": "DeletePost",
                "query": query,
                "variables": {"postId": post_id},
            },
            cookies=cookies,
            headers=headers,
            timeout=15,
        )


# --- Markdown to Deltas Converter ---


def markdown_to_deltas(title: str, body: str) -> list[dict]:
    """Convert markdown content to Medium's delta format."""
    deltas: list[dict] = []
    idx = 0

    # Title (H3 in Medium's model)
    deltas.append(_delta(idx, 3, title, []))
    idx += 1

    lines = body.split("\n")
    i = 0
    in_code = False
    code_lines: list[str] = []
    code_lang = ""

    while i < len(lines):
        line = lines[i]

        # Code fences
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                code_lines = []
            else:
                in_code = False
                code_text = "\n".join(code_lines)
                if code_lang:
                    comment = _lang_comment(code_lang)
                    code_text = f"{comment} {code_lang}\n{code_text}"
                deltas.append(_delta(idx, 8, code_text, []))
                idx += 1
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Blank lines
        if not line.strip():
            i += 1
            continue

        # H2
        if line.startswith("## "):
            text = _strip_md_formatting(line[3:])
            deltas.append(_delta(idx, 13, text, []))
            idx += 1
            i += 1
            continue

        # H3
        if line.startswith("### "):
            text = _strip_md_formatting(line[4:])
            deltas.append(_delta(idx, 4, text, []))
            idx += 1
            i += 1
            continue

        # H4
        if line.startswith("#### "):
            text = _strip_md_formatting(line[5:])
            deltas.append(_delta(idx, 4, text, []))
            idx += 1
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            text, markups = _parse_inline(line[2:].strip())
            deltas.append(_delta(idx, 6, text, markups))
            idx += 1
            i += 1
            continue

        # Bullet list
        if line.startswith("- ") or line.startswith("* "):
            text, markups = _parse_inline(line[2:].strip())
            deltas.append(_delta(idx, 9, text, markups))
            idx += 1
            i += 1
            continue

        # Ordered list
        if re.match(r"^\d+\. ", line):
            text, markups = _parse_inline(re.sub(r"^\d+\. ", "", line).strip())
            deltas.append(_delta(idx, 10, text, markups))
            idx += 1
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", line.strip()):
            deltas.append(_delta(idx, 1, "—" * 3, []))
            idx += 1
            i += 1
            continue

        # Table → structured paragraphs
        if line.startswith("|"):
            table_rows: list[list[str]] = []
            while i < len(lines) and lines[i].startswith("|"):
                row = lines[i]
                if not re.match(r"^\|[\s\-:|]+\|$", row):
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    table_rows.append(cells)
                i += 1
            if len(table_rows) > 1:
                headers_row = table_rows[0]
                for data_row in table_rows[1:]:
                    text, markups = _table_row_to_paragraph(headers_row, data_row)
                    deltas.append(_delta(idx, 1, text, markups))
                    idx += 1
            continue

        # Regular paragraph
        text, markups = _parse_inline(line)
        deltas.append(_delta(idx, 1, text, markups))
        idx += 1
        i += 1

    return deltas


def _delta(index: int, para_type: int, text: str, markups: list[dict]) -> dict:
    """Create a single delta insert operation."""
    return {
        "type": 1,  # 1 = insert
        "index": index,
        "paragraph": {"type": para_type, "text": text, "markups": markups},
    }


def _parse_inline(text: str) -> tuple[str, list[dict]]:
    """Parse inline markdown formatting to plain text + markups."""
    markups: list[dict] = []
    result = ""
    i = 0

    while i < len(text):
        # Bold **text**
        if text[i : i + 2] == "**":
            end = text.find("**", i + 2)
            if end != -1:
                content = text[i + 2 : end]
                # Recursively parse content for nested formatting
                inner_text, inner_markups = _parse_inline(content)
                start_pos = len(result)
                markups.append({"type": 1, "start": start_pos, "end": start_pos + len(inner_text)})
                for m in inner_markups:
                    markups.append(
                        {**m, "start": m["start"] + start_pos, "end": m["end"] + start_pos}
                    )
                result += inner_text
                i = end + 2
                continue

        # Italic *text* (not bold)
        if (
            text[i] == "*"
            and (i == 0 or text[i - 1] != "*")
            and (i + 1 < len(text) and text[i + 1] != "*")
        ):
            end = text.find("*", i + 1)
            if end != -1 and (end + 1 >= len(text) or text[end + 1] != "*"):
                content = text[i + 1 : end]
                markups.append({"type": 2, "start": len(result), "end": len(result) + len(content)})
                result += content
                i = end + 1
                continue

        # Inline code `text`
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                content = text[i + 1 : end]
                markups.append(
                    {"type": 10, "start": len(result), "end": len(result) + len(content)}
                )
                result += content
                i = end + 1
                continue

        # Links [text](url)
        if text[i] == "[":
            bracket_end = text.find("]", i)
            if (
                bracket_end != -1
                and bracket_end + 1 < len(text)
                and text[bracket_end + 1] == "("
            ):
                paren_end = text.find(")", bracket_end + 2)
                if paren_end != -1:
                    link_text = text[i + 1 : bracket_end]
                    link_url = text[bracket_end + 2 : paren_end]
                    markups.append(
                        {
                            "type": 3,
                            "start": len(result),
                            "end": len(result) + len(link_text),
                            "href": link_url,
                            "title": "",
                            "rel": "",
                            "anchorType": 0,
                        }
                    )
                    result += link_text
                    i = paren_end + 1
                    continue

        result += text[i]
        i += 1

    return result, markups


def _table_row_to_paragraph(headers: list[str], row: list[str]) -> tuple[str, list[dict]]:
    """Convert a table data row to a formatted paragraph with bold headers."""
    parts: list[str] = []
    markups: list[dict] = []
    pos = 0

    for j, (h, v) in enumerate(zip(headers, row)):
        entry = f"{h}: {v}"
        markups.append({"type": 1, "start": pos, "end": pos + len(h)})
        if j < len(headers) - 1:
            entry += " · "
        parts.append(entry)
        pos += len(entry)

    return "".join(parts), markups


def _strip_md_formatting(text: str) -> str:
    """Remove markdown bold/italic from header text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text.strip()


def _lang_comment(lang: str) -> str:
    """Return the comment prefix for a language."""
    sql_style = {"sql", "haskell", "lua"}
    hash_style = {"python", "ruby", "bash", "sh", "yaml", "yml", "toml", "r", "perl"}
    if lang.lower() in sql_style:
        return "--"
    if lang.lower() in hash_style:
        return "#"
    return "//"


def _slugify(text: str) -> str:
    """Create a URL-friendly slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60]
