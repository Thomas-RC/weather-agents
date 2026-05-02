"""End-to-end smoke test multi-agent system — wymaga LIVE Vertex AI.

Wysyła kilka testowych pytań do weather_router i wypisuje przebieg + odpowiedź.
"""

from __future__ import annotations

import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents.weather_router.agent import root_agent
from src.observability.logging import configure_logging, get_logger

APP_NAME = "weather-rag"
USER_ID = "smoke-user"

QUERIES = [
    "Jaka jest teraz temperatura w Warszawie?",
    "Czy jutro w Krakowie będzie padać?",
    "Pokaż najnowszą mapę radaru i powiedz gdzie pada.",
]


async def run_query(runner: Runner, session_id: str, query: str) -> None:
    log = get_logger("smoke_agents")
    log.info("query.start", q=query)
    msg = types.Content(role="user", parts=[types.Part(text=query)])

    final_text: list[str] = []
    async for ev in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=msg):
        if ev.author and ev.author != "user":
            tools_called = [
                p.function_call.name
                for p in (ev.content.parts if ev.content else [])
                if p.function_call is not None
            ]
            if tools_called:
                log.info("tool.call", agent=ev.author, tools=tools_called)
            elif ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if p.text:
                        final_text.append(p.text)

    log.info("query.done", agent_response="\n".join(final_text)[:500])


async def main() -> None:
    configure_logging("INFO")
    log = get_logger("smoke_agents")
    log.info("smoke.start", agents=[a.name for a in root_agent.sub_agents])

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

    for q in QUERIES:
        await run_query(runner, session.id, q)
        print("---")


if __name__ == "__main__":
    asyncio.run(main())
