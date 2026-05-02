"""IMGW publiczne API: synop + ostrzeżenia meteorologiczne."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from src.fetchers._util import (
    deterministic_id,
    parse_float,
    parse_imgw_datetime,
    parse_int,
)
from src.schemas import SensorReading, WeatherWarning

SYNOP_URL = "https://danepubliczne.imgw.pl/api/data/synop"
WARNINGS_URL = "https://danepubliczne.imgw.pl/api/data/warningsmeteo"


def fetch_synop(timeout: float = 10.0) -> list[SensorReading]:
    r = requests.get(SYNOP_URL, timeout=timeout)
    r.raise_for_status()
    return [_parse_synop_row(row) for row in r.json()]


def _parse_synop_row(row: dict[str, Any]) -> SensorReading:
    measured_at = parse_imgw_datetime(row["data_pomiaru"], row["godzina_pomiaru"])
    station_id = str(row.get("id_stacji", "")) or None
    return SensorReading(
        source="imgw",
        external_id=deterministic_id("imgw-synop", station_id, measured_at.isoformat()),
        station_id=station_id,
        station_name=row.get("stacja"),
        measured_at=measured_at,
        temperature_c=parse_float(row.get("temperatura")),
        pressure_hpa=parse_float(row.get("cisnienie")),
        wind_speed_ms=parse_float(row.get("predkosc_wiatru")),
        wind_dir_deg=parse_int(row.get("kierunek_wiatru")),
        humidity_pct=parse_float(row.get("wilgotnosc_wzgledna")),
        precipitation_mm=parse_float(row.get("suma_opadu")),
        raw=row,
    )


def fetch_warnings(timeout: float = 10.0) -> list[WeatherWarning]:
    r = requests.get(WARNINGS_URL, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict):
        # IMGW okazjonalnie wraca obiekt {"meteo": [...]} lub podobny
        items = payload.get("meteo") or payload.get("warnings") or []
    else:
        items = payload
    return [_parse_warning(row) for row in items]


def _parse_warning(row: dict[str, Any]) -> WeatherWarning:
    valid_from = _maybe_dt(row.get("obowiazuje_od") or row.get("ważne_od"))
    valid_to = _maybe_dt(row.get("obowiazuje_do") or row.get("ważne_do"))
    area = _stringify(row.get("obszar") or row.get("teryt"))
    eid = deterministic_id(
        "imgw-warn",
        area,
        row.get("zjawisko"),
        valid_from.isoformat() if valid_from else "",
    )
    return WeatherWarning(
        external_id=eid,
        level=str(row.get("stopien") or row.get("level") or "") or None,
        phenomenon=row.get("zjawisko") or row.get("phenomenon"),
        area=area,
        valid_from=valid_from,
        valid_to=valid_to,
        content=row.get("tresc") or row.get("content"),
        raw=row,
    )


def _stringify(v: object) -> str | None:
    """IMGW czasem zwraca listę kodów TERYT — joinujemy do stringa."""
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or None
    return str(v) or None


def _maybe_dt(s: object) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
