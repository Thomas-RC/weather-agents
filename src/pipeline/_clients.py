"""Współdzielone klienty Vertex AI / Gemini — leniwie inicjalizowane."""

from __future__ import annotations

from functools import lru_cache

import vertexai
from google import genai
from vertexai.vision_models import MultiModalEmbeddingModel

from src.config import get_settings


@lru_cache(maxsize=1)
def get_genai_client() -> genai.Client:
    s = get_settings()
    return genai.Client(
        vertexai=True,
        project=s.google_cloud_project,
        location=s.google_cloud_location,
    )


@lru_cache(maxsize=1)
def _vertex_init() -> bool:
    s = get_settings()
    vertexai.init(project=s.google_cloud_project, location=s.google_cloud_location)
    return True


@lru_cache(maxsize=1)
def get_mm_embedding_model() -> MultiModalEmbeddingModel:
    _vertex_init()
    return MultiModalEmbeddingModel.from_pretrained(get_settings().gemini_mm_embedding_model)
