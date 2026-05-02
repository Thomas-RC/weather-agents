-- Weather RAG schema (MariaDB 11.x)
-- Tworzony automatycznie przy pierwszym starcie kontenera mariadb.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ----------------------------------------------------------------------------
-- sensor_readings — odczyty ze stacji synoptycznych (IMGW + Open-Meteo)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source          VARCHAR(32)  NOT NULL,           -- 'imgw' | 'open-meteo'
    external_id     VARCHAR(128) NOT NULL,           -- deterministyczny hash
    station_id      VARCHAR(32)  NULL,
    station_name    VARCHAR(128) NULL,
    measured_at     DATETIME     NOT NULL,
    latitude        DECIMAL(9,5) NULL,
    longitude       DECIMAL(9,5) NULL,
    temperature_c   DECIMAL(5,2) NULL,
    pressure_hpa    DECIMAL(7,2) NULL,
    wind_speed_ms   DECIMAL(5,2) NULL,
    wind_dir_deg    SMALLINT     NULL,
    humidity_pct    DECIMAL(5,2) NULL,
    precipitation_mm DECIMAL(6,2) NULL,
    raw_json        JSON         NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_source_external (source, external_id),
    KEY idx_measured_at (measured_at),
    KEY idx_station (station_name, measured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- images — metadata klatek radaru i satelity
-- (faktyczny obraz lezy w MinIO, tu tylko metadata + lookup po vector_id)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS images (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    image_id        VARCHAR(128) NOT NULL,           -- = id punktu w Qdrant
    source          VARCHAR(32)  NOT NULL,           -- 'rainviewer' | 'owm-satellite'
    modality        VARCHAR(32)  NOT NULL,           -- 'radar' | 'satellite'
    minio_bucket    VARCHAR(128) NOT NULL,
    minio_key       VARCHAR(512) NOT NULL,
    captured_at     DATETIME     NOT NULL,
    bbox_north      DECIMAL(9,5) NULL,
    bbox_south      DECIMAL(9,5) NULL,
    bbox_east       DECIMAL(9,5) NULL,
    bbox_west       DECIMAL(9,5) NULL,
    zoom            TINYINT UNSIGNED NULL,
    tile_x          INT UNSIGNED NULL,
    tile_y          INT UNSIGNED NULL,
    caption_short   VARCHAR(512) NULL,               -- ≤25 słów (do mm-embed)
    caption_long    TEXT         NULL,               -- do prezentacji UI
    metadata_json   JSON         NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_image_id (image_id),
    KEY idx_captured (modality, captured_at),
    KEY idx_source (source, captured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- text_chunks — tekst do indeksu wektorowego (auto-opisy + ostrzeżenia)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS text_chunks (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    chunk_id        VARCHAR(128) NOT NULL,           -- = id punktu w Qdrant
    source          VARCHAR(64)  NOT NULL,           -- 'imgw-warnings' | 'auto-summary' | ...
    modality        VARCHAR(32)  NOT NULL DEFAULT 'text',
    content         TEXT         NOT NULL,
    valid_from      DATETIME     NULL,
    valid_to        DATETIME     NULL,
    metadata_json   JSON         NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_chunk_id (chunk_id),
    KEY idx_source_created (source, created_at),
    FULLTEXT KEY ft_content (content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- warnings — pełne ostrzeżenia IMGW (oddzielnie od text_chunks dla łatwego SQL)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warnings (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_id     VARCHAR(128) NOT NULL,
    source          VARCHAR(32)  NOT NULL DEFAULT 'imgw',
    level           VARCHAR(16)  NULL,               -- '1' | '2' | '3'
    phenomenon      VARCHAR(128) NULL,
    area            VARCHAR(255) NULL,
    valid_from      DATETIME     NULL,
    valid_to        DATETIME     NULL,
    content         TEXT         NULL,
    raw_json        JSON         NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_source_external (source, external_id),
    KEY idx_validity (valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- fetch_log — audyt uruchomień fetcherów / handlerów
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fetch_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source          VARCHAR(64)  NOT NULL,
    started_at      DATETIME     NOT NULL,
    ended_at        DATETIME     NULL,
    duration_ms     INT UNSIGNED NULL,
    records_count   INT          NULL,
    status          VARCHAR(16)  NOT NULL,           -- 'ok' | 'error' | 'partial'
    error_message   TEXT         NULL,
    PRIMARY KEY (id),
    KEY idx_source_started (source, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
