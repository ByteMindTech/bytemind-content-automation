"""Gemini AI client with retry, token tracking, and OpenAI fallback."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.prompts import PromptTemplate
from app.ai.validator import AIOutputValidator
from app.config import get_settings
from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
_settings = get_settings()

# Token cost per 1M tokens (approximate, update as pricing changes)
_GEMINI_COSTS = {
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
}
_OPENAI_COSTS = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


@dataclass
class GenerationResult:
    """Result of a single AI generation call."""

    prompt_type: str
    provider: str
    model: str
    output: str
    output_validated: bool
    validation_issues: list[str]
    tokens_input: int
    tokens_output: int
    cost_usd: float
    latency_ms: int
    retry_count: int


class GeminiClient:
    """Async Gemini client using google-generativeai SDK."""

    def __init__(self) -> None:
        import google.generativeai as genai

        genai.configure(api_key=_settings.gemini_api_key)
        self._genai = genai
        self._model_name = _settings.gemini_model
        self._validator = AIOutputValidator()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
        retry_count: int = 0,
    ) -> GenerationResult:
        """Call Gemini and return a GenerationResult."""
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            generation_config=self._genai.GenerationConfig(
                temperature=_settings.gemini_temperature,
                max_output_tokens=prompt.max_output_tokens,
            ),
        )

        start_ms = int(time.time() * 1000)
        response = model.generate_content(prompt.text)
        latency = int(time.time() * 1000) - start_ms

        raw_output = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count or 0
        tokens_out = response.usage_metadata.candidates_token_count or 0
        cost = self._calc_cost(self._model_name, tokens_in, tokens_out, _GEMINI_COSTS)

        sanitized = self._validator.sanitize(raw_output)
        valid, issues = self._validator.validate(sanitized, prompt.prompt_type, source_body)

        logger.info(
            "gemini_generate",
            prompt_type=prompt.prompt_type,
            model=self._model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost, 6),
            latency_ms=latency,
            valid=valid,
        )

        return GenerationResult(
            prompt_type=prompt.prompt_type,
            provider="gemini",
            model=self._model_name,
            output=sanitized,
            output_validated=valid,
            validation_issues=issues,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
            latency_ms=latency,
            retry_count=retry_count,
        )

    @staticmethod
    def _calc_cost(model: str, tokens_in: int, tokens_out: int, table: dict) -> float:
        costs = table.get(model, {"input": 0.0, "output": 0.0})
        return (tokens_in * costs["input"] + tokens_out * costs["output"]) / 1_000_000


class OpenAIClient:
    """OpenAI client as fallback for Gemini."""

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=_settings.openai_api_key)
        self._model = _settings.openai_model
        self._validator = AIOutputValidator()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
        retry_count: int = 0,
    ) -> GenerationResult:
        start_ms = int(time.time() * 1000)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt.text}],
            max_tokens=prompt.max_output_tokens,
            temperature=0.7,
        )
        latency = int(time.time() * 1000) - start_ms
        raw_output = response.choices[0].message.content or ""
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        cost = GeminiClient._calc_cost(self._model, tokens_in, tokens_out, _OPENAI_COSTS)

        sanitized = self._validator.sanitize(raw_output)
        valid, issues = self._validator.validate(sanitized, prompt.prompt_type, source_body)

        return GenerationResult(
            prompt_type=prompt.prompt_type,
            provider="openai",
            model=self._model,
            output=sanitized,
            output_validated=valid,
            validation_issues=issues,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
            latency_ms=latency,
            retry_count=retry_count,
        )


class AIEngine:
    """
    Facade that routes generation requests to Gemini (primary)
    or OpenAI (fallback) based on config and availability.
    """

    def __init__(self) -> None:
        self._gemini: GeminiClient | None = None
        self._openai: OpenAIClient | None = None
        self._provider = _settings.ai_provider

        if self._provider in ("gemini", "auto") and _settings.gemini_api_key:
            self._gemini = GeminiClient()
        if self._provider in ("openai", "auto") and _settings.openai_api_key:
            self._openai = OpenAIClient()

    def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
    ) -> GenerationResult:
        """Generate content. Falls back to OpenAI if Gemini fails."""
        if self._provider == "openai" and self._openai:
            return self._openai.generate(prompt, source_body)

        if self._gemini:
            try:
                return self._gemini.generate(prompt, source_body)
            except Exception as exc:
                logger.warning(
                    "gemini_failed_fallback_openai",
                    prompt_type=prompt.prompt_type,
                    error=str(exc),
                )
                if self._openai:
                    return self._openai.generate(prompt, source_body)
                raise

        raise RuntimeError(
            "No AI provider available. Configure GEMINI_API_KEY or OPENAI_API_KEY."
        )
