"""Structured prompt templates for content enrichment."""

from dataclasses import dataclass

from app.utils.markdown_parser import ParsedArticle


@dataclass
class PromptTemplate:
    """A named prompt with type tag and rendered text."""

    prompt_type: str
    text: str
    max_output_tokens: int = 2048


class PromptBuilder:
    """Build structured prompts for each enrichment task."""

    SYSTEM_CONTEXT = """You are an expert technical content strategist for ByteMind,
an enterprise consulting firm specializing in Data Engineering, Google Cloud Platform,
Enterprise AI, Agentic AI, Secure RAG architectures, Responsible AI,
and Cloud modernization.

Rules you MUST follow:
- NEVER invent or hallucinate commands, APIs, or architecture claims not present in the article.
- NEVER reduce technical precision or remove code examples.
- ALWAYS preserve the author's voice and technical depth.
- Output ONLY the requested content — no preamble, no meta-commentary.
- Use European professional English (formal but accessible).
"""

    def build_seo_title(self, article: ParsedArticle) -> PromptTemplate:
        return PromptTemplate(
            prompt_type="seo_title",
            text=f"""{self.SYSTEM_CONTEXT}

Generate an SEO-optimized title for the following technical article.
Requirements:
- 50–60 characters
- Include the primary keyword from the article
- Compelling and accurate — no clickbait
- Do not wrap in quotes

Article title: {article.title}
Category: {article.category}
Tags: {', '.join(article.tags)}
Excerpt: {article.excerpt}
""",
            max_output_tokens=64,
        )

    def build_seo_description(self, article: ParsedArticle) -> PromptTemplate:
        return PromptTemplate(
            prompt_type="seo_description",
            text=f"""{self.SYSTEM_CONTEXT}

Write an SEO meta description for this technical article.
Requirements:
- 150–160 characters
- Include primary keyword naturally
- Describe the value the reader gets
- No quotes

Article title: {article.title}
Category: {article.category}
Tags: {', '.join(article.tags)}
Excerpt: {article.excerpt}
""",
            max_output_tokens=200,
        )

    def build_linkedin_short(self, article: ParsedArticle) -> PromptTemplate:
        body_preview = article.content_body[:800]
        return PromptTemplate(
            prompt_type="linkedin_short",
            text=f"""{self.SYSTEM_CONTEXT}

Write a SHORT LinkedIn post (max 300 characters) to promote this technical article.
- Hook in the first line
- One key insight from the article
- End with a CTA to read the full post
- No hashtags yet

Article title: {article.title}
Excerpt: {article.excerpt}
Content preview: {body_preview}
""",
            max_output_tokens=2048,
        )

    def build_linkedin_medium(self, article: ParsedArticle) -> PromptTemplate:
        body_preview = article.content_body[:1500]
        return PromptTemplate(
            prompt_type="linkedin_medium",
            text=f"""{self.SYSTEM_CONTEXT}

Write a MEDIUM LinkedIn post (400–700 characters) to promote this technical article.
- Strong hook with a problem statement or surprising fact
- 2–3 key takeaways from the article
- Professional ByteMind tone
- End with a question to drive comments

Article title: {article.title}
Category: {article.category}
Excerpt: {article.excerpt}
Content preview: {body_preview}
""",
            max_output_tokens=2048,
        )

    def build_linkedin_technical(self, article: ParsedArticle) -> PromptTemplate:
        body_preview = article.content_body[:3000]
        return PromptTemplate(
            prompt_type="linkedin_technical",
            text=f"""{self.SYSTEM_CONTEXT}

Write a TECHNICAL LinkedIn article teaser (800–1200 characters) for this post.
Target audience: senior engineers, data architects, CTO/CDOs.
Structure:
1. Context / Problem (1–2 sentences)
2. Solution approach described in the article (3–4 sentences, preserve technical accuracy)
3. Key architectural or implementation details
4. Business impact
5. Invitation to read full article

Article title: {article.title}
Category: {article.category}
Tags: {', '.join(article.tags)}
Excerpt: {article.excerpt}
Content preview: {body_preview}
""",
            max_output_tokens=4096,
        )

    def build_medium_intro(self, article: ParsedArticle) -> PromptTemplate:
        body_preview = article.content_body[:2000]
        return PromptTemplate(
            prompt_type="medium_intro",
            text=f"""{self.SYSTEM_CONTEXT}

Write a compelling 2–3 paragraph introduction for this article to be published on Medium.
- Paragraph 1: Industry context / problem statement
- Paragraph 2: What this article covers (technical preview)
- Paragraph 3: Who should read this and what they'll gain
Preserve all technical accuracy. Do not summarize — this will precede the full article.

Article title: {article.title}
Excerpt: {article.excerpt}
Content preview: {body_preview}
""",
            max_output_tokens=4096,
        )

    def build_hashtags(self, article: ParsedArticle) -> PromptTemplate:
        return PromptTemplate(
            prompt_type="hashtags",
            text=f"""{self.SYSTEM_CONTEXT}

Generate exactly 8 LinkedIn hashtags for this technical article.
- Mix: 2 broad (e.g. #AI, #CloudComputing), 4 specific (e.g. #VertexAI, #RAG), 2 brand (#ByteMind)
- All lowercase, no spaces, prefixed with #
- Return them on a single line separated by spaces

Article title: {article.title}
Category: {article.category}
Tags: {', '.join(article.tags)}
""",
            max_output_tokens=128,
        )

    def build_cta(self, article: ParsedArticle) -> PromptTemplate:
        return PromptTemplate(
            prompt_type="cta",
            text=f"""{self.SYSTEM_CONTEXT}

Write a 1-sentence call-to-action (CTA) for this article.
- Professional, not aggressive
- Mention ByteMind if natural
- Encourage readers to visit bytemind.fr or reach out for consulting

Article title: {article.title}
Category: {article.category}
""",
            max_output_tokens=128,
        )

    def build_readability_pass(self, article: ParsedArticle) -> PromptTemplate:
        """Improve readability while preserving technical precision."""
        return PromptTemplate(
            prompt_type="readability",
            text=f"""{self.SYSTEM_CONTEXT}

Review the following technical article and suggest readability improvements.
Return a JSON object with these keys:
- "suggestions": list of {{"location": "...", "original": "...", "improved": "..."}}
- "overall_score": integer 1–10 (current readability)
- "summary": 1-sentence overall assessment

IMPORTANT: Preserve ALL technical content, commands, and code blocks exactly.
Only suggest improvements for sentence clarity, paragraph structure, or transitions.

Article title: {article.title}
Content (first 3000 chars):
{article.content_body[:3000]}
""",
            max_output_tokens=2048,
        )

    def build_all(self, article: ParsedArticle) -> list[PromptTemplate]:
        """Return all prompt templates for a full enrichment run."""
        return [
            self.build_seo_title(article),
            self.build_seo_description(article),
            self.build_linkedin_short(article),
            self.build_linkedin_medium(article),
            self.build_linkedin_technical(article),
            self.build_medium_intro(article),
            self.build_hashtags(article),
            self.build_cta(article),
        ]
