"""Embedding tekstu — gemini-embedding-001 (3072 dim)."""

from __future__ import annotations

from google.genai.types import EmbedContentConfig

from src.config import get_settings
from src.pipeline._clients import get_genai_client


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embedduje teksty jako dokumenty (task RETRIEVAL_DOCUMENT). Max 250 tekstów,
    20k tok łącznie, 2048 tok na tekst."""
    if not texts:
        return []
    s = get_settings()
    resp = get_genai_client().models.embed_content(
        model=s.gemini_text_embedding_model,
        contents=texts,
        config=EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=s.text_embedding_dim,
        ),
    )
    return [list(e.values) for e in resp.embeddings]


def embed_query(query: str) -> list[float]:
    """Embedduje zapytanie użytkownika (task RETRIEVAL_QUERY)."""
    s = get_settings()
    resp = get_genai_client().models.embed_content(
        model=s.gemini_text_embedding_model,
        contents=[query],
        config=EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=s.text_embedding_dim,
        ),
    )
    return list(resp.embeddings[0].values)
