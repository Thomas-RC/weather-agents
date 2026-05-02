"""Backfill archiwalny — historyczne dane do analog forecasting.

Pobiera:
1. **Open-Meteo archive**: 60 dni (do 7 dni wstecz), 8 miast PL — sensors
2. **NASA GIBS**: 30 dni (Terra TrueColor) — satelita
3. **Daily summaries**: dla każdej (dzień, miasto) generuje opis ze statystyk
   sensor_readings i wrzuca jako text_chunk z embeddingiem (do analog search)

Uruchomienie:
    docker compose run --rm worker python -m scripts.backfill_archive
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from src.config import get_settings
from src.fetchers import nasa_gibs, openmeteo
from src.fetchers._util import deterministic_id
from src.observability.logging import configure_logging, get_logger
from src.pipeline import upsert
from src.schemas import ImageRecord, TextChunk
from src.storage import mariadb_store
from src.storage.minio_store import ensure_bucket
from src.storage.qdrant_store import init_collections

CITIES = openmeteo.DEFAULT_CITIES  # 8 miast PL


def step1_openmeteo_archive(days_back: int = 60, end_offset: int = 7) -> int:
    """60 dni archiwum, kończąc 7 dni temu (Open-Meteo ma kilkudniowe opóźnienie)."""
    log = get_logger("backfill.openmeteo")
    end = date.today() - timedelta(days=end_offset)
    start = end - timedelta(days=days_back)
    log.info("openmeteo.fetch_archive", start=start.isoformat(), end=end.isoformat())
    readings = openmeteo.fetch_archive(start.isoformat(), end.isoformat())
    n = mariadb_store.insert_sensor_readings(readings)
    log.info("openmeteo.inserted", n=n)
    return n


def step2_nasa_gibs(days_back: int = 30) -> int:
    """30 dni × 1 layer (MODIS Terra) — captioning + embedding każdej klatki."""
    log = get_logger("backfill.nasa_gibs")
    s = get_settings()
    n_processed = 0
    for d in range(1, days_back + 1):
        target = date.today() - timedelta(days=d)
        frame = nasa_gibs.fetch_tile(
            layer="MODIS_Terra_CorrectedReflectance_TrueColor",
            target_date=target,
            zoom=4,
        )
        if frame is None:
            log.info("nasa_gibs.skip", date=target.isoformat(), reason="no_tile")
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
            metadata={"layer": frame.layer, "provider": "nasa-gibs", "backfill": True},
        )
        added = upsert.process_image(record, frame.image_bytes, mime="image/jpeg")
        if added:
            n_processed += 1
            log.info("nasa_gibs.added", date=target.isoformat())
        else:
            log.info("nasa_gibs.exists", date=target.isoformat())
    return n_processed


_DAILY_AGGREGATE_SQL = text(
    """
    SELECT station_name,
           DATE(measured_at) AS day,
           AVG(temperature_c) AS avg_t,
           MIN(temperature_c) AS min_t,
           MAX(temperature_c) AS max_t,
           SUM(precipitation_mm) AS total_precip,
           AVG(pressure_hpa) AS avg_press,
           MAX(wind_speed_ms) AS max_wind,
           AVG(humidity_pct) AS avg_humid
    FROM sensor_readings
    WHERE source='open-meteo'
      AND measured_at BETWEEN :start AND :end
    GROUP BY station_name, DATE(measured_at)
    ORDER BY day, station_name
    """
)


def step3_daily_summaries(days_back: int = 60, end_offset: int = 7) -> int:
    """Per (miasto, dzień) generuje krótki tekst statystyczny i osadza go jako
    chunk w Qdrant. Te chunki służą do analog forecasting — agent szuka podobnych
    sytuacji historycznych po podobieństwie semantycznym."""
    log = get_logger("backfill.summaries")
    end = datetime.combine(date.today() - timedelta(days=end_offset), datetime.min.time())
    start = end - timedelta(days=days_back)

    with mariadb_store.get_engine().connect() as conn:
        rows = list(conn.execute(_DAILY_AGGREGATE_SQL, {"start": start, "end": end}).mappings())

    log.info("summaries.aggregated", rows=len(rows))
    n_chunks = 0
    for r in rows:
        chunk = _row_to_chunk(r)
        n_chunks += upsert.process_text_chunk(chunk)
    log.info("summaries.embedded", new=n_chunks)
    return n_chunks


def _row_to_chunk(r: Any) -> TextChunk:
    day = r["day"]
    city = r["station_name"]
    parts = [f"Pogoda w {city}, {day}:"]
    if r["avg_t"] is not None:
        parts.append(
            f"temperatura średnio {r['avg_t']:.1f}°C "
            f"(min {r['min_t']:.1f}°C, max {r['max_t']:.1f}°C)"
        )
    if r["total_precip"] is not None:
        if r["total_precip"] > 0.5:
            parts.append(f"opady łącznie {r['total_precip']:.1f} mm")
        else:
            parts.append("brak opadów")
    if r["avg_press"] is not None:
        parts.append(f"ciśnienie średnio {r['avg_press']:.0f} hPa")
    if r["max_wind"] is not None:
        parts.append(f"max wiatr {r['max_wind']:.1f} m/s")
    if r["avg_humid"] is not None:
        parts.append(f"wilgotność średnio {r['avg_humid']:.0f}%")
    content = ". ".join(parts) + "."

    chunk_id = deterministic_id("daily-summary", city, day.isoformat())
    return TextChunk(
        chunk_id=chunk_id,
        source="auto-summary",
        content=content,
        valid_from=datetime.combine(day, datetime.min.time()),
        valid_to=datetime.combine(day, datetime.max.time().replace(microsecond=0)),
        metadata={
            "kind": "daily-summary",
            "city": city,
            "day": day.isoformat(),
            "max_t": float(r["max_t"]) if r["max_t"] is not None else None,
            "min_t": float(r["min_t"]) if r["min_t"] is not None else None,
            "total_precip": float(r["total_precip"]) if r["total_precip"] is not None else None,
            "max_wind": float(r["max_wind"]) if r["max_wind"] is not None else None,
        },
    )


def main() -> None:
    s = get_settings()
    configure_logging(s.app_log_level)
    log = get_logger("backfill.archive")
    log.info("backfill.start")

    init_collections()
    ensure_bucket()

    n_sensors = step1_openmeteo_archive(days_back=60, end_offset=7)
    n_satellite = step2_nasa_gibs(days_back=30)
    n_summaries = step3_daily_summaries(days_back=60, end_offset=7)

    log.info(
        "backfill.done",
        openmeteo_archive=n_sensors,
        nasa_gibs=n_satellite,
        daily_summaries=n_summaries,
    )


if __name__ == "__main__":
    main()
