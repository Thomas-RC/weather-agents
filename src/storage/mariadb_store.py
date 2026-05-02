"""MariaDB — sensory + metadata (SQLAlchemy Core, surowy SQL)."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from typing import Any, Iterable

from sqlalchemy import Engine, create_engine, text

from src.config import get_settings
from src.schemas import ImageRecord, SensorReading, TextChunk, WeatherWarning


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_settings().mariadb_url, pool_pre_ping=True, future=True)


def _j(v: dict[str, Any] | None) -> str | None:
    return json.dumps(v, ensure_ascii=False, default=str) if v is not None else None


# --------------------------------------------------------------------------
# sensor_readings
# --------------------------------------------------------------------------
_INSERT_SENSOR = text(
    """
    INSERT INTO sensor_readings (
        source, external_id, station_id, station_name, measured_at,
        latitude, longitude, temperature_c, pressure_hpa, wind_speed_ms,
        wind_dir_deg, humidity_pct, precipitation_mm, raw_json
    ) VALUES (
        :source, :external_id, :station_id, :station_name, :measured_at,
        :latitude, :longitude, :temperature_c, :pressure_hpa, :wind_speed_ms,
        :wind_dir_deg, :humidity_pct, :precipitation_mm, :raw_json
    )
    ON DUPLICATE KEY UPDATE
        temperature_c=VALUES(temperature_c),
        pressure_hpa=VALUES(pressure_hpa),
        wind_speed_ms=VALUES(wind_speed_ms),
        wind_dir_deg=VALUES(wind_dir_deg),
        humidity_pct=VALUES(humidity_pct),
        precipitation_mm=VALUES(precipitation_mm),
        raw_json=VALUES(raw_json)
    """
)


def insert_sensor_readings(readings: Iterable[SensorReading]) -> int:
    rows = [
        {**r.model_dump(exclude={"raw"}), "raw_json": _j(r.raw)} for r in readings
    ]
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(_INSERT_SENSOR, rows)
    return len(rows)


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
_INSERT_IMAGE = text(
    """
    INSERT INTO images (
        image_id, source, modality, minio_bucket, minio_key, captured_at,
        bbox_north, bbox_south, bbox_east, bbox_west, zoom, tile_x, tile_y,
        caption_short, caption_long, metadata_json
    ) VALUES (
        :image_id, :source, :modality, :minio_bucket, :minio_key, :captured_at,
        :bbox_north, :bbox_south, :bbox_east, :bbox_west, :zoom, :tile_x, :tile_y,
        :caption_short, :caption_long, :metadata_json
    )
    ON DUPLICATE KEY UPDATE
        caption_short=VALUES(caption_short),
        caption_long=VALUES(caption_long),
        metadata_json=VALUES(metadata_json)
    """
)


def insert_images(images: Iterable[ImageRecord]) -> int:
    rows = [
        {**i.model_dump(exclude={"metadata"}), "metadata_json": _j(i.metadata)}
        for i in images
    ]
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(_INSERT_IMAGE, rows)
    return len(rows)


# --------------------------------------------------------------------------
# text_chunks
# --------------------------------------------------------------------------
_INSERT_CHUNK = text(
    """
    INSERT INTO text_chunks (chunk_id, source, modality, content, valid_from, valid_to, metadata_json)
    VALUES (:chunk_id, :source, 'text', :content, :valid_from, :valid_to, :metadata_json)
    ON DUPLICATE KEY UPDATE
        content=VALUES(content),
        valid_from=VALUES(valid_from),
        valid_to=VALUES(valid_to),
        metadata_json=VALUES(metadata_json)
    """
)


def insert_text_chunks(chunks: Iterable[TextChunk]) -> int:
    rows = [
        {**c.model_dump(exclude={"metadata"}), "metadata_json": _j(c.metadata)}
        for c in chunks
    ]
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(_INSERT_CHUNK, rows)
    return len(rows)


# --------------------------------------------------------------------------
# warnings
# --------------------------------------------------------------------------
_INSERT_WARNING = text(
    """
    INSERT INTO warnings (
        external_id, source, level, phenomenon, area, valid_from, valid_to, content, raw_json
    ) VALUES (
        :external_id, :source, :level, :phenomenon, :area, :valid_from, :valid_to, :content, :raw_json
    )
    ON DUPLICATE KEY UPDATE
        level=VALUES(level),
        phenomenon=VALUES(phenomenon),
        area=VALUES(area),
        valid_from=VALUES(valid_from),
        valid_to=VALUES(valid_to),
        content=VALUES(content),
        raw_json=VALUES(raw_json)
    """
)


def insert_warnings(warnings: Iterable[WeatherWarning]) -> int:
    rows = [
        {**w.model_dump(exclude={"raw"}), "raw_json": _j(w.raw)} for w in warnings
    ]
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(_INSERT_WARNING, rows)
    return len(rows)


# --------------------------------------------------------------------------
# fetch_log
# --------------------------------------------------------------------------
_INSERT_LOG = text(
    """
    INSERT INTO fetch_log (source, started_at, ended_at, duration_ms, records_count, status, error_message)
    VALUES (:source, :started_at, :ended_at, :duration_ms, :records_count, :status, :error_message)
    """
)


def log_fetch(
    *,
    source: str,
    started_at: datetime,
    ended_at: datetime,
    records_count: int | None,
    status: str,
    error_message: str | None = None,
) -> None:
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    with get_engine().begin() as conn:
        conn.execute(
            _INSERT_LOG,
            {
                "source": source,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms,
                "records_count": records_count,
                "status": status,
                "error_message": error_message,
            },
        )


# --------------------------------------------------------------------------
# Queries (do tools agentów)
# --------------------------------------------------------------------------
def query_sensor_timeseries(
    station_name: str,
    variable: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Zwraca [{measured_at, value}, ...] dla danej stacji i zmiennej."""
    allowed = {
        "temperature_c",
        "pressure_hpa",
        "wind_speed_ms",
        "humidity_pct",
        "precipitation_mm",
    }
    if variable not in allowed:
        raise ValueError(f"variable must be one of {allowed}")
    sql = text(
        f"""SELECT measured_at, {variable} AS value
            FROM sensor_readings
            WHERE station_name = :station AND measured_at BETWEEN :start AND :end
            ORDER BY measured_at"""
    )
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"station": station_name, "start": start, "end": end})]


def query_latest_sensor_per_station() -> list[dict[str, Any]]:
    """Najświeższy odczyt per stacja (do widoku live)."""
    sql = text(
        """
        SELECT s.* FROM sensor_readings s
        JOIN (
            SELECT station_name, MAX(measured_at) AS max_t
            FROM sensor_readings
            GROUP BY station_name
        ) m ON s.station_name = m.station_name AND s.measured_at = m.max_t
        """
    )
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql)]
