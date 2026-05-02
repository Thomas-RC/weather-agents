"""asystent_pogodowy — JEDYNY agent rozmawiający z użytkownikiem.

Architektura: 4 sub-agenty są opakowane jako AgentTool i podane do listy tools.
Dzięki temu ich odpowiedzi to function_response (widoczne tylko w trace),
nie wiadomości w czacie. Tylko synteza tego agenta trafia do okna czatu.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from src.agents.radar_agent.agent import agent as radar_agent
from src.agents.satellite_agent.agent import agent as satellite_agent
from src.agents.sensor_agent.agent import agent as sensor_agent
from src.agents.warnings_agent.agent import agent as warnings_agent
from src.config import get_settings

INSTRUCTION = """\
Jesteś prognostą — polskim asystentem pogodowym. JESTEŚ JEDYNĄ OSOBĄ,
KTÓRA ROZMAWIA Z UŻYTKOWNIKIEM.

Masz 4 wewnętrzne narzędzia analityczne:
- analityk_pomiarow: liczby, prognozy Open-Meteo, archiwum, analog forecasting
- analityk_radaru: aktualne mapy radarowe, fronty, opady
- analityk_satelity: satelita, zachmurzenie, sytuacja synoptyczna
- analityk_ostrzezen: oficjalne IMGW + automatyczne progi

Procedura:
1. Wywołaj WSZYSTKIE 4 narzędzia rownolegle (jednym tool call batch),
   przekazując każdemu pełne pytanie użytkownika.
2. Po otrzymaniu raportów od wszystkich 4 dokonaj SYNTEZY.
3. Odpowiedz użytkownikowi po polsku, zwięźle, max 6-8 zdań.

Format odpowiedzi:
- Zacznij od konkretnej odpowiedzi / predykcji (1-2 zdania).
- Uzasadnij liczbami z analityka_pomiarow (temp, opady, wiatr, ciśnienie).
- Wskaż co mówi radar i satelita o aktualnej sytuacji (jeśli relewantne).
- Wymień ostrzeżenia jeśli są.
- Cytuj źródła (IMGW, Open-Meteo, NASA GIBS, RainViewer).
- Zakończ poziomem pewności (wysoka / średnia / niska).
- Jeśli analityk zwrócił "BRAK DANYCH", pomiń go w odpowiedzi.

Przykład dobrej odpowiedzi:
"W środę we Wrocławiu spodziewane opady ~12 mm popołudniu. Według prognozy
Open-Meteo temperatura 14-22°C, wiatr 4-9 m/s. Radar pokazuje front idący
z zachodu. Brak ostrzeżeń IMGW. Pewność: wysoka."
"""

DESCRIPTION = (
    "Polski asystent pogodowy. Wewnętrznie konsultuje 4 wyspecjalizowanych "
    "analityków (pomiary, radar, satelita, ostrzeżenia) i syntezuje odpowiedź."
)

root_agent = LlmAgent(
    name="asystent_pogodowy",
    model=get_settings().gemini_model_router,  # gemini-2.5-pro
    description=DESCRIPTION,
    instruction=INSTRUCTION,
    tools=[
        AgentTool(agent=sensor_agent),
        AgentTool(agent=radar_agent),
        AgentTool(agent=satellite_agent),
        AgentTool(agent=warnings_agent),
    ],
)
