"""RainViewer — globalne mapy radarowe jako kafelki PNG.

Workflow:
1. Pobierz metadata: GET https://api.rainviewer.com/public/weather-maps.json
   Zwraca host + listy `radar.past[]` i `radar.nowcast[]` z timestampami i ścieżkami.
2. Dla każdej klatki (`past` używamy do archiwum) buduj URL:
   {host}{path}/{size}/{z}/{x}/{y}/{color}/{options}.png
3. Pobierz PNG-i.

Domyślnie pobieramy 1 kafelek pokrywający środek Polski przy zoom=4 (cała Europa
Środkowa) — wystarczy do projektu, łatwo zwiększyć przez parametry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from src.fetchers._util import deterministic_id, lonlat_to_tile, tile_bbox

WEATHER_MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"

# Środek Polski (mniej więcej Łódź)
DEFAULT_LON = 19.45
DEFAULT_LAT = 51.92


@dataclass(slots=True)
class RadarFrameRaw:
    image_id: str
    captured_at: datetime
    zoom: int
    tile_x: int
    tile_y: int
    bbox_north: float
    bbox_south: float
    bbox_east: float
    bbox_west: float
    image_bytes: bytes
    source_url: str
    color_scheme: int
    options_str: str


def fetch_metadata(timeout: float = 10.0) -> dict[str, Any]:
    r = requests.get(WEATHER_MAPS_URL, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_recent_frames(
    *,
    n_frames: int = 6,
    zoom: int = 4,
    lon: float = DEFAULT_LON,
    lat: float = DEFAULT_LAT,
    color_scheme: int = 1,  # 0=Original, 1=Universal Blue, 2=Titan...
    options: str = "1_1",  # smooth=1, snow=1
    tile_size: int = 256,
    timeout: float = 15.0,
    metadata: dict[str, Any] | None = None,
) -> list[RadarFrameRaw]:
    """Pobiera ostatnie n klatek `past` jako PNG-i.

    Każda klatka = 1 kafelek (lon, lat, zoom). Aby pokryć większy obszar wywołaj
    funkcję wielokrotnie z różnymi (lon, lat) lub zwiększ liczbę kafelków
    własnym wrapperem.
    """
    meta = metadata or fetch_metadata(timeout=timeout)
    host = meta["host"]
    past = meta["radar"]["past"]
    if not past:
        return []
    selected = past[-n_frames:]

    tx, ty = lonlat_to_tile(lon, lat, zoom)
    north, south, east, west = tile_bbox(tx, ty, zoom)

    frames: list[RadarFrameRaw] = []
    for entry in selected:
        ts = int(entry["time"])
        path = entry["path"]
        url = f"{host}{path}/{tile_size}/{zoom}/{tx}/{ty}/{color_scheme}/{options}.png"
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
            continue
        captured = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        frames.append(
            RadarFrameRaw(
                image_id=deterministic_id("rainviewer", ts, zoom, tx, ty, color_scheme),
                captured_at=captured,
                zoom=zoom,
                tile_x=tx,
                tile_y=ty,
                bbox_north=north,
                bbox_south=south,
                bbox_east=east,
                bbox_west=west,
                image_bytes=r.content,
                source_url=url,
                color_scheme=color_scheme,
                options_str=options,
            )
        )
    return frames
