"""GET /import-ready/{slug} — Serve blog articles as clean HTML for Medium import.

Medium's "Import a story" feature fetches raw HTML and requires:
- Server-rendered content (no JS)
- Standard article structure with <article>, <h1>, <p> tags
- Canonical URL in <link rel="canonical">
- og:title and og:description meta tags

Medium-specific rendering:
- Tables → styled HTML tables (Medium supports basic tables)
- Code blocks → <pre> with language label header
- Diagrams → formatted as code blocks with context
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


# Language display names for code block headers
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


def _render_table_to_html(table_lines: list[str]) -> str:
    """Convert markdown table lines to a styled HTML table."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 2:
        return ""

    # First row is header, second is separator (skip it)
    header = rows[0]
    data_rows = rows[2:]  # skip separator row

    html = '<figure><table style="width:100%;border-collapse:collapse;margin:1.5rem 0;">\n'
    html += "<thead><tr>"
    for cell in header:
        html += f'<th style="border:1px solid #ddd;padding:10px 12px;background:#f8f9fa;font-weight:600;text-align:left;">{_inline_md(cell)}</th>'
    html += "</tr></thead>\n<tbody>\n"

    for row in data_rows:
        html += "<tr>"
        for i, cell in enumerate(row):
            if i < len(header):
                html += f'<td style="border:1px solid #ddd;padding:8px 12px;">{_inline_md(cell)}</td>'
        html += "</tr>\n"

    html += "</tbody></table></figure>\n"
    return html


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to HTML."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _render_code_block(lang: str, code: str) -> str:
    """Render a code block with a language label header for Medium."""
    lang_display = _LANG_NAMES.get(lang.lower(), lang.upper() if lang else "Code")
    escaped_code = html_escape(code.rstrip())

    return (
        f'<figure style="margin:1.5rem 0;">'
        f'<figcaption style="background:#2d2d2d;color:#ccc;padding:6px 12px;'
        f'font-size:0.8rem;font-family:monospace;border-radius:4px 4px 0 0;'
        f'display:inline-block;">📄 {html_escape(lang_display)}</figcaption>'
        f'<pre style="background:#1e1e1e;color:#d4d4d4;padding:1rem;'
        f'overflow-x:auto;border-radius:0 4px 4px 4px;margin-top:0;'
        f'font-size:0.85rem;line-height:1.5;">'
        f"<code>{escaped_code}</code></pre></figure>\n"
    )


def _markdown_to_medium_html(markdown_body: str) -> str:
    """Custom Markdown → HTML renderer optimized for Medium import.

    Handles: headings, paragraphs, code blocks with language labels,
    tables, bold, italic, inline code, blockquotes, lists, links.
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

        # ── Table ──
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_render_table_to_html(table_lines))
            continue

        # ── Headings ──
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = _inline_md(heading_match.group(2))
            style = ""
            if level == 2:
                style = ' style="margin-top:2.5rem;padding-top:1rem;border-top:1px solid #eee;"'
            html_parts.append(f"<h{level}{style}>{text}</h{level}>\n")
            i += 1
            continue

        # ── Blockquote ──
        if line.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(lines[i].lstrip("> "))
                i += 1
            quote_text = _inline_md(" ".join(quote_lines))
            html_parts.append(
                f'<blockquote style="border-left:4px solid #00d4ff;margin:1.5rem 0;'
                f'padding:0.8rem 1.2rem;color:#555;font-style:italic;'
                f'background:#f8fffe;">{quote_text}</blockquote>\n'
            )
            continue

        # ── Unordered list ──
        if re.match(r"^[\-\*]\s", line):
            list_items = []
            while i < len(lines) and re.match(r"^[\-\*]\s", lines[i]):
                list_items.append(_inline_md(lines[i][2:].strip()))
                i += 1
            html_parts.append("<ul>\n")
            for item in list_items:
                html_parts.append(f"  <li>{item}</li>\n")
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
                html_parts.append(f"  <li>{item}</li>\n")
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

        # ── Paragraph (collect consecutive non-empty lines) ──
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("```") and not lines[i].startswith(">") and not re.match(r"^[\-\*]\s", lines[i]) and not re.match(r"^\d+\.\s", lines[i]) and not ("|" in lines[i] and i + 1 < len(lines) and i + 1 < len(lines) and "|" in lines[i]):
            para_lines.append(lines[i])
            i += 1

        if para_lines:
            para_text = _inline_md(" ".join(para_lines))
            # Convert markdown links [text](url) to HTML
            para_text = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2">\1</a>',
                para_text,
            )
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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_escape(article.title)}</title>
    <meta name="description" content="{html_escape(article.excerpt)}">
    <meta name="author" content="{html_escape(article.author)}">
    <meta name="keywords" content="{html_escape(', '.join(article.tags))}">
    <link rel="canonical" href="{canonical_url}">

    <!-- Open Graph (Medium uses these) -->
    <meta property="og:type" content="article">
    <meta property="og:title" content="{html_escape(article.title)}">
    <meta property="og:description" content="{html_escape(article.excerpt)}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="article:published_time" content="{article.date.isoformat()}">
    <meta property="article:author" content="{html_escape(article.author)}">
    <meta property="article:section" content="{html_escape(article.category)}">

    <style>
        body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 720px; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.8; color: #1a1a1a; }}
        h1 {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 2.4rem; line-height: 1.2; margin-bottom: 0.3rem; letter-spacing: -0.02em; }}
        h2 {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 1.6rem; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #eee; }}
        h3 {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 1.3rem; margin-top: 1.5rem; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid #eee; }}
        .meta .tag {{ display: inline-block; background: #f0f0f0; padding: 2px 8px; border-radius: 3px; font-size: 0.8rem; margin-right: 4px; }}
        pre {{ background: #1e1e1e; color: #d4d4d4; padding: 1rem; overflow-x: auto; border-radius: 4px; font-size: 0.85rem; line-height: 1.5; }}
        code {{ font-family: 'SF Mono', 'Fira Code', Menlo, monospace; font-size: 0.88em; }}
        p code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; color: #c7254e; }}
        blockquote {{ border-left: 4px solid #00d4ff; margin: 1.5rem 0; padding: 0.8rem 1.2rem; color: #555; font-style: italic; background: #f8fffe; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1.5rem 0; }}
        th {{ background: #f8f9fa; font-weight: 600; text-align: left; }}
        th, td {{ border: 1px solid #ddd; padding: 10px 12px; }}
        img {{ max-width: 100%; }}
        figure {{ margin: 1.5rem 0; }}
        figcaption {{ font-size: 0.8rem; color: #666; }}
        hr {{ border: none; border-top: 1px solid #eee; margin: 2rem 0; }}
        ul, ol {{ padding-left: 1.5rem; }}
        li {{ margin-bottom: 0.4rem; }}
    </style>
</head>
<body>
<article>
    <header>
        <h1>{html_escape(article.title)}</h1>
        <div class="meta">
            <p>{article.date_label} · {article.read_time or f'{article.estimated_read_minutes} min read'} · {html_escape(article.category)}</p>
            <p>By <strong>{html_escape(article.author)}</strong>{f', {html_escape(article.author_role)}' if article.author_role else ''}</p>
            <p>{''.join(f'<span class="tag">{html_escape(t)}</span>' for t in article.tags)}</p>
        </div>
    </header>
    <section>
        {body_html}
    </section>
    <footer style="margin-top:3rem;padding-top:1rem;border-top:1px solid #eee;font-size:0.85rem;color:#666;">
        <p>Originally published at <a href="{canonical_url}">{canonical_url}</a></p>
    </footer>
</article>
</body>
</html>"""

    return HTMLResponse(content=html, status_code=200)

