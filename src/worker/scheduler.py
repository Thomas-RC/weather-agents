"""Worker entry point — APScheduler + 5 cron jobów + graceful shutdown.

Po starcie:
1. Inicjalizuje kolekcje Qdrant i bucket MinIO (idempotentnie)
2. Odpala każdy job raz (warm-up — natychmiast mamy dane, nie czekamy do pełnej godziny)
3. Uruchamia BlockingScheduler z cronami

Cron schedule (UTC):
- IMGW synop:        */15 *  *  * *
- IMGW warnings:     */30 *  *  * *
- RainViewer radar:  */10 *  *  * *
- NASA GIBS sat:     0    *  *  * *  (co godzinę — i tak ten sam obraz przez 24h)
- Open-Meteo fc:     0    6  *  * *  (raz dziennie rano)
"""

from __future__ import annotations

import signal
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler

from src.config import get_settings
from src.observability.logging import configure_logging, get_logger
from src.storage.minio_store import ensure_bucket
from src.storage.qdrant_store import init_collections
from src.worker import handlers


def main() -> None:
    s = get_settings()
    configure_logging(s.app_log_level)
    log = get_logger("worker.scheduler")
    log.info("worker.startup", project=s.google_cloud_project, env=s.app_env)

    # Idempotentna inicjalizacja
    init_collections()
    ensure_bucket()
    log.info("worker.infrastructure_ready")

    sched = BlockingScheduler(timezone="UTC")
    jobs: list[tuple[str, Any, dict[str, Any]]] = [
        ("imgw_synop",       handlers.handle_imgw_synop,        {"minute": "*/15"}),
        ("imgw_warnings",    handlers.handle_imgw_warnings,     {"minute": "*/30"}),
        ("rainviewer_radar", handlers.handle_radar,             {"minute": "*/10"}),
        ("nasa_gibs_sat",    handlers.handle_satellite,         {"minute": "5", "hour": "*"}),
        ("openmeteo_forecast", handlers.handle_openmeteo_forecast, {"hour": "6", "minute": "0"}),
    ]
    for job_id, fn, cron in jobs:
        sched.add_job(fn, "cron", id=job_id, **cron)

    # Warm-up — odpal każdy raz na start
    log.info("worker.warmup_start")
    for job_id, fn, _ in jobs:
        log.info("worker.warmup_run", job=job_id)
        try:
            fn()
        except Exception as e:
            log.error("worker.warmup_failed", job=job_id, error=str(e))
    log.info("worker.warmup_done")

    # Graceful shutdown
    def _shutdown(signum, frame):  # type: ignore[no-untyped-def]
        log.info("worker.shutdown_signal", signal=signum)
        sched.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("worker.scheduler_starting", jobs=[j[0] for j in jobs])
    sched.start()


if __name__ == "__main__":
    main()
