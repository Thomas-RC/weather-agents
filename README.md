# Weather RAG — multimodalny asystent pogodowy

Wieloagentowy system **predykcji pogody** dla Polski, oparty o Google ADK
(Agent Development Kit) i Vertex AI (Gemini 2.5).

Projekt zaliczeniowy z przedmiotu *"Uczenie maszynowe dla danych złożonych"* —
demonstruje multimodalny RAG łączący 4 modalności danych w jednym systemie.

## Modalności

| Modalność | Źródło | Detail |
|---|---|---|
| Sensory liczbowe | IMGW + Open-Meteo | 62 stacje synoptyczne PL + prognoza 7d + 60d archiwum dla 8 miast |
| Radar | RainViewer | mapy odbić co 10 min (zoom 4, Europa Środkowa) |
| Satelita | NASA GIBS | true-color MODIS Terra, daily snapshot, 30d archiwum |
| Tekst | IMGW + auto-summary | ostrzeżenia meteo + dzienne podsumowania statystyczne |

## Architektura

```
┌──────────────────────────────────────────────────────────────────┐
│                         User (Streamlit)                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  weather_router (Gemini Pro)│ ← LLM-driven delegation
                │  sub_agents=[...]           │
                └─┬────┬────┬────┬────────────┘
                  │    │    │    │
       ┌──────────▼┐ ┌─▼───┐ ┌▼──┐ ┌▼────────┐
       │sensor_a.  │ │radar│ │sat│ │warnings │ ← gemini-2.5-flash
       │5 tools    │ │3    │ │3  │ │3        │
       └─┬─────────┘ └─┬───┘ └─┬─┘ └────┬────┘
         │             │       │        │
         ▼             ▼       ▼        ▼
    ┌──────────┐  ┌────────┐ ┌──────┐ ┌──────────┐
    │MariaDB   │  │Qdrant  │ │MinIO │ │ Vertex AI│
    │sensors   │  │vectors │ │images│ │ Gemini + │
    │metadata  │  │named:  │ │PNG/  │ │ embed×2  │
    │aggregates│  │ text+mm│ │JPG   │ │          │
    └──────────┘  └────────┘ └──────┘ └──────────┘

         ▲ worker container ▲
         │ APScheduler co 10/15/30/60 min  │
         │ fetchery + caption + embed + upsert │
```

**Stack:**
- `gemini-2.5-pro` — router (synteza odpowiedzi)
- `gemini-2.5-flash` — sub-agenci + captioning obrazów
- `gemini-embedding-001` — text retrieval (3072d)
- `multimodalembedding@001` — cross-modal text↔image (1408d)
- Qdrant — wektorowa baza z **named vectors** (text_3072 + mm_1408)
- MinIO — S3-compatible blob storage dla obrazów
- MariaDB — sensor time series + metadata
- Streamlit — chat UI z multimodal upload
- APScheduler — cron w Pythonie

## Quick start

### 1. Wymagania

- Docker + docker-compose
- Konto GCP z Vertex AI API włączonym
- Service Account z rolą `roles/aiplatform.user`

### 2. Setup

```bash
# Sklonuj repo
git clone <url>
cd weather-agents

# Skopiuj env i wypełnij
cp .env.example .env
# Edytuj .env: GOOGLE_CLOUD_PROJECT, MARIADB_*, MINIO_*, GOOGLE_SA_KEY_FILE

# Wrzuć Service Account JSON do secrets/ (gitignored)
mv ~/Downloads/sa-key.json secrets/sa-key.json
```

### 3. Start

```bash
# Pełen stack (5 kontenerów + opcjonalnie phpMyAdmin)
docker compose up -d
docker compose --profile admin up -d phpmyadmin

# Backfill historycznych danych (raz na start, ~5 min, ~$0.30 Vertex)
docker compose run --rm worker python -m scripts.backfill_archive

# Sprawdź:
# - Streamlit:    http://localhost:8501
# - phpMyAdmin:   http://localhost:8081
# - MinIO console: http://localhost:9001
# - Qdrant API:   http://localhost:6333/dashboard
```

Worker uruchamia się i przy starcie odpala każdy handler raz (warmup), potem
działa cyklicznie co 10/15/30/60 minut.

## Mechanizm "uczenia się z historii"

System nie trenuje sieci neuronowej (RAG ≠ ML training). Predykcję realizuje
przez **3 mechanizmy**:

1. **Pre-trained physics models** — Open-Meteo zwraca prognozy z modeli
   ECMWF/GFS/ICON wytrenowanych na 80+ latach danych. To *ich* uczenie.

2. **Analog forecasting przez RAG** — dla każdego dnia w 60-dniowym archiwum
   trzymamy **embedded daily summary**. Pytanie *"jaka będzie pogoda?"* uruchamia:
   - pobranie aktualnego stanu (sensory + radar + satelita)
   - retrieval **k najpodobniejszych dni** historycznych (cosine over text_3072)
   - sprawdzenie co stało się następnego dnia (z archiwum)
   - synteza Gemini: *"3 z 5 podobnych dni zakończyły się burzą — prognoza X"*

3. **Threshold-based warnings** — `evaluate_forecast_thresholds()` sprawdza
   czy prognoza Open-Meteo przekracza progi (opady > 30 mm/h, wiatr > 25 m/s,
   itd.) i generuje automatyczne alerty.

## Sub-agenci i ich tools

| Agent | Model | Tools |
|---|---|---|
| **weather_router** | gemini-2.5-pro | `transfer_to_agent` (LLM-driven) |
| **sensor_agent** | gemini-2.5-flash | `get_current_synop_pl`, `get_forecast`, `get_sensor_history`, `find_analog_days`, `evaluate_forecast_thresholds` |
| **radar_agent** | gemini-2.5-flash | `get_latest_image`, `list_recent_images`, `search_radar_by_text` |
| **satellite_agent** | gemini-2.5-flash | `get_latest_image`, `list_recent_images`, `search_satellite_by_text` |
| **warnings_agent** | gemini-2.5-flash | `get_current_warnings`, `evaluate_forecast_thresholds`, `search_text_chunks` |

## Testy

```bash
# Unit (lokalnie, mockowane fetchery)
pytest tests/unit/ -v

# Integration (wymaga docker compose up + Vertex)
docker compose run --rm worker python -m scripts.smoke_storage
docker compose run --rm worker python -m scripts.smoke_pipeline
docker compose run --rm worker python -m scripts.smoke_agents
```

## Struktura repo

```
weather-rag/
├── docker-compose.yml         # 5 kontenerów: qdrant, minio, mariadb, worker, app
├── deploy/
│   ├── Dockerfile.worker      # APScheduler + handlery + pipeline
│   └── Dockerfile.app         # Streamlit + ADK Runner
├── infra/sql/init.sql         # MariaDB schema
├── secrets/                   # SA JSON (gitignored)
├── src/
│   ├── config.py              # Pydantic Settings
│   ├── schemas.py             # Pydantic modele danych
│   ├── fetchers/              # IMGW, RainViewer, NASA GIBS, Open-Meteo
│   ├── storage/               # Qdrant + MinIO + MariaDB wrappery
│   ├── pipeline/              # caption + embed text/mm + upsert
│   ├── worker/                # scheduler + handlery (cron)
│   ├── agents/                # ADK: 4 sub-agenty + router
│   │   ├── tools/             # search.py + live.py + threshold.py
│   │   ├── sensor_agent/
│   │   ├── radar_agent/
│   │   ├── satellite_agent/
│   │   ├── warnings_agent/
│   │   └── weather_router/    # root agent
│   ├── observability/         # structlog
│   └── app/streamlit_app.py   # UI
├── scripts/                   # backfill + smoke testy
└── tests/                     # unit (mock) + integration (live)
```

## Licencja / autorzy

Projekt zaliczeniowy WSB.
