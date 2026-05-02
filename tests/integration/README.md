# Integration tests

Testy które uderzają w **realne** Qdrant/MariaDB/MinIO/Vertex AI. Wymagają:
- `docker compose up -d` (4 infra kontenery zdrowe)
- Działającego SA key w `secrets/`
- Naliczają koszty Vertex AI (drobne — kilka centów)

## Uruchomienie

```bash
# Smoke testy (każdy odpalany przez worker container):
docker compose run --rm worker python -m scripts.smoke_storage    # Qdrant + MinIO + MariaDB
docker compose run --rm worker python -m scripts.smoke_pipeline   # caption + embed + retrieval
docker compose run --rm worker python -m scripts.smoke_agents     # 3 golden queries multi-agent

# Backfill historyczny (raz na początku projektu):
docker compose run --rm worker python -m scripts.backfill_archive
```

## Golden queries (smoke_agents.py)

1. **"Jaka jest teraz temperatura w Warszawie?"**
   → `weather_router → sensor_agent → get_current_synop_pl`
   → Liczbowa odpowiedź z IMGW.

2. **"Czy jutro w Krakowie będzie padać?"**
   → `sensor_agent → evaluate_forecast_thresholds + get_forecast`
   → Prognoza Open-Meteo + sprawdzenie progów.

3. **"Pokaż najnowszą mapę radaru i powiedz gdzie pada."**
   → `weather_router → radar_agent → get_latest_image`
   → URL klatki + opis z captionu.

Każdy test sprawdza poprawny routing (który sub-agent), wywołane tools i obecność
kluczowych słów w odpowiedzi.
