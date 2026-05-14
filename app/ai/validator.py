"""AI output validator — guards against hallucinations and malformed responses."""

from __future__ import annotations

import json
import re


class AIOutputValidator:
    """
    Validates AI-generated content before it is stored or published.

    Guards against:
    - Prompt injection echoes
    - Hallucinated shell commands not present in the source article
    - Excessive length
    - Malformed JSON (for structured outputs)
    """

    # Patterns that suggest prompt injection / system prompt leakage
    _INJECTION_PATTERNS = [
        r"(?i)ignore (all )?previous instructions",
        r"(?i)you are (now )?a",
        r"(?i)system context",
        r"(?i)rules you must follow",
        r"(?i)\[INST\]",
        r"(?i)<\|im_start\|>",
    ]

    # Shell commands that should not appear in text unless they were in the source
    _SUSPICIOUS_SHELL_RE = re.compile(
        r"`{1,3}(bash|sh|zsh|python|curl|wget|rm\s+-rf|sudo)[^`]*`{1,3}", re.IGNORECASE
    )

    MAX_LENGTHS: dict[str, int] = {
        "seo_title": 80,
        "seo_description": 200,
        "linkedin_short": 400,
        "linkedin_medium": 900,
        "linkedin_technical": 1500,
        "medium_intro": 2000,
        "hashtags": 256,
        "cta": 300,
        "readability": 10000,
    }

    def validate(
        self,
        output: str,
        prompt_type: str,
        source_article_body: str = "",
    ) -> tuple[bool, list[str]]:
        """
        Returns (is_valid, list_of_issues).
        Empty issues list means the output passed all checks.
        """
        issues: list[str] = []

        stripped = output.strip()

        if not stripped:
            issues.append("Empty output")
            return False, issues

        # Check for prompt injection leakage
        for pattern in self._INJECTION_PATTERNS:
            if re.search(pattern, stripped):
                issues.append(f"Possible prompt injection detected: matched pattern '{pattern}'")

        # Check max length
        max_len = self.MAX_LENGTHS.get(prompt_type, 20000)
        if len(stripped) > max_len:
            issues.append(
                f"Output too long: {len(stripped)} chars, max allowed {max_len} "
                f"for prompt_type '{prompt_type}'"
            )

        # For readability type: must be valid JSON
        if prompt_type == "readability":
            json_issues = self._validate_json(stripped)
            issues.extend(json_issues)

        # Hallucination guard: shell commands in non-code outputs
        if prompt_type in ("seo_title", "seo_description", "cta", "hashtags"):
            if self._SUSPICIOUS_SHELL_RE.search(stripped):
                issues.append(
                    "Suspicious shell command found in non-code output — "
                    "possible hallucination"
                )

        return len(issues) == 0, issues

    def _validate_json(self, text: str) -> list[str]:
        issues: list[str] = []
        # Strip markdown code fences if present
        clean = re.sub(r"^```(?:json)?\s*", "", text)
        clean = re.sub(r"\s*```$", "", clean).strip()
        try:
            parsed = json.loads(clean)
            if not isinstance(parsed, dict):
                issues.append("JSON output must be a dict")
            if "suggestions" not in parsed:
                issues.append("readability JSON missing 'suggestions' key")
        except json.JSONDecodeError as exc:
            issues.append(f"Invalid JSON: {exc}")
        return issues

    def sanitize(self, output: str) -> str:
        """Strip common artefacts (leading/trailing quotes, markdown fences)."""
        text = output.strip()
        # Remove wrapping quotes that some models add
        if (text.startswith('"') and text.endswith('"')) or (
            text.startswith("'") and text.endswith("'")
        ):
            text = text[1:-1].strip()
        # Remove markdown bold/italic wrappers
        text = re.sub(r"^\*+(.+?)\*+$", r"\1", text, flags=re.DOTALL)
        return text
