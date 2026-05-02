"""Handlery — co robić gdy odpali się dany cron.

Każdy handler:
- pobiera dane z API
- zapisuje do MariaDB / MinIO / Qdrant
- loguje wynik do tabeli `fetch_log` (audyt)
- jest idempotentny (deterministyczne ID + ON DUPLICATE KEY UPDATE)
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.config import get_settings
from src.fetchers import imgw, nasa_gibs, openmeteo, rainviewer
from src.observability.logging import get_logger
from src.pipeline import upsert
from src.schemas import ImageRecord, TextChunk
from src.storage import mariadb_store

log = get_logger("worker.handlers")


def _safe(source: str, fn: Callable[[], int | None]) -> None:
    """Wrapper logujący start/end + zapisujący do fetch_log."""
    started = datetime.utcnow()
    log.info("handler.start", source=source)
    try:
        n = fn() or 0
        ended = datetime.utcnow()
        mariadb_store.log_fetch(
            source=source, started_at=started, ended_at=ended,
            records_count=n, status="ok",
        )
        log.info("handler.ok", source=source, records=n,
                 duration_ms=int((ended - started).total_seconds() * 1000))
    except Exception as e:
        ended = datetime.utcnow()
        mariadb_store.log_fetch(
            source=source, started_at=started, ended_at=ended,
            records_count=None, status="error", error_message=str(e)[:1000],
        )
        log.exception("handler.error", source=source, error=str(e))


# --------------------------------------------------------------------------
# Sensors (no embedding — sensor data jest tabelaryczne, query po SQL)
# --------------------------------------------------------------------------
def handle_imgw_synop() -> None:
    def _do() -> int:
        readings = imgw.fetch_synop()
        return mariadb_store.insert_sensor_readings(readings)

    _safe("imgw-synop", _do)


def handle_openmeteo_forecast(forecast_days: int = 7) -> None:
    def _do() -> int:
        readings = openmeteo.fetch_forecast(forecast_days=forecast_days)
        return mariadb_store.insert_sensor_readings(readings)

    _safe("open-meteo", _do)


# --------------------------------------------------------------------------
# Warnings (text → embedded chunks)
# --------------------------------------------------------------------------
def handle_imgw_warnings() -> None:
    def _do() -> int:
        warns = imgw.fetch_warnings()
        if not warns:
            return 0
        n_warn = mariadb_store.insert_warnings(warns)

        # zamień na chunki tekstowe + embeduj + Qdrant
        n_chunks = 0
        for w in warns:
            content_parts = [
                w.phenomenon or "Ostrzeżenie meteorologiczne",
                f"stopień {w.level}" if w.level else None,
                f"obszar: {w.area}" if w.area else None,
                w.content or "",
            ]
            content = ". ".join(p for p in content_parts if p).strip()
            if not content:
                continue
            chunk = TextChunk(
                chunk_id=w.external_id,  # już jest 32-char hex, pasuje jako UUID
                source="imgw-warnings",
                content=content,
                valid_from=w.valid_from,
                valid_to=w.valid_to,
                metadata={
                    "level": w.level,
                    "phenomenon": w.phenomenon,
                    "area": w.area,
                },
            )
            n_chunks += upsert.process_text_chunk(chunk)
        log.info("warnings.processed", in_db=n_warn, new_chunks=n_chunks)
        return n_warn

    _safe("imgw-warnings", _do)


# --------------------------------------------------------------------------
# Radar (RainViewer → MinIO + Qdrant)
# --------------------------------------------------------------------------
def handle_radar(*, n_frames: int = 2, zoom: int = 4) -> None:
    def _do() -> int:
        s = get_settings()
        frames = rainviewer.fetch_recent_frames(n_frames=n_frames, zoom=zoom)
        n = 0
        for f in frames:
            record = ImageRecord(
                image_id=f.image_id,
                source="rainviewer",
                modality="radar",
                minio_bucket=s.minio_bucket,
                minio_key=f"radar/{f.captured_at:%Y%m%d}/{f.image_id}.png",
                captured_at=f.captured_at,
                bbox_north=f.bbox_north,
                bbox_south=f.bbox_south,
                bbox_east=f.bbox_east,
                bbox_west=f.bbox_west,
                zoom=f.zoom,
                tile_x=f.tile_x,
                tile_y=f.tile_y,
                metadata={
                    "color_scheme": f.color_scheme,
                    "options": f.options_str,
                    "source_url": f.source_url,
                },
            )
            n += upsert.process_image(record, f.image_bytes, mime="image/png")
        return n

    _safe("rainviewer", _do)


# --------------------------------------------------------------------------
# Satellite (NASA GIBS → MinIO + Qdrant)
# --------------------------------------------------------------------------
SATELLITE_LAYERS: list[nasa_gibs.Layer] = [
    "MODIS_Terra_CorrectedReflectance_TrueColor",
    "VIIRS_SNPP_CorrectedReflectance_TrueColor",
]


def handle_satellite(*, zoom: int = 4) -> None:
    def _do() -> int:
        s = get_settings()
        n = 0
        for layer in SATELLITE_LAYERS:
            frame = nasa_gibs.fetch_tile(layer=layer, zoom=zoom)
            if frame is None:
                continue
            record = ImageRecord(
                image_id=frame.image_id,
                source="nasa-gibs",
                modality="satellite",
                minio_bucket=s.minio_bucket,
                minio_key=f"satellite/{frame.captured_at:%Y%m%d}/{frame.image_id}.jpg",
                captured_at=frame.captured_at,
                bbox_north=frame.bbox_north,
                bbox_south=frame.bbox_south,
                bbox_east=frame.bbox_east,
                bbox_west=frame.bbox_west,
                zoom=frame.zoom,
                tile_x=frame.tile_x,
                tile_y=frame.tile_y,
                metadata={"layer": frame.layer, "source_url": frame.source_url, "provider": "nasa-gibs"},
            )
            n += upsert.process_image(record, frame.image_bytes, mime="image/jpeg")
        return n

    _safe("nasa-gibs", _do)
