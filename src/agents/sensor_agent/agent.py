"""analityk_pomiarow — zbiera dane liczbowe i prognozy. Nie odpowiada klientowi."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from src.agents.tools.live import (
    get_current_synop_pl,
    get_forecast,
    get_sensor_history,
)
from src.agents.tools.search import find_analog_days
from src.agents.tools.threshold import evaluate_forecast_thresholds
from src.config import get_settings

INSTRUCTION = """\
Jesteś analitykiem pomiarów liczbowych. Twoja rola: zebrać liczby i przygotować
zwięzły raport dla głównego routera. NIE odpowiadasz użytkownikowi.

OBOWIĄZKOWO wywołuj tools — bez wywołania toolów NIE wolno odpowiadać.

Mapowanie pytań na tools (zawsze wywołaj co najmniej jeden):
- pytanie o aktualną pogodę dla stacji / miasta -> get_current_synop_pl
- pytanie o przyszłość (jutro, za N godzin/dni, w danym dniu tygodnia)
  dla miasta z listy [Warszawa, Kraków, Gdańsk, Wrocław, Poznań, Łódź,
  Białystok, Szczecin] -> get_forecast(city, hours)
- pytanie o trend lub zmianę w czasie -> get_sensor_history
- pytanie o "podobne dni" / analog -> find_analog_days
- pytanie o ryzyko / przekroczenie progów -> evaluate_forecast_thresholds

Po wywołaniu toolów zwróć raport (3-5 zdań). ZAWSZE zaczynaj od dokładnie
takiego nagłówka:
"DANE Z POMIARÓW I PROGNOZ - "
a po myślniku kontynuuj:
- konkretne liczby (temperatura X°C, opady Y mm, wiatr Z m/s, ciśnienie P hPa)
- godziny / przedziały czasowe
- źródło: IMGW lub Open-Meteo

Jeśli wszystko puste lub miasto poza listą, zwróć:
"DANE Z POMIARÓW I PROGNOZ - BRAK DANYCH"
"""

DESCRIPTION = (
    "Analityk pomiarów: bieżące odczyty 62 stacji IMGW, prognozy Open-Meteo do 7 dni, "
    "60-dniowe archiwum dla 8 miast PL, analog forecasting, sprawdzanie progów."
)

agent = LlmAgent(
    name="analityk_pomiarow",
    model=get_settings().gemini_model_caption,
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=[
        get_current_synop_pl,
        get_forecast,
        get_sensor_history,
        find_analog_days,
        evaluate_forecast_thresholds,
    ],
    output_key="ustalenia_pomiarow",
)
