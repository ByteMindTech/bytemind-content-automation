"""Unit tests — Markdown parser."""

import pytest

from app.utils.markdown_parser import MarkdownParser


class TestMarkdownParser:
    def setup_method(self):
        self.parser = MarkdownParser()

    def test_parse_valid_article(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        assert parsed.title == "Enterprise RAG on Vertex AI: A Production Guide"
        assert parsed.slug == "enterprise-rag-vertex-ai"
        assert parsed.category == "ai"
        assert "rag" in parsed.tags
        assert parsed.featured is True
        assert parsed.author == "ByteMind Team"

    def test_reading_time_estimated(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        assert parsed.estimated_read_minutes >= 1

    def test_word_count_nonzero(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        assert parsed.word_count > 0

    def test_headings_extracted(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        headings = [h["text"] for h in parsed.headings]
        assert "Introduction" in headings
        assert "Architecture Overview" in headings

    def test_code_blocks_extracted(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        assert len(parsed.code_blocks) >= 1
        assert parsed.code_blocks[0]["language"] == "python"

    def test_toc_built(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown)
        assert len(parsed.toc) >= 2
        assert all("anchor" in item for item in parsed.toc)

    def test_missing_required_field_raises(self):
        bad_md = "---\ntitle: No Slug Here\n---\nContent"
        with pytest.raises(ValueError, match="Missing required frontmatter fields"):
            self.parser.parse_string(bad_md)

    def test_source_path_stored(self, sample_markdown):
        parsed = self.parser.parse_string(sample_markdown, source_path="/some/path.md")
        assert parsed.source_path == "/some/path.md"
