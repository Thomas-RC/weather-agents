"""End-to-end smoke test pipeline'a — wymaga LIVE Vertex AI.

Pobiera 1 klatkę radaru, captionuje, embeduje, upsertuje do wszystkich storów,
a potem weryfikuje retrieval.

Uruchomienie:
    python -m scripts.smoke_pipeline
"""

from __future__ import annotations

from src.config import get_settings
from src.fetchers import rainviewer
from src.observability.logging import configure_logging, get_logger
from src.pipeline import embed_text, upsert
from src.schemas import ImageRecord
from src.storage import qdrant_store
from src.storage.minio_store import ensure_bucket
from src.storage.qdrant_store import init_collections


def main() -> None:
    s = get_settings()
    configure_logging("INFO")
    log = get_logger("smoke_pipeline")

    log.info("infrastructure.init")
    init_collections()
    ensure_bucket()

    log.info("rainviewer.fetch_one")
    frames = rainviewer.fetch_recent_frames(n_frames=1, zoom=4)
    if not frames:
        log.error("rainviewer.no_frames")
        return
    f = frames[0]

    record = ImageRecord(
        image_id=f.image_id,
        source="rainviewer",
        modality="radar",
        minio_bucket=s.minio_bucket,
        minio_key=f"radar/smoke/{f.image_id}.png",
        captured_at=f.captured_at,
        bbox_north=f.bbox_north,
        bbox_south=f.bbox_south,
        bbox_east=f.bbox_east,
        bbox_west=f.bbox_west,
        zoom=f.zoom,
        tile_x=f.tile_x,
        tile_y=f.tile_y,
    )
    log.info("pipeline.process_image", id=record.image_id, captured_at=record.captured_at)
    n = upsert.process_image(record, f.image_bytes, mime="image/png")
    log.info("pipeline.processed", new_records=n)

    # Retrieval — embed query, szukaj w Qdrant
    query = "burze i opady deszczu nad Polską"
    log.info("retrieval.embed_query", q=query)
    qvec = embed_text.embed_query(query)
    hits = qdrant_store.search_text(s.qdrant_collection_radar, qvec, limit=3)
    log.info("retrieval.results", count=len(hits))
    for h in hits:
        cap = (h.payload.get("caption_short") or "")[:80]
        log.info("retrieval.hit", id=h.id, score=round(h.score, 3), caption=cap)


if __name__ == "__main__":
    main()
