"""
CLI to publish blog articles to Medium via GraphQL API.

Usage:
    python -m app.medium.publish <slug> [--status draft|public] [--delete <post_id>]

Examples:
    python -m app.medium.publish integrating-gemini-enterprise-workflows
    python -m app.medium.publish responsible-ai-security-patterns-enterprise-llm --status public
    python -m app.medium.publish --delete c2b0564327c7
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.config import get_settings
from app.medium.graphql_publisher import MediumGraphQLPublisher
from app.utils.markdown_parser import MarkdownParser


def publish_article(slug: str, status: str = "draft") -> None:
    """Parse a blog article and publish it to Medium."""
    settings = get_settings()
    content_path = Path(settings.content_source_path)
    md_file = content_path / f"{slug}.md"

    if not md_file.exists():
        print(f"❌ Article not found: {md_file}")
        sys.exit(1)

    # Parse the markdown
    parser = MarkdownParser()
    article = parser.parse_file(md_file)

    print(f"📝 Article: {article.title}")
    print(f"   Slug: {article.slug}")
    print(f"   Words: {article.word_count}")
    print(f"   Tags: {', '.join(article.tags[:5])}")
    print(f"   Status: {status}")
    print()

    canonical_url = f"{settings.medium_canonical_base_url}/{article.slug}"
    print(f"🔗 Canonical: {canonical_url}")
    print()

    # Publish via GraphQL API
    publisher = MediumGraphQLPublisher()
    result = publisher.publish(
        title=article.title,
        markdown_body=article.content_body,
        tags=article.tags[:5],
        canonical_url=canonical_url,
        publish_status=status,
    )

    if result.get("dry_run"):
        print("🏜️  DRY RUN — set MEDIUM_DRY_RUN=false to publish for real")
        print(f"   Would publish to: {result['url']}")
    else:
        print(f"✅ Published to Medium!")
        print(f"   Post ID: {result['post_id']}")
        print(f"   URL: {result['url']}")
        print(f"   Edit: {result['edit_url']}")
        print(f"   Paragraphs: {result['paragraphs_count']}")
        print(f"   Status: {result['status']}")


def main() -> None:
    if "--delete" in sys.argv:
        idx = sys.argv.index("--delete")
        if idx + 1 < len(sys.argv):
            post_id = sys.argv[idx + 1]
            publisher = MediumGraphQLPublisher()
            publisher.delete_post(post_id)
            print(f"🗑️  Deleted post: {post_id}")
            return

    if len(sys.argv) < 2:
        print("Usage: python -m app.medium.publish <slug> [--status draft|public]")
        print("       python -m app.medium.publish --delete <post_id>")
        print("\nAvailable articles:")
        settings = get_settings()
        content_path = Path(settings.content_source_path)
        if content_path.exists():
            for f in sorted(content_path.glob("*.md")):
                print(f"  - {f.stem}")
        sys.exit(1)

    slug = sys.argv[1]
    status = "draft"

    if "--status" in sys.argv:
        idx = sys.argv.index("--status")
        if idx + 1 < len(sys.argv):
            status = sys.argv[idx + 1]

    publish_article(slug, status)


if __name__ == "__main__":
    main()
