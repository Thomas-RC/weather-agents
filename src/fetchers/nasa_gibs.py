"""NASA GIBS — prawdziwa satelita (MODIS / VIIRS) jako kafelki WMTS.

Zalety vs OWM:
- bez klucza, bez rejestracji, darmowe
- prawdziwe obrazy satelitarne (true color), nie nakładka modelu pogody
- archiwum kilkanaście lat wstecz (dla MODIS od 2000)

URL pattern (EPSG:3857, czyli Web Mercator jak Google Maps):
    https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/
        {LAYER}/default/{DATE}/{TILEMATRIXSET}/{Z}/{Y}/{X}.{FORMAT}

UWAGA: GIBS używa kolejności {Z}/{Y}/{X} (Y przed X), nie XYZ.
Wybrane warstwy true color (codziennie, jeden snapshot z przelotu):
- MODIS_Terra_CorrectedReflectance_TrueColor   (Terra, ~10:30 local time)
- MODIS_Aqua_CorrectedReflectance_TrueColor    (Aqua,  ~13:30 local time)
- VIIRS_SNPP_CorrectedReflectance_TrueColor    (Suomi NPP, świeże)
- VIIRS_NOAA20_CorrectedReflectance_TrueColor  (NOAA-20)

TileMatrixSet dla EPSG:3857: GoogleMapsCompatible_Level9 (lub _Level6/_Level8)
Format: jpg (true color) lub png.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import requests

from src.fetchers._util import deterministic_id, lonlat_to_tile, tile_bbox

GIBS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"

Layer = Literal[
    "MODIS_Terra_CorrectedReflectance_TrueColor",
    "MODIS_Aqua_CorrectedReflectance_TrueColor",
    "VIIRS_SNPP_CorrectedReflectance_TrueColor",
    "VIIRS_NOAA20_CorrectedReflectance_TrueColor",
]

DEFAULT_LON = 19.45
DEFAULT_LAT = 51.92


@dataclass(slots=True)
class SatelliteFrameRaw:
    image_id: str
    captured_at: datetime  # data przelotu satelity (00:00 UTC danego dnia)
    layer: str
    zoom: int
    tile_x: int
    tile_y: int
    bbox_north: float
    bbox_south: float
    bbox_east: float
    bbox_west: float
    image_bytes: bytes
    source_url: str


def fetch_tile(
    *,
    layer: Layer = "MODIS_Terra_CorrectedReflectance_TrueColor",
    target_date: date | None = None,
    zoom: int = 4,
    lon: float = DEFAULT_LON,
    lat: float = DEFAULT_LAT,
    tilematrixset: str = "GoogleMapsCompatible_Level9",
    image_format: str = "jpg",
    timeout: float = 20.0,
) -> SatelliteFrameRaw | None:
    """Pobiera jeden kafelek satelity dla podanej daty (domyślnie wczoraj — Terra
    publikuje obrazy z opóźnieniem ~3-6h; dziś po 12 UTC zwykle jest dostępne)."""
    d = target_date or _yesterday_utc()
    tx, ty = lonlat_to_tile(lon, lat, zoom)
    north, south, east, west = tile_bbox(tx, ty, zoom)
    url = (
        f"{GIBS_BASE}/{layer}/default/{d.isoformat()}/{tilematrixset}"
        f"/{zoom}/{ty}/{tx}.{image_format}"
    )
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    if not (r.content.startswith(b"\xff\xd8") or r.content.startswith(b"\x89PNG")):
        return None
    captured = datetime(d.year, d.month, d.day, tzinfo=None)
    return SatelliteFrameRaw(
        image_id=deterministic_id("nasa-gibs", layer, d.isoformat(), zoom, tx, ty),
        captured_at=captured,
        layer=layer,
        zoom=zoom,
        tile_x=tx,
        tile_y=ty,
        bbox_north=north,
        bbox_south=south,
        bbox_east=east,
        bbox_west=west,
        image_bytes=r.content,
        source_url=url,
    )


def _yesterday_utc() -> date:
    """Wczorajsza data UTC — bezpieczny default, dane satelity zwykle gotowe."""
    return datetime.now(timezone.utc).date() - timedelta(days=1)
