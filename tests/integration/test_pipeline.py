"""Integration test — full pipeline with mocked AI and Medium."""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.engine import GenerationResult
from app.utils.markdown_parser import MarkdownParser


class TestFullPipelineMocked:
    """
    Tests the full ingest → AI enrich pipeline using mocked AI calls.
    No real Gemini/OpenAI calls are made.
    """

    def test_parser_produces_valid_article(self, sample_markdown):
        parser = MarkdownParser()
        parsed = parser.parse_string(sample_markdown, source_path="test.md")
        assert parsed.slug == "enterprise-rag-vertex-ai"
        assert parsed.word_count > 0
        assert len(parsed.toc) > 0

    def test_mock_generation_result(self, sample_markdown):
        """Ensure GenerationResult dataclass is well-formed."""
        result = GenerationResult(
            prompt_type="seo_title",
            provider="gemini",
            model="gemini-1.5-pro",
            output="Enterprise RAG on Vertex AI: Production Guide",
            output_validated=True,
            validation_issues=[],
            tokens_input=150,
            tokens_output=15,
            cost_usd=0.0000152,
            latency_ms=1200,
            retry_count=0,
        )
        assert result.output_validated
        assert result.cost_usd > 0

    @pytest.mark.asyncio
    @patch("app.ai.engine.GeminiClient.generate", new_callable=AsyncMock)
    async def test_ai_engine_returns_mock_result(self, mock_generate, sample_markdown):
        mock_result = GenerationResult(
            prompt_type="seo_title",
            provider="gemini",
            model="gemini-1.5-pro",
            output="Enterprise RAG on Vertex AI",
            output_validated=True,
            validation_issues=[],
            tokens_input=100,
            tokens_output=10,
            cost_usd=0.0001,
            latency_ms=500,
            retry_count=0,
        )
        mock_generate.return_value = mock_result

        from app.ai.engine import AIEngine
        from app.ai.prompts import PromptBuilder
        from app.utils.markdown_parser import MarkdownParser

        parser = MarkdownParser()
        parsed = parser.parse_string(sample_markdown)
        builder = PromptBuilder()
        prompt = builder.build_seo_title(parsed)

        # Force gemini provider for this test
        with patch.dict(os.environ, {"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "fake-key"}):
            engine = AIEngine()
            engine._gemini = AsyncMock()
            engine._gemini.generate = AsyncMock(return_value=mock_result)
            engine._provider = "gemini"

            result = await engine.generate(prompt)
            assert result.prompt_type == "seo_title"
            assert result.output == "Enterprise RAG on Vertex AI"
