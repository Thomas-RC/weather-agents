"""Orkiestracja per rekord: caption → embed → MinIO + MariaDB + Qdrant.

Idempotencja: przed całym ciężarem (caption + embeddingi = $$) sprawdzamy
czy rekord już istnieje w MariaDB. Jeśli tak — pomijamy.
"""

from __future__ import annotations

from sqlalchemy import text

from src.config import get_settings
from src.pipeline import caption, embed_mm, embed_text
from src.schemas import ImageRecord, TextChunk
from src.storage import mariadb_store, minio_store, qdrant_store


def _image_exists(image_id: str) -> bool:
    sql = text("SELECT 1 FROM images WHERE image_id = :id LIMIT 1")
    with mariadb_store.get_engine().connect() as conn:
        return conn.execute(sql, {"id": image_id}).first() is not None


def _chunk_exists(chunk_id: str) -> bool:
    sql = text("SELECT 1 FROM text_chunks WHERE chunk_id = :id LIMIT 1")
    with mariadb_store.get_engine().connect() as conn:
        return conn.execute(sql, {"id": chunk_id}).first() is not None


def process_image(record: ImageRecord, image_bytes: bytes, *, mime: str = "image/png") -> int:
    """Pełna ścieżka dla jednej klatki radaru/satelity.

    Zwraca 1 jeśli przetworzono, 0 jeśli pominięto (już istniała).
    """
    if _image_exists(record.image_id):
        return 0

    s = get_settings()
    target_collection = (
        s.qdrant_collection_radar
        if record.modality == "radar"
        else s.qdrant_collection_satellite
    )

    # 1. MinIO — surowy plik
    minio_store.put_object(record.minio_key, image_bytes, content_type=mime)

    # 2. Captioning (Gemini 2.5 Flash)
    caps = caption.caption_image(image_bytes, mime_type=mime)
    record.caption_short = caps["short"]
    record.caption_long = caps["long"]

    # 3. Embeddingi
    text_for_embed = caps["long"] or caps["short"] or "weather map"
    text_vec = embed_text.embed_documents([text_for_embed])[0]
    mm_vec = embed_mm.embed_image_with_caption(image_bytes, caps["short"] or "weather map")

    # 4. MariaDB — metadata
    mariadb_store.insert_images([record])

    # 5. Qdrant — wektory + payload
    payload = {
        "source": record.source,
        "modality": record.modality,
        "captured_at": record.captured_at.isoformat(),
        "minio_bucket": record.minio_bucket,
        "minio_key": record.minio_key,
        "caption_short": caps["short"],
        "caption_long": caps["long"],
        "bbox_north": record.bbox_north,
        "bbox_south": record.bbox_south,
        "bbox_east": record.bbox_east,
        "bbox_west": record.bbox_west,
        "zoom": record.zoom,
    }
    qdrant_store.upsert_image_with_named_vectors(
        collection=target_collection,
        points=[(record.image_id, text_vec, mm_vec, payload)],
    )
    return 1


def process_text_chunk(chunk: TextChunk) -> int:
    """Pełna ścieżka dla chunka tekstu (ostrzeżenie / auto-summary).

    Zwraca 1 jeśli przetworzono, 0 jeśli pominięto.
    """
    if _chunk_exists(chunk.chunk_id):
        return 0

    s = get_settings()
    text_vec = embed_text.embed_documents([chunk.content])[0]
    mariadb_store.insert_text_chunks([chunk])
    payload = {
        "source": chunk.source,
        "modality": "text",
        "content": chunk.content,
        "valid_from": chunk.valid_from.isoformat() if chunk.valid_from else None,
        "valid_to": chunk.valid_to.isoformat() if chunk.valid_to else None,
    }
    if chunk.metadata:
        payload.update(chunk.metadata)
    qdrant_store.upsert_text_chunks(
        [(chunk.chunk_id, text_vec, payload)],
    )
    return 1
