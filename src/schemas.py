"""Pydantic modele danych — wspólne dla fetcherów, pipeline, agentów."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Modality = Literal["sensor", "radar", "satellite", "text"]
Source = Literal[
    "imgw", "imgw-warnings", "open-meteo", "rainviewer", "owm-satellite", "auto-summary"
]


class SensorReading(BaseModel):
    """Pojedynczy odczyt ze stacji synoptycznej."""

    model_config = ConfigDict(extra="forbid")

    source: Source
    external_id: str  # deterministyczny hash (source + station + timestamp)
    station_id: str | None = None
    station_name: str | None = None
    measured_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    temperature_c: float | None = None
    pressure_hpa: float | None = None
    wind_speed_ms: float | None = None
    wind_dir_deg: int | None = None
    humidity_pct: float | None = None
    precipitation_mm: float | None = None
    raw: dict[str, Any] | None = None


class ImageRecord(BaseModel):
    """Klatka radaru lub satelity. Bytes są oddzielnie (do MinIO)."""

    model_config = ConfigDict(extra="forbid")

    image_id: str  # deterministyczny, używany jako Qdrant point id
    source: Source
    modality: Modality  # 'radar' | 'satellite'
    minio_bucket: str
    minio_key: str
    captured_at: datetime
    bbox_north: float | None = None
    bbox_south: float | None = None
    bbox_east: float | None = None
    bbox_west: float | None = None
    zoom: int | None = None
    tile_x: int | None = None
    tile_y: int | None = None
    caption_short: str | None = None  # ≤ 25 słów (multimodalembedding limit)
    caption_long: str | None = None  # do prezentacji UI
    metadata: dict[str, Any] | None = None


class TextChunk(BaseModel):
    """Chunk tekstu do indeksu wektorowego."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source: Source
    content: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] | None = None


class WeatherWarning(BaseModel):
    """Ostrzeżenie meteo (IMGW)."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    source: Source = "imgw-warnings"
    level: str | None = None  # '1' | '2' | '3'
    phenomenon: str | None = None
    area: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    content: str | None = None
    raw: dict[str, Any] | None = None


class RetrievalResult(BaseModel):
    """Wynik wyszukiwania zwracany przez tools agentów."""

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float
    modality: Modality
    source: Source
    payload: dict[str, Any] = Field(default_factory=dict)
