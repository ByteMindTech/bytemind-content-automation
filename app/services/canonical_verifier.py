"""Canonical URL verification for Medium-imported articles."""

from __future__ import annotations

import re

import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)


class CanonicalVerifier:
    """Fetches a web page and extracts the rel=canonical link."""

    async def verify_canonical(self, medium_url: str, expected_canonical: str) -> dict:
        """Fetch a Medium article and verify its canonical URL."""
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "ByteMind-CanonicalVerifier/1.0"},
            ) as client:
                response = await client.get(medium_url)
                response.raise_for_status()

            canonical_found = self._extract_canonical(response.text)
            if canonical_found is None:
                return {
                    "verified": False,
                    "canonical_found": None,
                    "expected_canonical": expected_canonical,
                    "medium_url": medium_url,
                    "error": "No canonical link found in page",
                }

            normalized_found = canonical_found.strip().rstrip("/")
            normalized_expected = expected_canonical.strip().rstrip("/")
            verified = normalized_found == normalized_expected

            return {
                "verified": verified,
                "canonical_found": canonical_found,
                "expected_canonical": expected_canonical,
                "medium_url": medium_url,
                "error": None if verified else f"Canonical mismatch: found {canonical_found}",
            }
        except Exception as exc:
            logger.error("canonical_verification_failed", medium_url=medium_url, error=str(exc))
            return {
                "verified": False,
                "canonical_found": None,
                "expected_canonical": expected_canonical,
                "medium_url": medium_url,
                "error": str(exc),
            }

    def _extract_canonical(self, html: str) -> str | None:
        """Extract canonical URL from HTML without extra parser dependencies."""
        patterns = [
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
