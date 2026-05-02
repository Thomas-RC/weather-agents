# Plan wdrożenia: Multimodalny RAG pogodowy

Aplikacja webowa odpowiadająca na pytania o pogodę w Polsce, łącząca 4 modalności danych
(sensory liczbowe, radar, satelita, tekst) przez wieloagentową architekturę zbudowaną
w Google ADK z Gemini 2.5 jako modelem rozumowania i embeddingów.

---

## 1. Cel i zakres

**Cel:** projekt zaliczeniowy "Uczenie maszynowe dla danych złożonych" — produkcyjnie
zaprojektowana aplikacja multimodalnego RAG, w pełni działająca lokalnie w Docker,
wykorzystująca chmurę (Vertex AI) tylko do wywołań modeli (LLM + embeddery).

**Zakres modalności:**
- sensory liczbowe (temperatura, ciśnienie, wiatr, wilgotność, opady) — IMGW + Open-Meteo
- obrazy radaru (PNG mapy odbić) — RainViewer
- obrazy satelitarne (true color MODIS / VIIRS) — NASA GIBS WMTS
- tekst (ostrzeżenia meteo + auto-opisy stanu pogody) — IMGW warnings + generator

**Co robi aplikacja:**
- Q&A naturalne: "*Gdzie teraz pada najmocniej w Polsce?*"
- Q&A historyczne: "*Czy 1 maja były burze nad Mazowszem?*"
- Q&A obrazem: upload klatki radaru → "*co to za zjawisko, gdzie i kiedy podobne wystąpiło?*"
- Wizualizacje: tabele odczytów, wykresy szeregów czasowych, galeria klatek z cytowaniem źródła

---

## 2. Stack (zweryfikowany w dokumentacji ADK + Vertex AI)

| Warstwa | Komponent | Lokalizacja |
|---|---|---|
| LLM (router + synteza) | `gemini-2.5-pro` | Vertex AI |
| LLM (captiony obrazów) | `gemini-2.5-flash` | Vertex AI (taniej, szybciej) |
| Embedding tekstu | `gemini-embedding-001` (3072 dim, max 2048 tok) | Vertex AI |
| Embedding multimodalny | `multimodalembedding@001` (1408 dim, max 32 tok tekstu) | Vertex AI |
| Vector DB | Qdrant (named vectors: `text_3072` + `mm_1408`) | Docker |
| Blob storage (obrazy) | MinIO (S3-compatible, bucket `weather-rag-raw`) | Docker |
| Sensor time series + metadata | MariaDB | Docker |
| GUI bazy | phpMyAdmin (lub Adminer) | Docker, profil `admin` |
| Worker (scheduler + fetchery + embedding) | Python + APScheduler | Docker |
| App | Streamlit + ADK Runner (streaming async) | Docker |
| Auth do Vertex AI | Service Account JSON (mount `secrets/*.json` → `/gcp/sa-key.json`) | host → kontenery |

**Decyzje świadomie odrzucone:**
- Vertex AI Vector Search (drogi endpoint 24/7) → Qdrant lokalnie
- Cloud Run / Cloud Scheduler / Pub/Sub → docker-compose + APScheduler
- PostgreSQL + TimescaleDB → MariaDB (znajomy ekosystem, skala wystarczy)
- Redis pub/sub → niepotrzebne (worker = scheduler + embedder w jednym procesie)
- Jaeger/Prometheus/Grafana → `adk web` daje tracing w devie, na prod logi JSON wystarczą
- Caddy reverse proxy → na MVP dostęp przez `localhost:8501`
- ADK Visual Builder → trzymamy się czystego Pythona

---

## 3. Architektura

```
┌──────────────────────────────────────────────────────────────────┐
│                    docker-compose network                        │
│                                                                  │
│   ┌──────────┐                                                  │
│   │  worker  │  APScheduler in-process                          │
│   │          │  - co 10 min: RainViewer (radar PNG)             │
│   │          │  - co 15 min: IMGW synop (sensory)               │
│   │          │  - co 30 min: IMGW warnings (tekst)              │
│   │          │  - co 1 h:    NASA GIBS satellite (JPG)         │
│   │          │  - po fetchu: caption + embed + upsert           │
│   └─┬──┬──┬──┘                                                  │
│     │  │  │                                                     │
│     ▼  ▼  ▼                                                     │
│   ┌──────┐  ┌────────┐  ┌────────┐                              │
│   │minio │  │mariadb │  │qdrant  │                              │
│   │ PNG  │  │sensors │  │vectors │                              │
│   │      │  │+ meta  │  │ named  │                              │
│   └──┬───┘  └───┬────┘  └───┬────┘                              │
│      │          │           │                                    │
│      └──────────┼───────────┘                                    │
│                 ▼                                                │
│         ┌──────────────────────────────┐                        │
│         │           app                │                        │
│         │  Streamlit + ADK Runner      │                        │
│         │  weather_router (Gemini 2.5) │                        │
│         │  ├─ sensor_agent             │                        │
│         │  ├─ radar_agent              │                        │
│         │  ├─ satellite_agent          │                        │
│         │  └─ warnings_agent           │                        │
│         └────────────┬─────────────────┘                        │
└──────────────────────┼──────────────────────────────────────────┘
                       │
                       ▼
                ┌─────────────┐
                │  Vertex AI  │  ← jedyna chmura (pay-per-call)
                │  - Gemini   │
                │  - embed×2  │
                └─────────────┘
```

### Architektura agentów (ADK)

```
            User query (Streamlit)
                     │
                     ▼
        ┌──────────────────────────┐
        │   weather_router (root)  │  Gemini 2.5 Pro
        │   LLM-driven delegation  │  decyduje przez transfer_to_agent()
        │   sub_agents=[...]       │  syntezuje odpowiedź końcową
        └────┬──────┬──────┬──────┬┘
             │      │      │      │
             ▼      ▼      ▼      ▼
        sensor   radar  satel.  warn.   sub-agenty (LlmAgent)
        _agent  _agent  _agent  _agent

        tools:  tools:  tools:  tools:   funkcje Pythona
        - live  - live  - live  - live   z docstringami
        - srch  - srch  - srch  - srch
        - plot  - frame - frame
```

**Wzorzec routingu:** LLM-driven delegation. Router czyta `description` każdego sub-agenta
i sam wywołuje `transfer_to_agent("nazwa")`. Nie ma sztywnego routingu w kodzie.

**Komunikacja:** shared session state przez `output_key` każdego sub-agenta.

---

## 4. Struktura repo

```
weather-rag/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.override.yml      # dev (live reload, debug ports)
├── pyproject.toml
├── README.md
├── PLAN.md                          # ten plik
│
├── deploy/
│   ├── Dockerfile.worker
│   └── Dockerfile.app
│
├── infra/
│   └── sql/
│       └── init.sql                 # MariaDB schema
│
├── data/                            # docker volumes
│   ├── qdrant/
│   ├── minio/
│   └── mariadb/
│
├── src/
│   ├── config.py                    # pydantic-settings, jeden Settings
│   ├── schemas.py                   # Pydantic: SensorReading, RadarFrame, ...
│   │
│   ├── fetchers/                    # czyste funkcje (no side effects)
│   │   ├── __init__.py
│   │   ├── imgw.py
│   │   ├── rainviewer.py
│   │   ├── nasa_gibs.py
│   │   └── openmeteo.py
│   │
│   ├── storage/                     # wrappery na backendy
│   │   ├── __init__.py
│   │   ├── qdrant_store.py
│   │   ├── minio_store.py
│   │   └── mariadb_store.py
│   │
│   ├── pipeline/                    # caption + embed + upsert
│   │   ├── __init__.py
│   │   ├── caption.py               # gemini-2.5-flash → opis obrazu
│   │   ├── embed_text.py            # gemini-embedding-001
│   │   ├── embed_mm.py              # multimodalembedding@001
│   │   └── upsert.py
│   │
│   ├── worker/                      # entrypoint kontenera worker
│   │   ├── __init__.py
│   │   ├── scheduler.py             # APScheduler, cron triggery
│   │   └── handlers.py              # fetch → store → embed → upsert
│   │
│   ├── agents/                      # konwencja ADK: każdy agent w osobnym pakiecie
│   │   ├── __init__.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── search.py            # qdrant retrieval per modalność
│   │   │   ├── live.py              # świeże dane on-demand
│   │   │   └── plot.py              # plotly wykresy
│   │   ├── sensor_agent/
│   │   │   ├── __init__.py          # from . import agent
│   │   │   └── agent.py             # LlmAgent definition
│   │   ├── radar_agent/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── satellite_agent/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── warnings_agent/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   └── weather_router/
│   │       ├── __init__.py
│   │       └── agent.py             # root agent z sub_agents=[...]
│   │
│   └── app/                         # entrypoint kontenera app
│       ├── __init__.py
│       └── streamlit_app.py
│
└── tests/
    ├── unit/
    │   ├── test_fetchers.py
    │   ├── test_storage.py
    │   └── test_pipeline.py
    └── integration/
        └── test_e2e.py
```

---

## 5. Plan realizacji — 4 batche × 3 kroki

Każdy batch kończy się checkpointem: testem manualnym/automatycznym + zatwierdzeniem
przed kontynuacją.

### Batch 1 — Fundament

**Krok 1. Bootstrap repo + docker-compose**
- `pyproject.toml` (zależności: `google-adk`, `google-genai`, `google-cloud-aiplatform`,
  `vertexai`, `streamlit`, `qdrant-client`, `boto3`, `mariadb`, `sqlalchemy`,
  `apscheduler`, `requests`, `pydantic-settings`, `pillow`, `plotly`, `structlog`,
  `pytest`)
- `.env.example` z wszystkimi zmiennymi (GCP project, SA key path, MinIO/MariaDB credentials)
- `.gitignore` (`.env`, `data/`, `__pycache__`, `.venv`, `*.parquet` jeśli kiedyś)
- `docker-compose.yml` z 4 infra: `qdrant`, `minio`, `mariadb`, `phpmyadmin` (profil `admin`)
- `infra/sql/init.sql`: tabele `sensor_readings`, `text_chunks`, `images`, `warnings`,
  `fetch_log`, indeksy, klucze
- **Smoke test:** `docker compose up qdrant minio mariadb` → `mysql -h... -e 'SHOW TABLES'`,
  `curl localhost:6333/collections`, `mc alias set local`

**Krok 2. Konfiguracja + storage abstraction**
- `src/config.py`: klasa `Settings(BaseSettings)` — jedno miejsce na wszystkie env
- `src/schemas.py`: Pydantic modele dla każdej modalności + `RetrievalResult`
- `src/storage/qdrant_store.py`: init kolekcji `radar`, `satellite`, `text` z **named
  vectors** (`text_3072`, `mm_1408`), search/upsert wrappery
- `src/storage/minio_store.py`: put/get obrazów, presigned URL
- `src/storage/mariadb_store.py`: SQLAlchemy ORM, bulk insert, query helpers
- **Smoke test:** skrypt `scripts/smoke_storage.py` — wstawia 1 sample do każdego
  store'a, czyta z powrotem

**Krok 3. Fetchery**
- `src/fetchers/imgw.py`: `fetch_synop()`, `fetch_warnings()` → list[Pydantic]
- `src/fetchers/rainviewer.py`: `fetch_radar_frames(area="poland", n=13)` → list[bytes+meta]
- `src/fetchers/nasa_gibs.py`: `fetch_tile(layer, target_date, ...)` → SatelliteFrameRaw
- `src/fetchers/openmeteo.py`: `fetch_forecast(cities)` → list[Pydantic]
- Każdy fetcher: czysta funkcja, błędy = wyjątki, retry policy w wywołującym
- **Test:** `pytest tests/unit/test_fetchers.py` — mockowane requests, sprawdza modele

**Checkpoint Batch 1:**
- `docker compose up` startuje 3 infra kontenery
- Storage layer pisze i czyta z każdego backendu
- Fetchery zwracają poprawne modele
- → Demo: notebook lub skrypt `scripts/demo_batch1.py` pobiera dane i zapisuje do storów
- **Pytanie do użytkownika: lecimy dalej?**

---

### Batch 2 — Pipeline danych

**Krok 4. Pipeline captioningu i embeddingów**
- `src/pipeline/caption.py`: `caption_image(image_bytes) -> {short, long}` przez
  Gemini 2.5 Flash, `short` ≤ 25 słów (limit `multimodalembedding@001`),
  `long` ≤ 100 słów (do prezentacji w UI)
- `src/pipeline/embed_text.py`: `embed_documents(texts)` z `RETRIEVAL_DOCUMENT`,
  `embed_query(text)` z `RETRIEVAL_QUERY`
- `src/pipeline/embed_mm.py`: `embed_image_with_caption(img_bytes, caption_short)`
  → 1408d wektor; `embed_text_for_mm(text)` → 1408d (do cross-modal query)
- `src/pipeline/upsert.py`: formatuje `PointStruct` z dwoma named vectors, bulk upsert
- **Test:** integracyjny — jeden realny obraz przelatuje całość, kończy w Qdrant
  z dwoma wektorami i pełnym payloadem

**Krok 5. Worker container — scheduler + handlers**
- `src/worker/handlers.py`: 4 handlery (`handle_radar()`, `handle_imgw_synop()`,
  `handle_warnings()`, `handle_satellite()`) — każdy idempotentny, deterministyczny `id`
  (hash z timestamp+źródło)
- `src/worker/scheduler.py`: `BlockingScheduler` + cron decorators na każdy handler,
  proper logging, graceful shutdown (`SIGTERM`)
- `deploy/Dockerfile.worker`: Python 3.12-slim, `pip install -e .`,
  `CMD python -m src.worker.scheduler`
- Dodanie usługi `worker` do `docker-compose.yml` z mount `~/.config/gcloud`
- **Test:** `docker compose up worker` na 30 minut → sprawdzenie że MariaDB ma świeże
  rekordy, MinIO ma PNG-i, Qdrant ma wektory

**Krok 6. Bootstrap historyczny + idempotentność**
- `scripts/backfill.py`: jednorazowy skrypt który ściąga ostatnie X dni gdzie się da
  (Open-Meteo archive ma 80+ lat, IMGW tylko bieżące, więc realnie ~7 dni IMGW
  od momentu uruchomienia, satelita/radar od chwili startu workera)
- Mechanizm idempotentności: PRIMARY KEY na `(source, external_id)`,
  `INSERT ... ON DUPLICATE KEY UPDATE` w MariaDB, `upsert` w Qdrant
- Logowanie do `fetch_log` (kiedy ostatnio, ile rekordów, błędy)
- **Test:** dwukrotne uruchomienie backfilla nie tworzy duplikatów

**Checkpoint Batch 2:**
- Pełen pipeline działa autonomicznie (worker pobiera, embeduje, upsertuje)
- Idempotentny — restart bez duplikatów
- MariaDB ma sensor_readings, MinIO ma PNG-i, Qdrant ma wektory z named pairs
- → Demo: po 1h działania workera mamy realny dataset
- **Pytanie do użytkownika: lecimy dalej?**

---

### Batch 3 — Agenci

**Krok 7. Tools dla agentów**
- `src/agents/tools/search.py`:
  - `search_text_chunks(query: str, k=5) -> list[dict]` — text_3072 retrieval
  - `search_radar_by_text(query: str, k=5) -> list[dict]` — cross-modal (mm_1408 z
    embedowanego tekstu)
  - `search_radar_by_image(image_bytes, k=5) -> list[dict]` — image-to-image
  - `search_satellite_by_text(query: str, k=5)`
  - `search_satellite_by_image(image_bytes, k=5)`
  - `search_warnings(query: str, k=5)`
- `src/agents/tools/live.py`:
  - `get_current_synop(station: str | None = None) -> dict`
  - `get_current_warnings() -> list[dict]`
  - `get_latest_radar_frame() -> dict` (URL do MinIO + caption)
- `src/agents/tools/plot.py`:
  - `plot_station_timeseries(station, variable, start, end) -> base64_png`
- Każdy tool: docstring (ADK używa do prompt LLM), typy, czyste funkcje
- **Test:** unit, mockowane storage; sprawdzenie że ADK poprawnie introspectuje sygnatury

**Krok 8. Sub-agenty (4 specjalistyczne LlmAgent)**
- `src/agents/sensor_agent/agent.py`:
  ```python
  sensor_agent = LlmAgent(
      name="sensor_agent",
      model="gemini-2.5-pro",
      description="Specjalista od liczbowych odczytów ze stacji synoptycznych IMGW...",
      instruction="...",
      tools=[get_current_synop, search_text_chunks, plot_station_timeseries],
      output_key="sensor_findings",
  )
  ```
- Analogicznie `radar_agent` (live frame, search by text/image), `satellite_agent`,
  `warnings_agent`
- Krytyczne: **dobre `description`** — to po nich router będzie wybierał
- **Test:** każdy sub-agent uruchomiony osobno przez `adk run agents.sensor_agent`
  z 3 testowymi pytaniami

**Krok 9. Router agent**
- `src/agents/weather_router/agent.py`:
  ```python
  weather_router = LlmAgent(
      name="weather_router",
      model="gemini-2.5-pro",
      description="Asystent pogodowy. Routuje do specjalistów i syntezuje odpowiedź.",
      instruction="""...polskiego asystenta...4 sub-agenci...
                     1. Przeanalizuj pytanie. 2. Deleguj. 3. Syntezuj.
                     4. Cytuj źródła. 5. Dla pytań z obrazem → radar/satelita.""",
      sub_agents=[sensor_agent, radar_agent, satellite_agent, warnings_agent],
  )
  ```
- **Test:** `adk web` lokalnie + golden queries:
  1. "*Jaka teraz temperatura w Warszawie?*" → tylko sensor_agent
  2. "*Gdzie pada w Polsce?*" → radar_agent + sensor_agent
  3. "*Czy są ostrzeżenia?*" → warnings_agent
  4. "*Pokaż pogodę w Krakowie z 1 maja*" → sensor_agent (history)
  5. Upload PNG radaru: "*co to za zjawisko?*" → radar_agent

**Checkpoint Batch 3:**
- Każdy sub-agent działa samodzielnie
- Router poprawnie routuje 5/5 testowych pytań
- `adk web` pokazuje czytelny trace decyzji routera
- → Demo: live test w `adk web` 5 zapytaniami
- **Pytanie do użytkownika: lecimy dalej?**

---

### Batch 4 — App + finalizacja

**Krok 10. Streamlit app + ADK Runner streaming**
- `src/app/streamlit_app.py`:
  - Sidebar: status danych (ostatni fetch z `fetch_log`), wybór modelu (pro/flash)
  - Main: chat history + `st.chat_input` + `st.file_uploader` (obraz do query)
  - Streaming odpowiedzi: `runner.run_async()` → `st.write_stream(...)`
  - Panel boczny: galeria zwróconych klatek (presigned URL z MinIO),
    wykres plotly z sensor_agent, lista cytowań
- `Runner(agent=weather_router, app_name="weather-rag", session_service=InMemorySessionService())`
  trzymany w `st.session_state` per użytkownik
- `deploy/Dockerfile.app`: Streamlit + ADK + porty + healthcheck
- Dodanie `app` do `docker-compose.yml` z mount gcloud
- **Test:** `docker compose up` wszystkich, `http://localhost:8501`, ręczne przejście
  5 testowych zapytań

**Krok 11. End-to-end testy + golden queries**
- `tests/integration/test_e2e.py`: testy które uderzają w prawdziwy Qdrant/MariaDB/
  MinIO (z `docker-compose.test.yml`), mockują tylko Vertex AI (drogie)
- 8-10 golden queries z asercjami:
  - który sub-agent powinien być wywołany (assert na trace)
  - czy odpowiedź zawiera kluczowe słowa
  - czy zwrócone obrazy istnieją
- Smoke test deployu: `make smoke` — odpala compose, czeka 60s, robi curl + zamyka
- **Test:** CI-style pętla, wszystkie zielone

**Krok 12. README + demo + finalizacja**
- `README.md`:
  - one-liner: `cp .env.example .env && gcloud auth ... && docker compose up`
  - Diagram architektury (mermaid)
  - Lista sub-agentów + ich domena
  - Lista tools per agent
  - 5-10 przykładowych pytań z wynikami
  - Sekcja "produkcja" — co się zmienia w cloud (Vector Search / Cloud Run)
- `Makefile`: `make up`, `make down`, `make seed`, `make test`, `make logs`, `make web`
  (`adk web` na agentach do debug)
- Screenshoty UI + tracingu z `adk web` do dokumentacji projektu
- Wycięcie zbędnych plików, formatowanie (`ruff`, `mypy --strict` na kluczowych
  modułach)

**Checkpoint Batch 4:**
- Pełna apka działa od `docker compose up` do odpowiedzi z cytowaniami
- Streaming UI, multimodal upload, galeria, wykresy
- Testy zielone, README kompletne, screenshoty zrobione
- → Demo: pełen flow, 5-10 zapytań, prezentacja architektury
- **Projekt gotowy do oddania.**

---

## 6. Konwencje

**Naming:**
- pliki/moduły: `snake_case`
- klasy: `PascalCase`
- agenci: nazwa pakietu = nazwa agenta = `name=` w `LlmAgent` (`sensor_agent`, ...)

**Auth:**
- Service account JSON w `secrets/sa-key.json` (gitignorowany katalog)
- Mount w docker-compose: `${GOOGLE_SA_KEY_FILE}:/gcp/sa-key.json:ro`
- W kontenerze: `GOOGLE_APPLICATION_CREDENTIALS=/gcp/sa-key.json`
- `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION=us-central1`

**Konfiguracja:**
- Wszystko przez env, walidowane Pydantic Settings przy starcie
- `.env` lokalnie, `docker-compose.yml` przekazuje przez `env_file`
- Brak hardcode'ów URL-i / kluczy w kodzie

**Idempotentność:**
- Deterministyczne `id` = hash(`source` + `external_id`) dla każdego fetchowanego
  obiektu
- DB constraints (UNIQUE) + `ON DUPLICATE KEY UPDATE`
- Qdrant `upsert` (nie `insert`)

**Logging:**
- `structlog` JSON-format na stdout
- Każdy handler/tool/agent loguje na początku i końcu z `duration_ms` i
  `record_count`

**Testy:**
- Unit (`tests/unit/`) — mockowane storage i Vertex
- Integracja (`tests/integration/`) — realne Qdrant/MariaDB/MinIO przez
  `docker-compose.test.yml`, mockowane Vertex
- E2E (manual) — pełna apka, realny Vertex

**Dependency management:**
- `pyproject.toml` z lockfile (`uv.lock` lub `poetry.lock`)
- Pinowane wersje wszystkich Google packages (ADK jest pre-1.0, API się rusza)

---

## 7. Decyzje architektoniczne (skrót)

| Decyzja | Powód |
|---|---|
| Qdrant zamiast Vector Search | Free, lokalnie, named vectors dla cross-modal w jednym point |
| MariaDB zamiast Postgres+Timescale | Skala wystarczy, znajomy ekosystem |
| Worker = scheduler + embedder | Mała skala, prostsze niż Redis+osobne kontenery |
| MinIO zamiast lokalnego FS | API S3-compatible — kod identyczny dla cloud przy migracji |
| Gemini 2.5 Pro dla routera, Flash dla captionów | 10× tańsze captiony bez utraty jakości |
| `gemini-embedding-001` (3072d) dla tekstu | SOTA, multilingual (PL OK), 2048 tok limit |
| `multimodalembedding@001` (1408d) dla obrazów | Cross-modal text↔image w jednej przestrzeni |
| LLM-driven delegation (nie sztywny routing) | Łatwo dodać agenta, router się dostosuje |
| Streamlit zamiast custom React | Szybko, file upload + chat out-of-the-box |
| `adk web` zamiast Jaegera | Wbudowane w ADK, zero infrastruktury |

---

## 8. Ryzyka i mitygacje

| Ryzyko | Mitygacja |
|---|---|
| ADK pre-1.0, API się może zmienić | Pin `google-adk==X.Y.Z` |
| `multimodalembedding@001` limit 32 tok tekstu | Captiony krótkie ≤ 25 słów; długie opisy w metadata |
| RainViewer trzyma tylko 2h archiwum | Worker fetchuje co 10 min, własne archiwum w MinIO |
| IMGW publikuje nieregularnie | Best-effort, brakujące godziny są OK |
| Captioning Gemini wolny | Batch + asyncio + Flash zamiast Pro |
| Limity quota Vertex AI | Monitor `fetch_log`, prosty rate limiting w workerze |
| Lokalny dysk (volumes) wypełni się | Lifecycle policy: kasujemy obrazy >30 dni |
| Auth ADC wygasa | `gcloud auth application-default login` przed sesją (dokumentacja w README) |

---

## 9. Koszty (estymacja)

- Infra (Docker lokalnie): **$0**
- Vertex AI Gemini 2.5 Pro: ~$3.50/1M tok in, ~$10.50/1M tok out
- Vertex AI Gemini 2.5 Flash (captiony): ~$0.30/1M tok in, ~$2.50/1M tok out
- Vertex AI `gemini-embedding-001`: ~$0.000025/tok
- Vertex AI `multimodalembedding@001`: ~$0.0002/obraz

**Realne miesięczne (~100 zapytań/dzień + 24/7 worker):** **$5-15/mc**

Podczas demo / prezentacji obrony: pomijalne (dziesiątki centów).
