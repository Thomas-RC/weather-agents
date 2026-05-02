"""Open-Meteo — prognoza godzinowa dla wybranych miast."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import requests

from src.fetchers._util import deterministic_id
from src.schemas import SensorReading

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Domyślne miasta (lat, lon) dla MVP
DEFAULT_CITIES: dict[str, tuple[float, float]] = {
    "Warszawa": (52.23, 21.01),
    "Kraków": (50.06, 19.94),
    "Gdańsk": (54.36, 18.65),
    "Wrocław": (51.11, 17.04),
    "Poznań": (52.41, 16.93),
    "Łódź": (51.76, 19.46),
    "Białystok": (53.13, 23.16),
    "Szczecin": (53.43, 14.55),
}


def fetch_forecast(
    cities: Iterable[tuple[str, float, float]] | None = None,
    forecast_days: int = 1,
    timeout: float = 15.0,
) -> list[SensorReading]:
    """Pobiera godzinową prognozę temperatury/wiatru/opadów/ciśnienia/wilgotności
    dla wybranych miast. Zwracane jako SensorReading (source='open-meteo')."""
    items = list(cities) if cities else [(n, lat, lon) for n, (lat, lon) in DEFAULT_CITIES.items()]

    out: list[SensorReading] = []
    for name, lat, lon in items:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "precipitation",
                    "pressure_msl",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        r = requests.get(FORECAST_URL, params=params, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        h = d.get("hourly", {})
        times = h.get("time", [])
        for i, t in enumerate(times):
            measured_at = datetime.fromisoformat(t)
            out.append(
                SensorReading(
                    source="open-meteo",
                    external_id=deterministic_id("open-meteo", name, t),
                    station_name=name,
                    measured_at=measured_at,
                    latitude=lat,
                    longitude=lon,
                    temperature_c=_get(h, "temperature_2m", i),
                    pressure_hpa=_get(h, "pressure_msl", i),
                    wind_speed_ms=_get(h, "wind_speed_10m", i),
                    wind_dir_deg=_get_int(h, "wind_direction_10m", i),
                    humidity_pct=_get(h, "relative_humidity_2m", i),
                    precipitation_mm=_get(h, "precipitation", i),
                )
            )
    return out


def fetch_archive(
    start_date: str,
    end_date: str,
    cities: Iterable[tuple[str, float, float]] | None = None,
    timeout: float = 30.0,
) -> list[SensorReading]:
    """Pobiera ARCHIWALNE odczyty (reanaliza ERA5/historical) z Open-Meteo.

    Format dat: YYYY-MM-DD. Archiwum sięga 1940 roku.
    """
    items = list(cities) if cities else [(n, lat, lon) for n, (lat, lon) in DEFAULT_CITIES.items()]
    out: list[SensorReading] = []
    for name, lat, lon in items:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "precipitation",
                    "pressure_msl",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "timezone": "UTC",
        }
        r = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        h = d.get("hourly", {})
        times = h.get("time", [])
        for i, t in enumerate(times):
            measured_at = datetime.fromisoformat(t)
            out.append(
                SensorReading(
                    source="open-meteo",
                    external_id=deterministic_id("open-meteo-archive", name, t),
                    station_name=name,
                    measured_at=measured_at,
                    latitude=lat,
                    longitude=lon,
                    temperature_c=_get(h, "temperature_2m", i),
                    pressure_hpa=_get(h, "pressure_msl", i),
                    wind_speed_ms=_get(h, "wind_speed_10m", i),
                    wind_dir_deg=_get_int(h, "wind_direction_10m", i),
                    humidity_pct=_get(h, "relative_humidity_2m", i),
                    precipitation_mm=_get(h, "precipitation", i),
                )
            )
    return out


def _get(h: dict, key: str, i: int) -> float | None:
    arr = h.get(key)
    if not arr or i >= len(arr) or arr[i] is None:
        return None
    return float(arr[i])


def _get_int(h: dict, key: str, i: int) -> int | None:
    v = _get(h, key, i)
    return int(v) if v is not None else None
