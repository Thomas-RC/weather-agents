"""Qdrant — wektorowa baza z named vectors (text_3072 + mm_1408)."""

from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.config import get_settings
from src.schemas import RetrievalResult

NAMED_VEC_TEXT = "text_3072"
NAMED_VEC_MM = "mm_1408"


def get_client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url)


def _text_only_vectors_config(dim: int) -> dict[str, qm.VectorParams]:
    return {
        NAMED_VEC_TEXT: qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    }


def _multimodal_vectors_config(text_dim: int, mm_dim: int) -> dict[str, qm.VectorParams]:
    return {
        NAMED_VEC_TEXT: qm.VectorParams(size=text_dim, distance=qm.Distance.COSINE),
        NAMED_VEC_MM: qm.VectorParams(size=mm_dim, distance=qm.Distance.COSINE),
    }


def init_collections(client: QdrantClient | None = None) -> None:
    """Idempotentnie tworzy 3 kolekcje: text_chunks (1×3072), radar i satellite (2 named)."""
    s = get_settings()
    c = client or get_client()

    existing = {col.name for col in c.get_collections().collections}

    # text_chunks — tylko text_3072
    if s.qdrant_collection_text not in existing:
        c.create_collection(
            collection_name=s.qdrant_collection_text,
            vectors_config=_text_only_vectors_config(s.text_embedding_dim),
        )

    # radar — text_3072 + mm_1408
    if s.qdrant_collection_radar not in existing:
        c.create_collection(
            collection_name=s.qdrant_collection_radar,
            vectors_config=_multimodal_vectors_config(s.text_embedding_dim, s.mm_embedding_dim),
        )

    # satellite — text_3072 + mm_1408
    if s.qdrant_collection_satellite not in existing:
        c.create_collection(
            collection_name=s.qdrant_collection_satellite,
            vectors_config=_multimodal_vectors_config(s.text_embedding_dim, s.mm_embedding_dim),
        )


def upsert_text_chunks(
    points: list[tuple[str, list[float], dict[str, Any]]],
    client: QdrantClient | None = None,
) -> None:
    """Upsert do kolekcji text_chunks. points = [(id, text_embedding, payload), ...]."""
    if not points:
        return
    s = get_settings()
    c = client or get_client()
    c.upsert(
        collection_name=s.qdrant_collection_text,
        points=[
            qm.PointStruct(id=pid, vector={NAMED_VEC_TEXT: vec}, payload=payload)
            for pid, vec, payload in points
        ],
    )


def upsert_image_with_named_vectors(
    collection: str,
    points: list[tuple[str, list[float], list[float], dict[str, Any]]],
    client: QdrantClient | None = None,
) -> None:
    """Upsert do kolekcji radar/satellite z 2 wektorami per punkt.

    points = [(id, text_3072_vec, mm_1408_vec, payload), ...]
    """
    if not points:
        return
    c = client or get_client()
    c.upsert(
        collection_name=collection,
        points=[
            qm.PointStruct(
                id=pid,
                vector={NAMED_VEC_TEXT: text_vec, NAMED_VEC_MM: mm_vec},
                payload=payload,
            )
            for pid, text_vec, mm_vec, payload in points
        ],
    )


def search_text(
    collection: str,
    query_vec: list[float],
    *,
    using: str = NAMED_VEC_TEXT,
    limit: int = 5,
    qfilter: qm.Filter | None = None,
    client: QdrantClient | None = None,
) -> list[RetrievalResult]:
    """Wyszukiwanie po wybranym named vector. `using` = NAMED_VEC_TEXT albo NAMED_VEC_MM."""
    c = client or get_client()
    hits = c.query_points(
        collection_name=collection,
        query=query_vec,
        using=using,
        limit=limit,
        query_filter=qfilter,
        with_payload=True,
    ).points

    results: list[RetrievalResult] = []
    for h in hits:
        payload = h.payload or {}
        results.append(
            RetrievalResult(
                id=str(h.id),
                score=float(h.score) if h.score is not None else 0.0,
                modality=payload.get("modality", "text"),
                source=payload.get("source", "auto-summary"),
                payload=payload,
            )
        )
    return results
