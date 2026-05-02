"""Wektorowy retrieval — narzędzia używane przez sub-agentów.

Każda funkcja zwraca listę dictów (JSON-serializable) — to wymaganie ADK.
"""

from __future__ import annotations

from typing import Any

from src.config import get_settings
from src.pipeline import embed_mm, embed_text
from src.storage import minio_store, qdrant_store


def _hit_to_dict(hit, *, with_url: bool = False) -> dict[str, Any]:
    p = hit.payload or {}
    out: dict[str, Any] = {
        "id": hit.id,
        "score": round(hit.score, 4),
        "source": p.get("source"),
        "modality": p.get("modality"),
        "captured_at": p.get("captured_at"),
        "caption_short": p.get("caption_short"),
        "caption_long": p.get("caption_long"),
        "content": p.get("content"),
    }
    if with_url and p.get("minio_key"):
        try:
            out["url"] = minio_store.presigned_get_url(p["minio_key"], expires_in=3600)
        except Exception:
            out["url"] = None
    # Filtrujemy None żeby nie zaśmiecać kontekstu LLM
    return {k: v for k, v in out.items() if v is not None}


# --------------------------------------------------------------------------
# Tekst — daily summaries + warnings
# --------------------------------------------------------------------------
def search_text_chunks(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Wyszukuje semantycznie w bazie chunków tekstowych: dziennych podsumowań pogodowych
    i ostrzeżeń meteorologicznych. Używaj gdy pytanie dotyczy ogólnej historii pogody,
    podobnych dni z przeszłości, albo ostrzeżeń.

    Args:
        query: zapytanie po polsku, np. "burze i opady nad Mazowszem".
        k: liczba zwracanych wyników, domyślnie 5.

    Returns:
        Lista wpisów z polami: id, score, source, content, captured_at.
    """
    s = get_settings()
    qvec = embed_text.embed_query(query)
    hits = qdrant_store.search_text(s.qdrant_collection_text, qvec, limit=k)
    return [_hit_to_dict(h) for h in hits]


def find_analog_days(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Znajduje **historycznie podobne dni pogodowe** do opisanej w zapytaniu sytuacji.
    Używaj do **analog forecasting** — gdy chcesz przewidzieć co się stanie po danej
    sytuacji, znajdując podobne przypadki z przeszłości.

    Args:
        query: opis sytuacji, np. "ciepły wieczór, ciśnienie spada, południowy wiatr".
        k: ile podobnych dni zwrócić.

    Returns:
        Lista dni-podsumowań z payloadem zawierającym statystyki dnia (max_t, total_precip itd.).
    """
    s = get_settings()
    qvec = embed_text.embed_query(query)
    from qdrant_client.http import models as qm

    qfilter = qm.Filter(
        must=[qm.FieldCondition(key="source", match=qm.MatchValue(value="auto-summary"))]
    )
    hits = qdrant_store.search_text(s.qdrant_collection_text, qvec, limit=k, qfilter=qfilter)
    return [_hit_to_dict(h) for h in hits]


# --------------------------------------------------------------------------
# Radar — cross-modal text→image i image→image
# --------------------------------------------------------------------------
def search_radar_by_text(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Znajduje klatki radaru pasujące do tekstowego opisu (cross-modal).
    Przykład: "burze nad Polską", "front nadciągający z zachodu".

    Args:
        query: opis tekstowy zjawiska po polsku.
        k: liczba klatek do zwrócenia.

    Returns:
        Lista klatek z URL, captionami i timestamp.
    """
    s = get_settings()
    qvec = embed_mm.embed_text_for_mm(query)
    hits = qdrant_store.search_text(
        s.qdrant_collection_radar, qvec, using=qdrant_store.NAMED_VEC_MM, limit=k
    )
    return [_hit_to_dict(h, with_url=True) for h in hits]


def search_radar_by_image_bytes(image_bytes: bytes, k: int = 5) -> list[dict[str, Any]]:
    """Znajduje klatki radaru wizualnie podobne do podanego obrazu (image-to-image).

    Args:
        image_bytes: surowe bajty obrazu (PNG/JPG).
        k: liczba klatek do zwrócenia.
    """
    s = get_settings()
    qvec = embed_mm.embed_image_for_mm(image_bytes)
    hits = qdrant_store.search_text(
        s.qdrant_collection_radar, qvec, using=qdrant_store.NAMED_VEC_MM, limit=k
    )
    return [_hit_to_dict(h, with_url=True) for h in hits]


# --------------------------------------------------------------------------
# Satellite — cross-modal text→image i image→image
# --------------------------------------------------------------------------
def search_satellite_by_text(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Znajduje obrazy satelitarne pasujące do opisu (cross-modal).
    Przykład: "duże zachmurzenie nad Polską", "widoczne fronty atmosferyczne".

    Args:
        query: opis tekstowy zjawiska.
        k: liczba obrazów.
    """
    s = get_settings()
    qvec = embed_mm.embed_text_for_mm(query)
    hits = qdrant_store.search_text(
        s.qdrant_collection_satellite, qvec, using=qdrant_store.NAMED_VEC_MM, limit=k
    )
    return [_hit_to_dict(h, with_url=True) for h in hits]


def search_satellite_by_image_bytes(image_bytes: bytes, k: int = 5) -> list[dict[str, Any]]:
    """Znajduje obrazy satelitarne wizualnie podobne do podanego (image-to-image).

    Args:
        image_bytes: surowe bajty obrazu.
        k: liczba wyników.
    """
    s = get_settings()
    qvec = embed_mm.embed_image_for_mm(image_bytes)
    hits = qdrant_store.search_text(
        s.qdrant_collection_satellite, qvec, using=qdrant_store.NAMED_VEC_MM, limit=k
    )
    return [_hit_to_dict(h, with_url=True) for h in hits]
