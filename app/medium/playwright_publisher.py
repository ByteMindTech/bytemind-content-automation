"""
Medium Playwright Publisher — Browser automation for publishing to Medium.

Since Medium's API no longer issues integration tokens (Jan 2025), this module
uses Playwright to automate Medium's web editor, which accepts full HTML including
<table>, <pre><code>, and all standard elements.

Flow:
  1. Load stored session cookies (authenticate once manually, export cookies)
  2. Navigate to medium.com/new-story
  3. Inject HTML content via clipboard paste / execCommand
  4. Set title, tags, canonical URL
  5. Save as draft (default) or publish

Requirements:
  - playwright (pip install playwright && playwright install chromium)
  - Stored Medium session cookies (JSON file)
"""

from __future__ import annotations

import json
import re
from html import escape as html_escape
from pathlib import Path

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()

# Default cookies storage path (project root / content/)
COOKIES_PATH = Path(__file__).resolve().parent.parent.parent / "content" / ".medium-cookies.json"


class PlaywrightMediumPublisher:
    """Publish articles to Medium via browser automation."""

    def __init__(self, cookies_path: Path | str | None = None) -> None:
        self._cookies_path = Path(cookies_path) if cookies_path else COOKIES_PATH
        self._dry_run = _settings.medium_dry_run
        self._canonical_base = _settings.medium_canonical_base_url

    async def publish(
        self,
        *,
        title: str,
        html_body: str,
        tags: list[str],
        canonical_url: str | None = None,
        publish_status: str = "draft",
    ) -> dict:
        """
        Publish an article to Medium via Playwright.

        Args:
            title: Article title
            html_body: Full HTML content (tables, code blocks, etc.)
            tags: Up to 5 tags
            canonical_url: Original article URL for SEO
            publish_status: "draft" (default) or "public"

        Returns:
            Dict with: url, status, draft_url
        """
        if self._dry_run:
            logger.info("playwright_medium_dry_run", title=title, tags=tags)
            return {
                "url": f"https://medium.com/@melhosni/draft-{_slugify(title)}",
                "status": "dry_run",
                "dry_run": True,
            }

        if not self._cookies_path.exists():
            raise FileNotFoundError(
                f"Medium cookies not found at {self._cookies_path}. "
                "Run `python -m app.medium.auth login` to authenticate first."
            )

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            # Load stored cookies
            cookies = json.loads(self._cookies_path.read_text())
            await context.add_cookies(cookies)

            page = await context.new_page()

            try:
                # Navigate to new story editor
                await page.goto("https://medium.com/new-story", wait_until="networkidle")
                await page.wait_for_timeout(2000)

                # Check if redirected to login (cookies expired)
                if "signin" in page.url or "login" in page.url:
                    await browser.close()
                    raise PermissionError(
                        "Medium session expired. Re-run `python -m app.medium.auth login`"
                    )

                # Wait for the editor to load
                editor_selector = '[role="textbox"], [data-testid="editor"], .ProseMirror'
                await page.wait_for_selector(editor_selector, timeout=10000)

                # Set the title first
                title_selector = 'h3[data-placeholder="Title"], [data-placeholder="Title"]'
                title_el = await page.query_selector(title_selector)
                if title_el:
                    await title_el.click()
                    await page.keyboard.type(title)
                    await page.keyboard.press("Enter")
                    await page.keyboard.press("Enter")

                # Inject the HTML body into the editor
                await page.evaluate(
                    """(html) => {
                        const editor = document.querySelector('[role="textbox"], .ProseMirror, [contenteditable="true"]');
                        if (editor) {
                            editor.focus();
                            document.execCommand('insertHTML', false, html);
                        }
                    }""",
                    html_body,
                )

                await page.wait_for_timeout(2000)

                # Get the draft URL
                draft_url = page.url

                # If publish_status is "public", click publish
                if publish_status == "public":
                    await self._click_publish(page, tags, canonical_url)

                logger.info(
                    "playwright_medium_published",
                    title=title,
                    status=publish_status,
                    url=draft_url,
                )

                return {
                    "url": draft_url,
                    "status": publish_status,
                    "dry_run": False,
                }

            finally:
                await browser.close()

    async def _click_publish(self, page, tags: list[str], canonical_url: str | None) -> None:
        """Click through Medium's publish flow (Publish button → settings → confirm)."""
        # Click the "Publish" or "Ready to publish?" button
        publish_btn = await page.query_selector(
            'button:has-text("Publish"), button:has-text("Ready")'
        )
        if publish_btn:
            await publish_btn.click()
            await page.wait_for_timeout(1000)

            # Add tags if the tag input is visible
            tag_input = await page.query_selector(
                'input[placeholder*="tag"], input[placeholder*="Tag"]'
            )
            if tag_input:
                for tag in tags[:5]:
                    await tag_input.fill(tag)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(300)

            # Final publish confirmation
            confirm_btn = await page.query_selector(
                'button:has-text("Publish now"), button[data-action="publish"]'
            )
            if confirm_btn:
                await confirm_btn.click()
                await page.wait_for_timeout(3000)


def _slugify(text: str) -> str:
    """Create a URL-friendly slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60]
