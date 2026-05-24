"""GET /import-ready/{slug} — Serve blog articles as clean HTML for Medium import.

Medium's importer only supports a restricted subset of HTML:
  ✓ <h1>–<h4>, <p>, <strong>, <em>, <a>, <blockquote>
  ✓ <pre> (code blocks — single gray block, no syntax highlighting)
  ✓ <ul>, <ol>, <li>
  ✓ <figure><img> (images only)
  ✓ <hr>
  ✗ <table> — stripped entirely, rendered as raw text
  ✗ <figcaption> on non-images — stripped
  ✗ Any inline styles — stripped
  ✗ <code> inside <pre> — causes double-block

Security:
  - POST /import-ready/{slug}/token — Authenticated users generate a time-limited access token
  - GET  /import-ready/{slug}?token=XXX — Public access with valid token (2 min TTL)
  - GET  /import-ready/{slug} without token — 401 Unauthorized

Flags (query parameters):
  - tables=image  — Render tables as embedded images (SVG) for Medium compatibility
  - code=plain    — Strip language comments from code blocks (plain text only)
"""

import hashlib
import re
import secrets
import time
from html import escape as html_escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings
from app.security.auth import require_api_key
from app.utils.logging import get_logger
from app.utils.markdown_parser import MarkdownParser

router = APIRouter()
_parser = MarkdownParser()
logger = get_logger(__name__)

# Time-limited token store: {token_hash: (slug, expires_at)}
_TOKEN_STORE: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SECONDS = 120  # 2 minutes


# ── Token management ──────────────────────────────────────────────────────────


def _generate_import_token(slug: str) -> str:
    """Generate a cryptographically secure token valid for 2 minutes."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _TOKEN_STORE[token_hash] = (slug, time.time() + _TOKEN_TTL_SECONDS)
    _cleanup_expired_tokens()
    return token


def _validate_import_token(slug: str, token: str | None) -> bool:
    """Validate token and check it matches the requested slug."""
    if not token:
        return False
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    entry = _TOKEN_STORE.get(token_hash)
    if not entry:
        return False
    stored_slug, expires_at = entry
    if time.time() > expires_at:
        del _TOKEN_STORE[token_hash]
        return False
    if stored_slug != slug:
        return False
    return True


def _cleanup_expired_tokens() -> None:
    """Remove expired tokens from store."""
    now = time.time()
    expired = [k for k, (_, exp) in _TOKEN_STORE.items() if now > exp]
    for k in expired:
        del _TOKEN_STORE[k]


# ── Token endpoint (authenticated) ───────────────────────────────────────────

_basic_security = HTTPBasic(auto_error=False)


def _require_any_auth(
    request: Request,
    basic_creds: HTTPBasicCredentials | None = Depends(_basic_security),
) -> str:
    """Accept either Bearer token (API key/JWT) OR HTTP Basic Auth (docs credentials).

    This allows generating tokens from Swagger UI using the same Basic Auth
    credentials used to access /docs, without needing a separate Bearer token.
    """
    settings = get_settings()

    # Try Bearer token from Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]
        if secrets.compare_digest(token, settings.actions_api_key):
            return "github-actions"
        from app.security.jwt import decode_token

        try:
            payload = decode_token(token)
            return payload["sub"]
        except ValueError:
            pass

    # Try HTTP Basic Auth (same credentials as /docs)
    if basic_creds and basic_creds.username and basic_creds.password:
        valid_user = secrets.compare_digest(
            basic_creds.username.encode(), settings.docs_username.encode()
        )
        valid_pass = secrets.compare_digest(
            basic_creds.password.encode(), settings.docs_password.encode()
        )
        if valid_user and valid_pass:
            return f"docs-user:{basic_creds.username}"

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Use Bearer token OR Basic Auth (same as /docs).",
        headers={"WWW-Authenticate": 'Basic realm="import-token"'},
    )


@router.post("/{slug}/token")
async def create_import_token(
    slug: str,
    _subject: str = Depends(_require_any_auth),
) -> dict:
    """Generate a time-limited URL for Medium's import tool.

    **Auth:** Accepts Bearer token (API key) OR HTTP Basic Auth (same credentials as /docs).

    Returns a token valid for 2 minutes. Use it as:
      GET /import-ready/{slug}?token=<TOKEN>
    """
    settings = get_settings()
    content_path = Path(settings.content_source_path)
    md_file = content_path / f"{slug}.md"
    if not md_file.exists():
        raise HTTPException(status_code=404, detail=f"Article '{slug}' not found")

    token = _generate_import_token(slug)
    base_url = settings.approval_base_url.rstrip("/")
    import_url = f"{base_url}/import-ready/{slug}?token={token}"

    logger.info("import_token_generated", slug=slug, ttl_seconds=_TOKEN_TTL_SECONDS)
    return {
        "url": import_url,
        "token": token,
        "expires_in_seconds": _TOKEN_TTL_SECONDS,
        "note": "Use this URL in Medium's 'Import a story' tool within 2 minutes.",
    }


# ── Rendering helpers ─────────────────────────────────────────────────────────


_LANG_NAMES: dict[str, str] = {
    "python": "Python",
    "py": "Python",
    "terraform": "Terraform (HCL)",
    "hcl": "Terraform (HCL)",
    "sql": "SQL",
    "yaml": "YAML",
    "yml": "YAML",
    "json": "JSON",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "bash": "Bash",
    "sh": "Shell",
    "go": "Go",
    "rust": "Rust",
    "java": "Java",
    "dockerfile": "Dockerfile",
    "toml": "TOML",
    "xml": "XML",
    "html": "HTML",
    "css": "CSS",
    "graphql": "GraphQL",
    "protobuf": "Protocol Buffers",
    "proto": "Protocol Buffers",
}

_LANG_COMMENT: dict[str, str] = {
    "python": "#",
    "py": "#",
    "terraform": "#",
    "hcl": "#",
    "sql": "--",
    "yaml": "#",
    "yml": "#",
    "bash": "#",
    "sh": "#",
    "ruby": "#",
    "toml": "#",
    "dockerfile": "#",
    "javascript": "//",
    "js": "//",
    "typescript": "//",
    "ts": "//",
    "go": "//",
    "rust": "//",
    "java": "//",
    "c": "//",
    "cpp": "//",
    "json": "//",
    "graphql": "#",
    "proto": "//",
    "protobuf": "//",
    "css": "/*",
    "html": "<!--",
    "xml": "<!--",
}


def _render_table_as_image(table_lines: list[str]) -> str:
    """Render markdown table as an inline SVG image for Medium import."""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 3:
        return ""

    header = rows[0]
    data_rows = rows[2:]  # skip separator
    num_cols = len(header)

    # Calculate column widths
    col_width = 160
    row_height = 32
    padding = 12
    total_width = num_cols * col_width + padding * 2
    total_height = (len(data_rows) + 1) * row_height + padding * 2

    svg_rows = []
    # Header row (bold, darker background)
    y = padding + row_height
    svg_rows.append(
        f'<rect x="{padding}" y="{padding}" width="{total_width - padding * 2}" '
        f'height="{row_height}" fill="#e8e8e8" rx="4"/>'
    )
    for ci, cell in enumerate(header):
        x = padding + ci * col_width + 8
        svg_rows.append(
            f'<text x="{x}" y="{y - 10}" font-family="monospace" '
            f'font-size="12" font-weight="bold" fill="#1a1a1a">'
            f"{html_escape(cell[:20])}</text>"
        )

    # Data rows
    for ri, row in enumerate(data_rows):
        ry = padding + (ri + 1) * row_height
        y = ry + row_height - 10
        bg = "#f9f9f9" if ri % 2 == 0 else "#ffffff"
        svg_rows.append(
            f'<rect x="{padding}" y="{ry}" width="{total_width - padding * 2}" '
            f'height="{row_height}" fill="{bg}"/>'
        )
        for ci, cell in enumerate(row[:num_cols]):
            x = padding + ci * col_width + 8
            svg_rows.append(
                f'<text x="{x}" y="{y}" font-family="monospace" '
                f'font-size="11" fill="#333">{html_escape(cell[:22])}</text>'
            )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
        f'height="{total_height}" viewBox="0 0 {total_width} {total_height}">'
        f'<rect width="100%" height="100%" fill="#fff" rx="6" '
        f'stroke="#ddd" stroke-width="1"/>'
        + "\n".join(svg_rows)
        + "</svg>"
    )

    # Encode as data URI for inline embedding
    import base64

    svg_b64 = base64.b64encode(svg.encode()).decode()
    return (
        f'<figure><img src="data:image/svg+xml;base64,{svg_b64}" '
        f'alt="Table" width="{total_width}"/></figure>\n'
    )


def _render_table_as_text(table_lines: list[str]) -> str:
    """Convert markdown table to Medium-compatible format (structured list)."""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 3:
        return ""

    header = rows[0]
    data_rows = rows[2:]  # skip separator

    html = ""
    for row in data_rows:
        parts = []
        for i, cell in enumerate(row):
            if i < len(header) and cell:
                parts.append(f"<strong>{_inline_md(header[i])}</strong>: {_inline_md(cell)}")
        html += f"<p>{' · '.join(parts)}</p>\n"

    return html


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to HTML."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_code_block(lang: str, code: str, *, plain: bool = False) -> str:
    """Render a code block for Medium import.

    Uses one <pre> per line to prevent Medium from collapsing multi-line blocks
    into a single line. Medium treats each <pre> as a separate paragraph within
    the same code block when they appear consecutively.

    Args:
        lang: Programming language identifier
        code: The code content
        plain: If True, omit language comment header
    """
    code_lines = code.rstrip().split("\n")

    # Optional language header as first line
    lang_header_line = ""
    if not plain and lang:
        lang_display = _LANG_NAMES.get(lang.lower(), lang.upper() if lang else "")
        if lang_display:
            comment_char = _LANG_COMMENT.get(lang.lower(), "#")
            if comment_char == "<!--":
                lang_header_line = f"&lt;!-- {lang_display} --&gt;"
            elif comment_char == "/*":
                lang_header_line = f"/* {lang_display} */"
            else:
                lang_header_line = f"{html_escape(comment_char)} {lang_display}"

    # Build all lines into a single <pre> with explicit newline chars
    all_lines = []
    if lang_header_line:
        all_lines.append(lang_header_line)
    for line in code_lines:
        all_lines.append(html_escape(line) if line else "")

    # Use a single <pre> with \n preserved — Medium's import tool respects
    # newlines within <pre> blocks. If that fails, the fallback would be
    # multiple consecutive <pre> elements.
    return f"<pre>\n{chr(10).join(all_lines)}\n</pre>\n"


def _markdown_to_medium_html(
    markdown_body: str,
    *,
    tables_as_image: bool = False,
    code_plain: bool = False,
) -> str:
    """Custom Markdown → HTML renderer for Medium's restricted import.

    Only uses elements Medium actually supports:
    h1-h4, p, strong, em, code, a, blockquote, pre, ul, ol, li, hr, figure>img
    """
    lines = markdown_body.split("\n")
    html_parts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ──
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            html_parts.append(
                _render_code_block(lang, "\n".join(code_lines), plain=code_plain)
            )
            continue

        # ── Table (detect by separator row) ──
        if "|" in line and i + 1 < len(lines) and re.match(
            r"^\|[\s\-:|]+\|$", lines[i + 1].strip()
        ):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            if tables_as_image:
                html_parts.append(_render_table_as_image(table_lines))
            else:
                html_parts.append(_render_table_as_text(table_lines))
            continue

        # ── Headings ──
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)  # Medium supports h1-h4
            text = _inline_md(heading_match.group(2))
            html_parts.append(f"<h{level}>{text}</h{level}>\n")
            i += 1
            continue

        # ── Blockquote ──
        if line.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(lines[i].lstrip("> "))
                i += 1
            quote_text = _inline_md(" ".join(quote_lines))
            html_parts.append(f"<blockquote>{quote_text}</blockquote>\n")
            continue

        # ── Unordered list ──
        if re.match(r"^[\-\*]\s", line):
            list_items = []
            while i < len(lines) and re.match(r"^[\-\*]\s", lines[i]):
                list_items.append(_inline_md(lines[i][2:].strip()))
                i += 1
            html_parts.append("<ul>\n")
            for item in list_items:
                html_parts.append(f"<li>{item}</li>\n")
            html_parts.append("</ul>\n")
            continue

        # ── Ordered list ──
        if re.match(r"^\d+\.\s", line):
            list_items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i]):
                list_items.append(_inline_md(re.sub(r"^\d+\.\s", "", lines[i]).strip()))
                i += 1
            html_parts.append("<ol>\n")
            for item in list_items:
                html_parts.append(f"<li>{item}</li>\n")
            html_parts.append("</ol>\n")
            continue

        # ── Horizontal rule ──
        if re.match(r"^---+$", line.strip()):
            html_parts.append("<hr>\n")
            i += 1
            continue

        # ── Empty line ──
        if not line.strip():
            i += 1
            continue

        # ── Paragraph ──
        para_lines = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].startswith("#")
            and not lines[i].startswith("```")
            and not lines[i].startswith(">")
            and not re.match(r"^[\-\*]\s", lines[i])
            and not re.match(r"^\d+\.\s", lines[i])
            and not re.match(r"^---+$", lines[i].strip())
            and not (
                "|" in lines[i]
                and i + 1 < len(lines)
                and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip())
            )
        ):
            para_lines.append(lines[i])
            i += 1

        if para_lines:
            para_text = _inline_md(" ".join(para_lines))
            html_parts.append(f"<p>{para_text}</p>\n")
        else:
            i += 1

    return "".join(html_parts)


# ── Main endpoint (token-protected) ──────────────────────────────────────────


@router.get("/{slug}", response_class=HTMLResponse)
@router.head("/{slug}", response_class=HTMLResponse)
async def import_ready_article(
    slug: str,
    token: str | None = Query(default=None, description="Time-limited access token"),
    tables: str | None = Query(
        default=None, description="Table rendering: 'image' for SVG, default is structured text"
    ),
    code: str | None = Query(
        default=None, description="Code rendering: 'plain' to disable language labels"
    ),
) -> HTMLResponse:
    """Render a blog article as clean static HTML for Medium's import tool.

    Requires a valid time-limited token (generated via POST /{slug}/token).
    Token expires after 2 minutes.
    """
    # Validate token
    if not _validate_import_token(slug, token):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized — token missing, expired, or invalid. "
            "Generate one via POST /import-ready/{slug}/token",
        )

    settings = get_settings()
    content_path = Path(settings.content_source_path)
    md_file = content_path / f"{slug}.md"
    if not md_file.exists():
        raise HTTPException(status_code=404, detail=f"Article '{slug}' not found")

    article = _parser.parse_file(md_file)

    # Render with flags
    body_html = _markdown_to_medium_html(
        article.content_body,
        tables_as_image=(tables == "image"),
        code_plain=(code == "plain"),
    )
    canonical_url = f"{settings.medium_canonical_base_url}/{article.slug}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{html_escape(article.title)}</title>
    <meta name="description" content="{html_escape(article.excerpt)}">
    <meta name="author" content="{html_escape(article.author)}">
    <link rel="canonical" href="{canonical_url}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{html_escape(article.title)}">
    <meta property="og:description" content="{html_escape(article.excerpt)}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="article:published_time" content="{article.date.isoformat()}">
</head>
<body>
<article>
<h1>{html_escape(article.title)}</h1>
{body_html}
<p><em>Originally published at <a href="{canonical_url}">bytemind.fr</a></em></p>
</article>
</body>
</html>"""

    logger.info("import_ready_served", slug=slug, tables=tables, code=code)
    return HTMLResponse(content=html, status_code=200)

