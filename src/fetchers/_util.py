"""Wspólne narzędzia dla fetcherów."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime


def deterministic_id(*parts: str | int | float | None) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Web Mercator: konwersja (lon, lat, zoom) -> (tile_x, tile_y)."""
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_bbox(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Zwraca (north, south, east, west) granice kafelka Web Mercator."""
    n = 2.0**zoom

    def _lon(xt: int) -> float:
        return xt / n * 360.0 - 180.0

    def _lat(yt: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))

    west = _lon(x)
    east = _lon(x + 1)
    north = _lat(y)
    south = _lat(y + 1)
    return north, south, east, west


def parse_imgw_datetime(date_str: str, hour_str: str | int) -> datetime:
    """IMGW podaje 'YYYY-MM-DD' + godzinę 0-23. Zwracamy naive UTC."""
    hour = int(hour_str)
    return datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour)


def parse_float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_int(v: object) -> int | None:
    f = parse_float(v)
    return int(f) if f is not None else None
