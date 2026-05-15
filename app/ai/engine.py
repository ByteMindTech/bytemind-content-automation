"""Async AI engine with multi-LLM routing, retry, and token tracking."""

from __future__ import annotations

import asyncio
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
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}
_OPENAI_COSTS = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# Smart multi-LLM routing: cheap prompts → flash, complex → pro
MODEL_ROUTING: dict[str, dict[str, str]] = {
    # prompt_type → {gemini: model, openai: model}
    "seo_title": {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"},
    "seo_description": {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"},
    "hashtags": {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"},
    "cta": {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"},
    # Complex prompts — need higher-quality models
    "linkedin_short": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
    "linkedin_medium": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
    "linkedin_technical": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
    "medium_intro": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
    "readability": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
    "revision": {"gemini": "gemini-2.5-pro", "openai": "gpt-4o"},
}

# Concurrency limiter to avoid rate-limiting from AI providers
_SEMAPHORE = asyncio.Semaphore(4)


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
        self._default_model = _settings.gemini_model
        self._validator = AIOutputValidator()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
        model_override: str | None = None,
        retry_count: int = 0,
    ) -> GenerationResult:
        """Call Gemini asynchronously and return a GenerationResult."""
        model_name = model_override or self._default_model
        model = self._genai.GenerativeModel(
            model_name=model_name,
            generation_config=self._genai.GenerationConfig(
                temperature=_settings.gemini_temperature,
                max_output_tokens=prompt.max_output_tokens,
            ),
        )

        start_ms = int(time.time() * 1000)
        async with _SEMAPHORE:
            response = await model.generate_content_async(prompt.text)
        latency = int(time.time() * 1000) - start_ms

        raw_output = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count or 0
        tokens_out = response.usage_metadata.candidates_token_count or 0
        cost = self._calc_cost(model_name, tokens_in, tokens_out, _GEMINI_COSTS)

        sanitized = self._validator.sanitize(raw_output)
        valid, issues = self._validator.validate(sanitized, prompt.prompt_type, source_body)

        logger.info(
            "gemini_generate",
            prompt_type=prompt.prompt_type,
            model=model_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost, 6),
            latency_ms=latency,
            valid=valid,
        )

        return GenerationResult(
            prompt_type=prompt.prompt_type,
            provider="gemini",
            model=model_name,
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
    """Async OpenAI client as fallback for Gemini."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=_settings.openai_api_key)
        self._default_model = _settings.openai_model
        self._validator = AIOutputValidator()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
        model_override: str | None = None,
        retry_count: int = 0,
    ) -> GenerationResult:
        model_name = model_override or self._default_model
        start_ms = int(time.time() * 1000)

        async with _SEMAPHORE:
            response = await self._client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior technical content strategist for ByteMind, "
                            "an enterprise AI & cloud consultancy. Generate precise, factual "
                            "content. Never hallucinate commands, tools, or architecture claims."
                        ),
                    },
                    {"role": "user", "content": prompt.text},
                ],
                max_tokens=prompt.max_output_tokens,
                temperature=0.7,
            )
        latency = int(time.time() * 1000) - start_ms

        raw_output = response.choices[0].message.content or ""
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        cost = GeminiClient._calc_cost(model_name, tokens_in, tokens_out, _OPENAI_COSTS)

        sanitized = self._validator.sanitize(raw_output)
        valid, issues = self._validator.validate(sanitized, prompt.prompt_type, source_body)

        return GenerationResult(
            prompt_type=prompt.prompt_type,
            provider="openai",
            model=model_name,
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
    or OpenAI (fallback) based on config and smart model routing.
    """

    def __init__(self) -> None:
        self._gemini: GeminiClient | None = None
        self._openai: OpenAIClient | None = None
        self._provider = _settings.ai_provider

        if self._provider in ("gemini", "auto") and _settings.gemini_api_key:
            self._gemini = GeminiClient()
        if self._provider in ("openai", "auto") and _settings.openai_api_key:
            self._openai = OpenAIClient()

    def _get_model_for_prompt(self, prompt_type: str, provider: str) -> str | None:
        """Get the optimal model for a prompt type via smart routing."""
        routing = MODEL_ROUTING.get(prompt_type)
        if routing:
            return routing.get(provider)
        return None

    async def generate(
        self,
        prompt: PromptTemplate,
        source_body: str = "",
    ) -> GenerationResult:
        """Generate content asynchronously. Falls back to OpenAI if Gemini fails."""
        if self._provider == "openai" and self._openai:
            model = self._get_model_for_prompt(prompt.prompt_type, "openai")
            return await self._openai.generate(prompt, source_body, model_override=model)

        if self._gemini:
            try:
                model = self._get_model_for_prompt(prompt.prompt_type, "gemini")
                return await self._gemini.generate(prompt, source_body, model_override=model)
            except Exception as exc:
                logger.warning(
                    "gemini_failed_fallback_openai",
                    prompt_type=prompt.prompt_type,
                    error=str(exc),
                )
                if self._openai:
                    model = self._get_model_for_prompt(prompt.prompt_type, "openai")
                    return await self._openai.generate(
                        prompt, source_body, model_override=model
                    )
                raise

        raise RuntimeError(
            "No AI provider available. Configure GEMINI_API_KEY or OPENAI_API_KEY."
        )

    async def generate_batch(
        self,
        prompts: list[PromptTemplate],
        source_body: str = "",
    ) -> list[GenerationResult]:
        """Generate multiple prompts concurrently with semaphore-limited parallelism."""
        tasks = [self.generate(prompt, source_body) for prompt in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful: list[GenerationResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "batch_generation_failed",
                    prompt_type=prompts[i].prompt_type,
                    error=str(result),
                )
            else:
                successful.append(result)
        return successful
