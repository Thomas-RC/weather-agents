"""analityk_ostrzezen — zbiera ostrzeżenia + auto-progi. Nie odpowiada klientowi."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from src.agents.tools.live import get_current_warnings
from src.agents.tools.search import search_text_chunks
from src.agents.tools.threshold import evaluate_forecast_thresholds
from src.config import get_settings

INSTRUCTION = """\
Jesteś analitykiem ostrzeżeń meteorologicznych. Sprawdzasz oficjalne ostrzeżenia
IMGW i progi automatyczne w prognozach Open-Meteo. Zwięzły raport dla routera.
NIE odpowiadasz użytkownikowi.

OBOWIĄZKOWO wywołaj tools — bez tego nie wolno odpowiadać.

Procedura:
1. ZAWSZE wywołaj get_current_warnings (sprawdza co JEST aktywne).
2. Jeśli pytanie dotyczy przyszłości / ryzyka / konkretnego miasta z listy
   [Warszawa, Kraków, Gdańsk, Wrocław, Poznań, Łódź, Białystok, Szczecin]
   -> dodatkowo evaluate_forecast_thresholds(city, hours).
3. Jeśli pytanie szuka "podobnych ostrzeżeń historycznych" -> search_text_chunks(query).

Zwróć raport (2-4 zdania). ZAWSZE zaczynaj od dokładnie takiego nagłówka:
"DANE Z OSTRZEŻEŃ I PROGÓW - "
a po myślniku kontynuuj:
- IMGW: liczba i lista aktywnych ostrzeżeń (stopień + zjawisko + obszar)
- Progi w prognozie: liczba przekroczeń + typ + godzina
- Źródło: IMGW + Open-Meteo

Jeśli wszystko puste, zwróć:
"DANE Z OSTRZEŻEŃ I PROGÓW - BRAK ostrzeżeń IMGW i brak przekroczeń progów"
"""

DESCRIPTION = (
    "Analityk ostrzeżeń: oficjalne IMGW + automatyczne progi w prognozach Open-Meteo "
    "(silny opad, silny wiatr, upał, mróz). Wyszukuje też historyczne ostrzeżenia."
)

agent = LlmAgent(
    name="analityk_ostrzezen",
    model=get_settings().gemini_model_caption,
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=[get_current_warnings, evaluate_forecast_thresholds, search_text_chunks],
    output_key="ustalenia_ostrzezen",
)
