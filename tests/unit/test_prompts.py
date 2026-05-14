"""Unit tests — prompt builder."""

from app.ai.prompts import PromptBuilder
from app.utils.markdown_parser import MarkdownParser


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()
        self.parser = MarkdownParser()

    def _article(self, sample_markdown):
        return self.parser.parse_string(sample_markdown)

    def test_build_seo_title(self, sample_markdown):
        article = self._article(sample_markdown)
        prompt = self.builder.build_seo_title(article)
        assert prompt.prompt_type == "seo_title"
        assert article.title in prompt.text
        assert "50–60 characters" in prompt.text

    def test_build_all_returns_8_prompts(self, sample_markdown):
        article = self._article(sample_markdown)
        prompts = self.builder.build_all(article)
        assert len(prompts) == 8
        types = [p.prompt_type for p in prompts]
        assert "seo_title" in types
        assert "linkedin_technical" in types
        assert "hashtags" in types

    def test_system_context_in_all_prompts(self, sample_markdown):
        article = self._article(sample_markdown)
        for prompt in self.builder.build_all(article):
            assert "ByteMind" in prompt.text, f"{prompt.prompt_type} missing ByteMind context"

    def test_anti_hallucination_rule_present(self, sample_markdown):
        article = self._article(sample_markdown)
        for prompt in self.builder.build_all(article):
            assert "NEVER" in prompt.text, f"{prompt.prompt_type} missing NEVER rule"
