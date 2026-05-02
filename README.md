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

## Bibliografia i źródła

### Publikacje naukowe (arxiv.org)

**Retrieval-Augmented Generation:**
- Lewis et al. (2020), *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* — https://arxiv.org/abs/2005.11401 (foundational RAG paper)
- Shi et al. (2023), *REPLUG: Retrieval-Augmented Black-Box Language Models* — https://arxiv.org/abs/2301.12652
- Gao et al. (2024), *Retrieval-Augmented Generation for Large Language Models: A Survey* — https://arxiv.org/abs/2312.10997

**Multimodalne embeddings i retrieval:**
- Radford et al. (2021), *Learning Transferable Visual Models From Natural Language Supervision* (CLIP) — https://arxiv.org/abs/2103.00020
- Jia et al. (2021), *Scaling Up Visual and Vision-Language Representation Learning With Noisy Text Supervision* (ALIGN) — https://arxiv.org/abs/2102.05918
- Lin et al. (2024), *MM-Embed: Universal Multimodal Retrieval with Multimodal LLMs* — https://arxiv.org/abs/2411.02571

**Multi-agent LLM:**
- Wu et al. (2023), *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation* — https://arxiv.org/abs/2308.08155
- Hong et al. (2024), *MetaGPT: Meta Programming for Multi-Agent Collaborative Framework* — https://arxiv.org/abs/2308.00352
- Park et al. (2023), *Generative Agents: Interactive Simulacra of Human Behavior* — https://arxiv.org/abs/2304.03442

**ML w prognozach pogody (kontekst dla analog forecasting):**
- Lam et al. (2023), *GraphCast: Learning skillful medium-range global weather forecasting* — https://arxiv.org/abs/2212.12794 (DeepMind)
- Bi et al. (2022), *Pangu-Weather: A 3D High-Resolution Model for Fast and Accurate Global Weather Forecast* — https://arxiv.org/abs/2211.02556
- Pathak et al. (2022), *FourCastNet: A Global Data-driven High-resolution Weather Model using Adaptive Fourier Neural Operators* — https://arxiv.org/abs/2202.11214
- Lorenz (1969), *Atmospheric Predictability as Revealed by Naturally Occurring Analogues* — klasyczna praca o analog forecasting (J. Atmos. Sci.)

### Dokumentacja Google

**Agent Development Kit (ADK):**
- ADK home — https://adk.dev
- Quickstart Python — https://adk.dev/get-started/quickstart/
- Multi-agent patterns — https://adk.dev/agents/multi-agents/
- LlmAgent / Workflow agents — https://adk.dev/agents/llm-agents/, https://adk.dev/agents/workflow-agents/
- Agent-as-a-Tool — https://adk.dev/tools-custom/function-tools/
- Tutorial multi-tool weather agent — https://adk.dev/tutorials/multi-tool-agent/
- Tutorial agent team — https://adk.dev/tutorials/agent-team/

**Vertex AI / Gemini:**
- Gemini 2.5 Pro / Flash overview — https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models
- Text embeddings (`gemini-embedding-001`) — https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings
- Multimodal embeddings (`multimodalembedding@001`) — https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-multimodal-embeddings
- Thinking budget (Gemini 2.5) — https://cloud.google.com/vertex-ai/generative-ai/docs/thinking
- Vertex AI authentication (Service Accounts) — https://cloud.google.com/vertex-ai/docs/general/authentication

### Narzędzia open source

- **Qdrant** (vector DB, named vectors) — https://qdrant.tech/documentation/
- **MinIO** (S3-compatible object storage) — https://min.io/docs/minio/linux/index.html
- **MariaDB** — https://mariadb.org/documentation/
- **APScheduler** — https://apscheduler.readthedocs.io/

### Źródła danych

- **IMGW** (synop + warnings) — https://danepubliczne.imgw.pl
- **Open-Meteo** (forecast + archive) — https://open-meteo.com, https://open-meteo.com/en/docs/historical-weather-api
- **RainViewer** (radar tiles) — https://www.rainviewer.com/api.html
- **NASA GIBS** (satellite WMTS, MODIS Terra/Aqua) — https://nasa-gibs.github.io/gibs-api-docs/, https://wiki.earthdata.nasa.gov/display/GIBS

## Licencja / autorzy

Projekt zaliczeniowy WSB.
