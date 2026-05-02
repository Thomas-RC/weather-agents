"""Unit testy fetcherów — mockowane requests, sprawdzają parsowanie."""

from __future__ import annotations

import io
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.fetchers import imgw, nasa_gibs, openmeteo, rainviewer
from src.fetchers._util import lonlat_to_tile, parse_float, parse_int


def _png_bytes(color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    img = Image.new("RGB", (8, 8), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# IMGW synop
# --------------------------------------------------------------------------
def test_imgw_synop_parses_full_row(monkeypatch):
    sample = [
        {
            "id_stacji": "12295",
            "stacja": "Białystok",
            "data_pomiaru": "2026-05-02",
            "godzina_pomiaru": "11",
            "temperatura": "22.3",
            "predkosc_wiatru": "3",
            "kierunek_wiatru": "270",
            "wilgotnosc_wzgledna": "29.4",
            "suma_opadu": "0",
            "cisnienie": "1021.5",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = sample
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("src.fetchers.imgw.requests.get", lambda *a, **kw: mock_resp)

    result = imgw.fetch_synop()
    assert len(result) == 1
    r = result[0]
    assert r.source == "imgw"
    assert r.station_id == "12295"
    assert r.station_name == "Białystok"
    assert r.measured_at == datetime(2026, 5, 2, 11)
    assert r.temperature_c == 22.3
    assert r.wind_speed_ms == 3.0
    assert r.wind_dir_deg == 270
    assert r.humidity_pct == 29.4
    assert r.precipitation_mm == 0.0
    assert r.pressure_hpa == 1021.5
    assert r.external_id  # deterministyczny


def test_imgw_synop_handles_nulls(monkeypatch):
    sample = [
        {
            "id_stacji": "1",
            "stacja": "X",
            "data_pomiaru": "2026-01-01",
            "godzina_pomiaru": "0",
            "temperatura": None,
            "predkosc_wiatru": "",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = sample
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("src.fetchers.imgw.requests.get", lambda *a, **kw: mock_resp)

    [r] = imgw.fetch_synop()
    assert r.temperature_c is None
    assert r.wind_speed_ms is None


# --------------------------------------------------------------------------
# RainViewer
# --------------------------------------------------------------------------
def test_rainviewer_fetch_recent_frames(monkeypatch):
    metadata = {
        "host": "https://tilecache.rainviewer.com",
        "radar": {
            "past": [
                {"time": 1714651200, "path": "/v2/radar/abc"},
                {"time": 1714651800, "path": "/v2/radar/def"},
            ],
            "nowcast": [],
        },
    }
    png = _png_bytes((255, 0, 0))

    def _get(url, *a, **kw):
        m = MagicMock()
        if url == rainviewer.WEATHER_MAPS_URL:
            m.json.return_value = metadata
            m.raise_for_status = MagicMock()
        else:
            m.status_code = 200
            m.content = png
        return m

    monkeypatch.setattr("src.fetchers.rainviewer.requests.get", _get)

    frames = rainviewer.fetch_recent_frames(n_frames=2, zoom=4)
    assert len(frames) == 2
    f = frames[0]
    assert f.image_bytes.startswith(b"\x89PNG")
    assert f.zoom == 4
    assert f.bbox_north > f.bbox_south
    assert f.bbox_east > f.bbox_west
    assert f.image_id


def test_rainviewer_skips_non_png(monkeypatch):
    metadata = {
        "host": "https://x",
        "radar": {"past": [{"time": 1, "path": "/p"}], "nowcast": []},
    }

    def _get(url, *a, **kw):
        m = MagicMock()
        if url == rainviewer.WEATHER_MAPS_URL:
            m.json.return_value = metadata
            m.raise_for_status = MagicMock()
        else:
            m.status_code = 404
            m.content = b""
        return m

    monkeypatch.setattr("src.fetchers.rainviewer.requests.get", _get)
    frames = rainviewer.fetch_recent_frames(n_frames=1)
    assert frames == []


# --------------------------------------------------------------------------
# NASA GIBS satellite
# --------------------------------------------------------------------------
def test_nasa_gibs_fetches_tile(monkeypatch):
    from datetime import date

    # JPEG magic bytes (FFD8) — GIBS true-color zwraca jpg
    jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00fake-image-data"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = jpg
    monkeypatch.setattr("src.fetchers.nasa_gibs.requests.get", lambda *a, **kw: mock_resp)

    frame = nasa_gibs.fetch_tile(
        layer="MODIS_Terra_CorrectedReflectance_TrueColor",
        target_date=date(2026, 5, 1),
        zoom=4,
    )
    assert frame is not None
    assert frame.layer == "MODIS_Terra_CorrectedReflectance_TrueColor"
    assert frame.image_bytes == jpg
    assert "2026-05-01" in frame.source_url
    # GIBS używa kolejności Y/X, sprawdzamy że jest prawidłowo zbudowana
    assert f"/{frame.tile_y}/{frame.tile_x}.jpg" in frame.source_url


def test_nasa_gibs_returns_none_on_404(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.content = b""
    monkeypatch.setattr("src.fetchers.nasa_gibs.requests.get", lambda *a, **kw: mock_resp)
    assert nasa_gibs.fetch_tile() is None


def test_nasa_gibs_returns_none_on_invalid_image(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"not an image"
    monkeypatch.setattr("src.fetchers.nasa_gibs.requests.get", lambda *a, **kw: mock_resp)
    assert nasa_gibs.fetch_tile() is None


# --------------------------------------------------------------------------
# Open-Meteo
# --------------------------------------------------------------------------
def test_openmeteo_forecast_parses(monkeypatch):
    sample = {
        "hourly": {
            "time": ["2026-05-02T00:00", "2026-05-02T01:00"],
            "temperature_2m": [11.5, 11.2],
            "precipitation": [0.0, 0.1],
            "pressure_msl": [1015.0, 1015.2],
            "relative_humidity_2m": [80, 78],
            "wind_speed_10m": [2.5, 3.1],
            "wind_direction_10m": [180, 190],
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = sample
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("src.fetchers.openmeteo.requests.get", lambda *a, **kw: mock_resp)

    result = openmeteo.fetch_forecast(cities=[("TestCity", 52.0, 21.0)], forecast_days=1)
    assert len(result) == 2
    assert result[0].station_name == "TestCity"
    assert result[0].temperature_c == 11.5
    assert result[0].wind_dir_deg == 180


# --------------------------------------------------------------------------
# Util
# --------------------------------------------------------------------------
def test_lonlat_to_tile_warsaw_zoom4():
    x, y = lonlat_to_tile(21.01, 52.23, 4)
    assert (x, y) == (8, 5)


def test_parse_helpers():
    assert parse_float("12.3") == 12.3
    assert parse_float("12,3") == 12.3
    assert parse_float("") is None
    assert parse_float(None) is None
    assert parse_int("3") == 3
    assert parse_int("3.7") == 3
    assert parse_int(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
