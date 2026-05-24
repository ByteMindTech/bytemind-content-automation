"""
Full HTML renderer — converts Markdown to rich HTML for Medium's editor.

Unlike the import-ready renderer (which avoids <table> because Medium's
import tool strips them), this renderer produces FULL HTML because when
injected via Playwright's execCommand('insertHTML'), Medium's editor
accepts and renders tables, code blocks, and all standard elements.

Used by: PlaywrightMediumPublisher
"""

from __future__ import annotations

import re
from html import escape as html_escape


def markdown_to_full_html(markdown_body: str) -> str:
    """Convert Markdown to full-featured HTML for Medium editor injection.

    Supports: headings, paragraphs, tables, code blocks, blockquotes,
    lists, bold, italic, inline code, links, horizontal rules.
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
        if "|" in line and i + 1 < len(lines) and re.match(
            r"^\|[\s\-:|]+\|$", lines[i + 1].strip()
        ):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_render_table(table_lines))
            continue

        # ── Headings ──
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
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


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, code, links) to HTML."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", lambda m: f"<code>{html_escape(m.group(1))}</code>", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_code_block(lang: str, code: str) -> str:
    """Render code block as <pre> — Medium editor handles formatting."""
    escaped = html_escape(code.rstrip())
    if lang:
        return f'<pre data-lang="{html_escape(lang)}"><code>{escaped}</code></pre>\n'
    return f"<pre><code>{escaped}</code></pre>\n"


def _render_table(table_lines: list[str]) -> str:
    """Render markdown table as full HTML <table> element."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 3:
        return ""

    header = rows[0]
    data_rows = rows[2:]  # skip separator

    html = "<table>\n<thead><tr>"
    for cell in header:
        html += f"<th>{_inline_md(cell)}</th>"
    html += "</tr></thead>\n<tbody>\n"

    for row in data_rows:
        html += "<tr>"
        for i, cell in enumerate(row):
            if i < len(header):
                html += f"<td>{_inline_md(cell)}</td>"
        html += "</tr>\n"

    html += "</tbody></table>\n"
    return html
