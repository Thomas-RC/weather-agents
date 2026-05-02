"""Smoke test storage layer — pisze i czyta z każdego backendu.

Uruchomienie:
    python -m scripts.smoke_storage

Zakłada że `docker compose up qdrant minio mariadb` jest live.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta, timezone

from PIL import Image

from src.schemas import ImageRecord, SensorReading, TextChunk, WeatherWarning
from src.storage import mariadb_store, minio_store, qdrant_store


def _fake_png(color: tuple[int, int, int] = (200, 50, 50)) -> bytes:
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).replace(tzinfo=None)
    print("=== Qdrant ===")
    qdrant_store.init_collections()
    text_vec = [0.01] * 3072
    mm_vec = [0.02] * 1408
    qdrant_store.upsert_text_chunks(
        [("smoke-text-1", text_vec, {"source": "auto-summary", "modality": "text", "content": "smoke"})]
    )
    qdrant_store.upsert_image_with_named_vectors(
        "radar",
        [(
            "smoke-radar-1",
            text_vec,
            mm_vec,
            {"source": "rainviewer", "modality": "radar", "captured_at": now.isoformat()},
        )],
    )
    text_hits = qdrant_store.search_text("text_chunks", text_vec, limit=1)
    radar_hits = qdrant_store.search_text("radar", text_vec, limit=1)
    radar_mm_hits = qdrant_store.search_text("radar", mm_vec, using="mm_1408", limit=1)
    assert text_hits and text_hits[0].id == "smoke-text-1"
    assert radar_hits and radar_hits[0].id == "smoke-radar-1"
    assert radar_mm_hits and radar_mm_hits[0].id == "smoke-radar-1"
    print(f"  text_chunks search: {text_hits[0].id} score={text_hits[0].score:.3f}")
    print(f"  radar text_3072:    {radar_hits[0].id} score={radar_hits[0].score:.3f}")
    print(f"  radar mm_1408:      {radar_mm_hits[0].id} score={radar_mm_hits[0].score:.3f}")

    print("\n=== MinIO ===")
    minio_store.ensure_bucket()
    key = f"smoke/{now.strftime('%Y%m%dT%H%M%S')}.png"
    minio_store.put_object(key, _fake_png())
    blob = minio_store.get_object(key)
    assert blob.startswith(b"\x89PNG"), "not a PNG"
    url = minio_store.presigned_get_url(key, expires_in=600)
    print(f"  uploaded {key} ({len(blob)} bytes), presigned URL OK")

    print("\n=== MariaDB ===")
    n_sensor = mariadb_store.insert_sensor_readings(
        [
            SensorReading(
                source="imgw",
                external_id=f"smoke-sensor-{now.isoformat()}",
                station_id="0000",
                station_name="SmokeTown",
                measured_at=now,
                temperature_c=20.5,
                pressure_hpa=1013.0,
                humidity_pct=42.0,
                wind_speed_ms=2.5,
                wind_dir_deg=180,
                precipitation_mm=0.0,
            )
        ]
    )
    n_image = mariadb_store.insert_images(
        [
            ImageRecord(
                image_id="smoke-radar-1",
                source="rainviewer",
                modality="radar",
                minio_bucket="weather-rag-raw",
                minio_key=key,
                captured_at=now,
                caption_short="testowa klatka radaru",
            )
        ]
    )
    n_chunk = mariadb_store.insert_text_chunks(
        [
            TextChunk(
                chunk_id="smoke-text-1",
                source="auto-summary",
                content="smoke chunk",
            )
        ]
    )
    n_warn = mariadb_store.insert_warnings(
        [
            WeatherWarning(
                external_id="smoke-warn-1",
                level="2",
                phenomenon="burze",
                area="SmokeProvince",
                valid_from=now,
                valid_to=now + timedelta(hours=6),
                content="testowe ostrzeżenie",
            )
        ]
    )
    mariadb_store.log_fetch(
        source="smoke",
        started_at=now,
        ended_at=now + timedelta(milliseconds=10),
        records_count=4,
        status="ok",
    )
    print(f"  inserted: sensor={n_sensor} image={n_image} chunk={n_chunk} warn={n_warn}")

    latest = mariadb_store.query_latest_sensor_per_station()
    smoke_rows = [r for r in latest if r["station_name"] == "SmokeTown"]
    assert smoke_rows, "SmokeTown not found in latest sensor query"
    print(f"  latest_sensor for SmokeTown: T={smoke_rows[0]['temperature_c']}°C")

    print("\nALL OK ✓")


if __name__ == "__main__":
    sys.exit(main() or 0)
