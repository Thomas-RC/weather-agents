"""Embedding multimodalny — multimodalembedding@001 (1408 dim).

Wspólna przestrzeń wektorowa dla tekstu i obrazu — pozwala na cross-modal
search ("tekst znajduje obrazy" i "obraz znajduje teksty").

Limity:
- text input: max 32 tokeny (~25-30 słów)
- image: dowolny rozmiar, automatyczny resize do 512x512
- output: 1408 dim (default), opcjonalnie 128/256/512
"""

from __future__ import annotations

from vertexai.vision_models import Image as VImage

from src.pipeline._clients import get_mm_embedding_model

MAX_TEXT_CHARS = 120  # bezpieczny zapas pod limit 32 tok


def embed_image_with_caption(image_bytes: bytes, caption_short: str) -> list[float]:
    """Embedduje obraz z krótkim captionem jako kontekstem.

    Zwraca image_embedding (1408d) — ten wektor reprezentuje obraz w wspólnej
    przestrzeni z embeddingami tekstowymi tego samego modelu.
    """
    model = get_mm_embedding_model()
    img = VImage(image_bytes=image_bytes)
    out = model.get_embeddings(
        image=img,
        contextual_text=caption_short[:MAX_TEXT_CHARS],
        dimension=1408,
    )
    return list(out.image_embedding)


def embed_text_for_mm(text: str) -> list[float]:
    """Embedduje sam tekst do przestrzeni multimodalnej (do cross-modal query).

    Używamy gdy user pisze tekst, a chcemy znaleźć podobne obrazy w mm_1408.
    """
    model = get_mm_embedding_model()
    out = model.get_embeddings(
        contextual_text=text[:MAX_TEXT_CHARS],
        dimension=1408,
    )
    return list(out.text_embedding)


def embed_image_for_mm(image_bytes: bytes) -> list[float]:
    """Embedduje sam obraz (do image-to-image search)."""
    model = get_mm_embedding_model()
    img = VImage(image_bytes=image_bytes)
    out = model.get_embeddings(image=img, dimension=1408)
    return list(out.image_embedding)
