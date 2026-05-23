"""GET /import-ready/{slug} — Serve blog articles as clean HTML for Medium import.

Medium's "Import a story" feature fetches raw HTML and requires:
- Server-rendered content (no JS)
- Standard article structure with <article>, <h1>, <p> tags
- Canonical URL in <link rel="canonical">
- og:title and og:description meta tags
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.utils.markdown_parser import MarkdownParser

router = APIRouter()
_parser = MarkdownParser()


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

    # Convert markdown body to HTML
    import mistune

    md_renderer = mistune.create_markdown(escape=False)
    body_html = md_renderer(article.content_body)

    canonical_url = f"{settings.medium_canonical_base_url}/{article.slug}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.title}</title>
    <meta name="description" content="{article.excerpt}">
    <meta name="author" content="{article.author}">
    <meta name="keywords" content="{', '.join(article.tags)}">
    <link rel="canonical" href="{canonical_url}">

    <!-- Open Graph (Medium uses these) -->
    <meta property="og:type" content="article">
    <meta property="og:title" content="{article.title}">
    <meta property="og:description" content="{article.excerpt}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="article:published_time" content="{article.date.isoformat()}">
    <meta property="article:author" content="{article.author}">
    <meta property="article:section" content="{article.category}">

    <style>
        body {{ font-family: Georgia, serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #1a1a1a; }}
        h1 {{ font-size: 2.2rem; line-height: 1.2; margin-bottom: 0.5rem; }}
        h2 {{ font-size: 1.6rem; margin-top: 2rem; }}
        h3 {{ font-size: 1.3rem; margin-top: 1.5rem; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; border-bottom: 1px solid #eee; padding-bottom: 1rem; }}
        pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto; border-radius: 4px; }}
        code {{ font-family: 'SF Mono', Menlo, monospace; font-size: 0.9em; }}
        blockquote {{ border-left: 3px solid #00d4ff; margin: 1.5rem 0; padding: 0.5rem 1rem; color: #555; }}
        img {{ max-width: 100%; }}
    </style>
</head>
<body>
<article>
    <header>
        <h1>{article.title}</h1>
        <div class="meta">
            <span>{article.date_label}</span> · <span>{article.read_time or f'{article.estimated_read_minutes} min read'}</span> · <span>{article.category}</span>
            <br>By <strong>{article.author}</strong>{f', {article.author_role}' if article.author_role else ''}
        </div>
    </header>
    <section>
        {body_html}
    </section>
</article>
</body>
</html>"""

    return HTMLResponse(content=html, status_code=200)
