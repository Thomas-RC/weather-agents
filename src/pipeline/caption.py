"""Captioning obrazów — Gemini 2.5 Flash generuje krótki + długi opis."""

from __future__ import annotations

from google.genai import types

from src.config import get_settings
from src.pipeline._clients import get_genai_client

SHORT_PROMPT = (
    "Opisz tę mapę pogodową w JEDNYM zdaniu po polsku, MAKSYMALNIE 25 słów. "
    "Wymień TYLKO: typ obrazu (radar/satelita), gdzie widoczne zjawiska "
    "(opady/chmury/burze), nad jakim regionem. Bez wstępu i bez dygresji."
)
LONG_PROMPT = (
    "Opisz tę mapę pogodową w 2-4 zdaniach po polsku, łącznie do 100 słów. "
    "Uwzględnij: typ obrazu, widoczne zjawiska pogodowe, intensywność, "
    "regiony Polski/Europy nad którymi występują, ewentualny ruch frontów. "
    "Konkretnie i rzeczowo, bez ozdobników."
)


def caption_image(image_bytes: bytes, mime_type: str = "image/png") -> dict[str, str]:
    """Zwraca {'short': ..., 'long': ...} — opisy obrazu."""
    client = get_genai_client()
    model = get_settings().gemini_model_caption

    img_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    no_thinking = types.ThinkingConfig(thinking_budget=0)
    short = client.models.generate_content(
        model=model,
        contents=[SHORT_PROMPT, img_part],
        config=types.GenerateContentConfig(
            temperature=0.2, max_output_tokens=200, thinking_config=no_thinking
        ),
    )
    long_ = client.models.generate_content(
        model=model,
        contents=[LONG_PROMPT, img_part],
        config=types.GenerateContentConfig(
            temperature=0.3, max_output_tokens=600, thinking_config=no_thinking
        ),
    )
    return {
        "short": (short.text or "").strip(),
        "long": (long_.text or "").strip(),
    }
