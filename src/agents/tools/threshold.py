"""Logika progowa dla ostrzeżeń i analog forecasting."""

from __future__ import annotations

from typing import Any

from src.agents.tools.live import get_forecast


# Progi ostrzeżeń (uproszczona klasyfikacja IMGW)
THRESHOLDS = {
    "intense_rain_mm_h": 15.0,           # opad >= 15 mm/h = silny
    "very_intense_rain_mm_h": 30.0,      # >= 30 mm/h = bardzo silny
    "high_wind_ms": 17.0,                # 17 m/s = silny wiatr
    "very_high_wind_ms": 25.0,           # 25 m/s = bardzo silny / sztorm
    "heat_c": 30.0,                      # > 30°C = upał
    "extreme_heat_c": 35.0,              # > 35°C = ekstremalny
    "frost_c": -10.0,                    # < -10°C = silny mróz
    "extreme_frost_c": -20.0,
}


def evaluate_forecast_thresholds(city: str, hours: int = 48) -> dict[str, Any]:
    """Sprawdza prognozę na N godzin pod kątem przekroczenia progów ostrzeżeń.
    Używaj przed udzieleniem odpowiedzi, jeśli user pyta o jutrzejszą/przyszłą pogodę
    żeby wykryć potencjalnie niebezpieczne zjawiska.

    Args:
        city: miasto z DEFAULT_CITIES.
        hours: horyzont czasowy.

    Returns:
        Podsumowanie z listą wykrytych progów i godzin ich wystąpienia.
    """
    fc = get_forecast(city, hours=hours)
    if fc and "error" in fc[0]:
        return fc[0]

    alerts: list[dict[str, Any]] = []
    for r in fc:
        if r.get("precipitation_mm") and r["precipitation_mm"] >= THRESHOLDS["very_intense_rain_mm_h"]:
            alerts.append({"type": "very_intense_rain", "time": r["time"], "value": r["precipitation_mm"]})
        elif r.get("precipitation_mm") and r["precipitation_mm"] >= THRESHOLDS["intense_rain_mm_h"]:
            alerts.append({"type": "intense_rain", "time": r["time"], "value": r["precipitation_mm"]})
        if r.get("wind_speed_ms") and r["wind_speed_ms"] >= THRESHOLDS["very_high_wind_ms"]:
            alerts.append({"type": "very_high_wind", "time": r["time"], "value": r["wind_speed_ms"]})
        elif r.get("wind_speed_ms") and r["wind_speed_ms"] >= THRESHOLDS["high_wind_ms"]:
            alerts.append({"type": "high_wind", "time": r["time"], "value": r["wind_speed_ms"]})
        if r.get("temperature_c") and r["temperature_c"] >= THRESHOLDS["extreme_heat_c"]:
            alerts.append({"type": "extreme_heat", "time": r["time"], "value": r["temperature_c"]})
        elif r.get("temperature_c") and r["temperature_c"] >= THRESHOLDS["heat_c"]:
            alerts.append({"type": "heat", "time": r["time"], "value": r["temperature_c"]})
        if r.get("temperature_c") and r["temperature_c"] <= THRESHOLDS["extreme_frost_c"]:
            alerts.append({"type": "extreme_frost", "time": r["time"], "value": r["temperature_c"]})
        elif r.get("temperature_c") and r["temperature_c"] <= THRESHOLDS["frost_c"]:
            alerts.append({"type": "frost", "time": r["time"], "value": r["temperature_c"]})

    return {
        "city": city,
        "horizon_hours": hours,
        "alerts_count": len(alerts),
        "alerts": alerts[:20],
        "thresholds": THRESHOLDS,
    }
