"""analityk_radaru — zbiera dane z radaru. Nie odpowiada klientowi."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from src.agents.tools.live import get_latest_image, list_recent_images
from src.agents.tools.search import search_radar_by_text
from src.config import get_settings

INSTRUCTION = """\
Jesteś analitykiem map radarowych. Zbierasz fakty wizualne z radaru i robisz
zwięzły raport dla głównego routera. NIE odpowiadasz użytkownikowi.

OBOWIĄZKOWO wywołaj co najmniej jeden tool. ZAWSZE warto sprawdzić aktualny
stan radaru, nawet dla pytań o przyszłość — bo wskazuje gdzie teraz są fronty
i co za chwilę się przesunie.

Mapowanie pytań na tools:
- każde pytanie o opady / burze / fronty / pogodę -> get_latest_image('radar')
- pytanie o ruch frontu / trend krótkoterminowy -> list_recent_images('radar', hours=2)
- pytanie o "podobną sytuację historyczną" -> search_radar_by_text(query)

Po wywołaniu toolów zwróć raport (2-4 zdania). ZAWSZE zaczynaj od dokładnie
takiego nagłówka:
"DANE Z MAP RADAROWYCH - "
a po myślniku kontynuuj:
- co widać na klatce (z captionu)
- region (na podstawie bbox: zachód/centrum/wschód PL, Europa Środkowa)
- kierunek ruchu frontu jeśli wynika z sekwencji
- URL klatki jeśli relewantny

Jeśli wszystko puste, zwróć: "DANE Z MAP RADAROWYCH - BRAK DANYCH"
"""

DESCRIPTION = (
    "Analityk map radarowych RainViewer: aktualne odbicia opadów i burz, sekwencja "
    "klatek do wykrycia ruchu frontu, cross-modal search po tekstowym opisie."
)

agent = LlmAgent(
    name="analityk_radaru",
    model=get_settings().gemini_model_caption,
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=[get_latest_image, list_recent_images, search_radar_by_text],
    output_key="ustalenia_radaru",
)
