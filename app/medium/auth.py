"""
Medium authentication via browser — extract session cookies for Playwright automation.

Usage:
    python -m app.medium.auth login     # Opens browser, you log in manually, cookies saved
    python -m app.medium.auth check     # Verify stored cookies are still valid
    python -m app.medium.auth clear     # Delete stored cookies

Cookies are stored at: content/.medium-cookies.json (gitignored)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

COOKIES_PATH = Path("content/.medium-cookies.json")


async def login() -> None:
    """Open a browser window for manual Medium login, then save cookies."""
    from playwright.async_api import async_playwright

    print("🔐 Opening browser for Medium login...")
    print("   Log in to your Medium account, then press Enter here when done.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await page.goto("https://medium.com/m/signin")

        # Wait for user to complete login
        input("✅ Press Enter after you've logged in to Medium...")

        # Verify we're logged in
        cookies = await context.cookies()
        medium_cookies = [c for c in cookies if "medium.com" in c.get("domain", "")]

        if not medium_cookies:
            print("❌ No Medium cookies found. Login may have failed.")
            await browser.close()
            return

        # Check for session indicators
        session_cookies = [c for c in medium_cookies if c["name"] in ("uid", "sid", "connect.sid")]
        if not session_cookies:
            print("⚠️  Warning: No session cookie found. Saving all Medium cookies anyway.")

        # Save cookies
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_text(json.dumps(medium_cookies, indent=2))
        print(f"\n✅ Saved {len(medium_cookies)} cookies to {COOKIES_PATH}")
        print(f"   Session valid for: {[c['name'] for c in session_cookies]}")

        await browser.close()


async def check() -> None:
    """Verify stored cookies are still valid."""
    if not COOKIES_PATH.exists():
        print("❌ No stored cookies. Run: python -m app.medium.auth login")
        return

    from playwright.async_api import async_playwright

    cookies = json.loads(COOKIES_PATH.read_text())
    print(f"📋 Found {len(cookies)} stored cookies")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(cookies)

        page = await context.new_page()
        await page.goto("https://medium.com/me/stories", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        if "signin" in page.url or "login" in page.url:
            print("❌ Cookies expired. Re-run: python -m app.medium.auth login")
        else:
            print(f"✅ Session valid! Logged in at: {page.url}")

        await browser.close()


def clear() -> None:
    """Delete stored cookies."""
    if COOKIES_PATH.exists():
        COOKIES_PATH.unlink()
        print("🗑️  Cookies deleted.")
    else:
        print("ℹ️  No cookies to delete.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.medium.auth [login|check|clear]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "login":
        asyncio.run(login())
    elif cmd == "check":
        asyncio.run(check())
    elif cmd == "clear":
        clear()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
