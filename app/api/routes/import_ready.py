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

Strategy:
- Tables → formatted as structured lists (bold header: value)
- Code blocks → <pre> with language comment as first line
- Everything else → simple semantic HTML only
"""

import re
from html import escape as html_escape
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.utils.markdown_parser import MarkdownParser

router = APIRouter()
_parser = MarkdownParser()


# Comment syntax per language for code block headers
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


def _render_table_for_medium(table_lines: list[str]) -> str:
    """Convert markdown table to Medium-compatible format (structured list).

    Medium does NOT support <table> — it strips the tags and renders
    raw pipe text. Instead, we render each row as a structured block.
    """
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 3:
        return ""

    header = rows[0]
    data_rows = rows[2:]  # skip separator

    html = ""
    for row in data_rows:
        # Each row becomes a paragraph with bold field names
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
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_code_block(lang: str, code: str) -> str:
    """Render a code block for Medium — just <pre> with language as a comment."""
    lang_display = _LANG_NAMES.get(lang.lower(), lang.upper() if lang else "")
    comment_char = _LANG_COMMENT.get(lang.lower(), "#")
    escaped_code = html_escape(code.rstrip())

    # Add language label as a comment at the top of the code
    lang_header = ""
    if lang_display:
        if comment_char == "<!--":
            lang_header = f"&lt;!-- {lang_display} --&gt;\n"
        elif comment_char == "/*":
            lang_header = f"/* {lang_display} */\n"
        else:
            lang_header = f"{html_escape(comment_char)} {lang_display}\n"

    return f"<pre>{lang_header}{escaped_code}</pre>\n"


def _markdown_to_medium_html(markdown_body: str) -> str:
    """Custom Markdown → HTML renderer for Medium's restricted import.

    Only uses elements Medium actually supports:
    h1-h4, p, strong, em, code, a, blockquote, pre, ul, ol, li, hr
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
            html_parts.append(_render_code_block(lang, "\n".join(code_lines)))
            continue

        # ── Table (detect by separator row) ──
        if "|" in line and i + 1 < len(lines) and re.match(
            r"^\|[\s\-:|]+\|$", lines[i + 1].strip()
        ):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_render_table_for_medium(table_lines))
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


@router.get("/{slug}", response_class=HTMLResponse)
@router.head("/{slug}", response_class=HTMLResponse)
async def import_ready_article(slug: str) -> HTMLResponse:
    """Render a blog article as clean static HTML for Medium/external importers."""
    settings = get_settings()
    content_path = Path(settings.content_source_path)

    md_file = content_path / f"{slug}.md"
    if not md_file.exists():
        raise HTTPException(status_code=404, detail=f"Article '{slug}' not found")

    article = _parser.parse_file(md_file)
    body_html = _markdown_to_medium_html(article.content_body)
    canonical_url = f"{settings.medium_canonical_base_url}/{article.slug}"

    # Medium only respects: title, canonical, og: tags, and basic semantic HTML.
    # All inline styles and custom elements are stripped on import.
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

    return HTMLResponse(content=html, status_code=200)

