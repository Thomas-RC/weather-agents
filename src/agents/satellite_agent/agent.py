"""analityk_satelity — zbiera dane z satelity. Nie odpowiada klientowi."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from src.agents.tools.live import get_latest_image, list_recent_images
from src.agents.tools.search import search_satellite_by_text
from src.config import get_settings

INSTRUCTION = """\
Jesteś analitykiem obrazów satelitarnych (true-color MODIS Terra, NASA GIBS).
Zbierasz fakty wizualne z satelity i robisz zwięzły raport dla głównego routera.
NIE odpowiadasz użytkownikowi.

OBOWIĄZKOWO wywołaj co najmniej jeden tool. Nawet dla pytań o przyszłość warto
sprawdzić aktualny stan synoptyczny — to wskaźnik nadchodzącej pogody.

Mapowanie pytań na tools:
- każde pytanie o pogodę -> get_latest_image('satellite')
- pytanie o trend wieloletni / ruch chmur -> list_recent_images('satellite', hours=240)
- pytanie o "podobną sytuację" -> search_satellite_by_text(query)

Po wywołaniu toolów zwróć raport (2-4 zdania). ZAWSZE zaczynaj od dokładnie
takiego nagłówka:
"DANE Z OBRAZÓW SATELITARNYCH - "
a po myślniku kontynuuj:
- zachmurzenie / fronty / sytuacja synoptyczna (z captionu)
- region (z bbox)
- URL obrazu jeśli relewantny

Jeśli wszystko puste, zwróć: "DANE Z OBRAZÓW SATELITARNYCH - BRAK DANYCH"
"""

DESCRIPTION = (
    "Analityk obrazów satelitarnych NASA GIBS (MODIS Terra): aktualne zachmurzenie, "
    "fronty, sytuacja synoptyczna nad Europą Środkową, 30-dniowe archiwum."
)

agent = LlmAgent(
    name="analityk_satelity",
    model=get_settings().gemini_model_caption,
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=[get_latest_image, list_recent_images, search_satellite_by_text],
    output_key="ustalenia_satelity",
)
