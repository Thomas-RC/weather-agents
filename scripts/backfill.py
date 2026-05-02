"""Jednorazowy backfill — odpala każdy handler raz, bez schedulera.

Zastosowanie:
- pierwsze uruchomienie projektu (inicjalizacja Qdrant + MinIO + bootstrap danych)
- odzyskanie po awarii (worker padł na X godzin, chcemy nadrobić)
- ręczne testy bez czekania na cron

Uruchomienie z hosta (po `docker compose up -d` infra):
    docker compose run --rm worker python -m scripts.backfill

albo lokalnie z venv:
    python -m scripts.backfill
"""

from __future__ import annotations

from src.config import get_settings
from src.observability.logging import configure_logging, get_logger
from src.storage.minio_store import ensure_bucket
from src.storage.qdrant_store import init_collections
from src.worker import handlers


def main() -> None:
    s = get_settings()
    configure_logging(s.app_log_level)
    log = get_logger("backfill")
    log.info("backfill.start")

    init_collections()
    ensure_bucket()

    handlers.handle_imgw_synop()
    handlers.handle_imgw_warnings()
    handlers.handle_radar(n_frames=6, zoom=4)  # więcej klatek niż w scheduler
    handlers.handle_satellite(zoom=4)
    handlers.handle_openmeteo_forecast()

    log.info("backfill.done")


if __name__ == "__main__":
    main()
