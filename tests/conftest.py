"""Shared pytest fixtures."""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# ── Force test environment before any app imports ────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-must-be-at-least-32-chars")
os.environ.setdefault("ACTIONS_API_KEY", "test-api-key-must-be-at-least-32-chars-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://bytemind:testpassword@localhost:5432/bytemind_test")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("AI_PROVIDER", "gemini")
os.environ.setdefault("MEDIUM_DRY_RUN", "true")
os.environ.setdefault("MEDIUM_INTEGRATION_TOKEN", "")
os.environ.setdefault("MEDIUM_AUTHOR_ID", "")


@pytest.fixture
def sample_markdown() -> str:
    return """\
---
title: "Enterprise RAG on Vertex AI: A Production Guide"
slug: enterprise-rag-vertex-ai
date: 2024-11-15
dateLabel: November 15, 2024
category: ai
categoryColor: "#00d4ff"
tags:
  - ai
  - rag
  - vertex-ai
  - gcp
author: ByteMind Team
authorRole: AI Engineering
excerpt: "A comprehensive guide to building production-grade RAG systems on Google Cloud Vertex AI."
featured: true
---

## Introduction

Retrieval-Augmented Generation (RAG) is a powerful pattern for grounding LLM responses
in verified enterprise knowledge.

## Architecture Overview

The system consists of three main components:

1. **Document Ingestion Pipeline** — extracts and chunks documents
2. **Vector Store** — stores embeddings in Vertex AI Vector Search
3. **Generation Layer** — uses Gemini to synthesize answers

```python
from vertexai.language_models import TextEmbeddingModel

model = TextEmbeddingModel.from_pretrained("textembedding-gecko@003")
embeddings = model.get_embeddings(["Enterprise RAG architecture"])
```

## Conclusion

RAG on Vertex AI provides enterprise-grade retrieval with Google Cloud security guarantees.
"""
