"""Unit tests for canonical URL verification."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.canonical_verifier import CanonicalVerifier


def test_extract_canonical_supports_multiple_attribute_orders() -> None:
    verifier = CanonicalVerifier()

    html_rel_first = (
        '<html><head><link rel="canonical" href="https://bytemind.fr/blogs/test" /></head></html>'
    )
    html_href_first = (
        '<html><head><link href="https://bytemind.fr/blogs/test" rel="canonical" /></head></html>'
    )

    assert verifier._extract_canonical(html_rel_first) == "https://bytemind.fr/blogs/test"
    assert verifier._extract_canonical(html_href_first) == "https://bytemind.fr/blogs/test"


@pytest.mark.asyncio
async def test_verify_canonical_normalizes_trailing_slashes() -> None:
    medium_url = "https://medium.com/@bytemind/test-article"
    expected_canonical = "https://bytemind.fr/blogs/test-article/"
    response = httpx.Response(
        200,
        text=(
            '<html><head><link rel="canonical" '
            'href="https://bytemind.fr/blogs/test-article" /></head></html>'
        ),
        request=httpx.Request("GET", medium_url),
    )

    with patch("app.services.canonical_verifier.httpx.AsyncClient") as async_client_cls:
        client = AsyncMock()
        client.get.return_value = response
        async_client_cls.return_value.__aenter__.return_value = client

        verifier = CanonicalVerifier()
        result = await verifier.verify_canonical(medium_url, expected_canonical)

    assert result == {
        "verified": True,
        "canonical_found": "https://bytemind.fr/blogs/test-article",
        "expected_canonical": expected_canonical,
        "medium_url": medium_url,
        "error": None,
    }


@pytest.mark.asyncio
async def test_verify_canonical_reports_missing_link() -> None:
    medium_url = "https://medium.com/@bytemind/test-article"
    expected_canonical = "https://bytemind.fr/blogs/test-article"
    response = httpx.Response(
        200,
        text="<html><head></head><body>No canonical here</body></html>",
        request=httpx.Request("GET", medium_url),
    )

    with patch("app.services.canonical_verifier.httpx.AsyncClient") as async_client_cls:
        client = AsyncMock()
        client.get.return_value = response
        async_client_cls.return_value.__aenter__.return_value = client

        verifier = CanonicalVerifier()
        result = await verifier.verify_canonical(medium_url, expected_canonical)

    assert result == {
        "verified": False,
        "canonical_found": None,
        "expected_canonical": expected_canonical,
        "medium_url": medium_url,
        "error": "No canonical link found in page",
    }
