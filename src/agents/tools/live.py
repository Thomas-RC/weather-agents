"""Bieżące dane / odświeżenie on-demand i lookup w MariaDB."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from src.fetchers import imgw, openmeteo
from src.storage import mariadb_store, minio_store
from src.storage.mariadb_store import query_sensor_timeseries


def _jsonable(v: Any) -> Any:
    """Konwersja typów MariaDB/Python na JSON-serializable (Decimal→float, datetime→str)."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def get_current_synop_pl() -> list[dict[str, Any]]:
    """Pobiera **bieżące** odczyty ze wszystkich 62 stacji synoptycznych IMGW (Polska).
    Zwraca świeże dane prosto z API IMGW. Używaj dla pytań o aktualną pogodę.

    Returns:
        Lista stacji z polami: stacja, temperatura, ciśnienie, wiatr, opady, wilgotność.
    """
    readings = imgw.fetch_synop()
    return [
        {
            "station": r.station_name,
            "measured_at": r.measured_at.isoformat(),
            "temperature_c": r.temperature_c,
            "pressure_hpa": r.pressure_hpa,
            "wind_speed_ms": r.wind_speed_ms,
            "wind_dir_deg": r.wind_dir_deg,
            "humidity_pct": r.humidity_pct,
            "precipitation_mm": r.precipitation_mm,
        }
        for r in readings
    ]


def get_current_warnings() -> list[dict[str, Any]]:
    """Pobiera **bieżące** ostrzeżenia meteorologiczne IMGW. Pusta lista jeśli brak alertów.

    Returns:
        Lista ostrzeżeń: stopień, zjawisko, obszar, ważność od/do, treść.
    """
    warns = imgw.fetch_warnings()
    return [
        {
            "level": w.level,
            "phenomenon": w.phenomenon,
            "area": w.area,
            "valid_from": w.valid_from.isoformat() if w.valid_from else None,
            "valid_to": w.valid_to.isoformat() if w.valid_to else None,
            "content": w.content,
        }
        for w in warns
    ]


def get_forecast(city: str, hours: int = 48) -> list[dict[str, Any]]:
    """Prognoza pogody dla miasta na N godzin do przodu (Open-Meteo, model fizyczny).
    Obsługuje miasta polskie z DEFAULT_CITIES — Warszawa, Kraków, Gdańsk, Wrocław,
    Poznań, Łódź, Białystok, Szczecin. Zwraca godzinową prognozę.

    Args:
        city: nazwa miasta po polsku (musi być w DEFAULT_CITIES).
        hours: liczba godzin prognozy do zwrócenia (max 168 = 7 dni).

    Returns:
        Lista godzinowych prognoz z polami temperature_c, precipitation_mm itd.
    """
    if city not in openmeteo.DEFAULT_CITIES:
        return [{"error": f"Nieznane miasto '{city}'. Dostępne: {list(openmeteo.DEFAULT_CITIES)}"}]
    lat, lon = openmeteo.DEFAULT_CITIES[city]
    forecast_days = min(7, max(1, (hours + 23) // 24))
    readings = openmeteo.fetch_forecast(
        cities=[(city, lat, lon)], forecast_days=forecast_days
    )
    return [
        {
            "time": r.measured_at.isoformat(),
            "temperature_c": r.temperature_c,
            "precipitation_mm": r.precipitation_mm,
            "pressure_hpa": r.pressure_hpa,
            "wind_speed_ms": r.wind_speed_ms,
            "wind_dir_deg": r.wind_dir_deg,
            "humidity_pct": r.humidity_pct,
        }
        for r in readings[:hours]
    ]


def get_sensor_history(station_name: str, variable: str, hours: int = 72) -> list[dict[str, Any]]:
    """Zwraca szereg czasowy danej zmiennej dla stacji za ostatnie N godzin.

    Args:
        station_name: nazwa stacji lub miasta (np. "Warszawa", "Kraków").
        variable: jedna z: temperature_c, pressure_hpa, wind_speed_ms, humidity_pct,
                  precipitation_mm.
        hours: ile godzin wstecz, max 720 (30 dni).

    Returns:
        Lista {measured_at, value} posortowana po czasie.
    """
    end = datetime.utcnow()
    start = end - timedelta(hours=min(hours, 720))
    rows = query_sensor_timeseries(station_name, variable, start, end)
    return [
        {"time": r["measured_at"].isoformat(), "value": float(r["value"]) if r["value"] is not None else None}
        for r in rows
    ]


def get_latest_image(modality: str) -> dict[str, Any] | None:
    """Najświeższy obraz (radar lub satellite) z URL i captionem.

    Args:
        modality: 'radar' lub 'satellite'.
    """
    if modality not in ("radar", "satellite"):
        return None
    sql = text(
        """SELECT image_id, source, captured_at, minio_key, caption_short, caption_long,
                  bbox_north, bbox_south, bbox_east, bbox_west
           FROM images WHERE modality = :m ORDER BY captured_at DESC LIMIT 1"""
    )
    with mariadb_store.get_engine().connect() as conn:
        row = conn.execute(sql, {"m": modality}).first()
    if not row:
        return None
    d = _jsonable(dict(row._mapping))
    try:
        d["url"] = minio_store.presigned_get_url(d["minio_key"], expires_in=3600)
    except Exception:
        d["url"] = None
    return d


def list_recent_images(modality: str, hours: int = 48) -> list[dict[str, Any]]:
    """Lista klatek danej modalności z ostatnich N godzin (chronologicznie rosnąco).

    Args:
        modality: 'radar' albo 'satellite'.
        hours: jak daleko wstecz.
    """
    if modality not in ("radar", "satellite"):
        return []
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    sql = text(
        """SELECT image_id, captured_at, minio_key, caption_short
           FROM images WHERE modality = :m AND captured_at >= :cutoff
           ORDER BY captured_at"""
    )
    with mariadb_store.get_engine().connect() as conn:
        rows = list(conn.execute(sql, {"m": modality, "cutoff": cutoff}).mappings())
    return [_jsonable({
        "image_id": r["image_id"],
        "captured_at": r["captured_at"],
        "caption_short": r["caption_short"],
    }) for r in rows]
