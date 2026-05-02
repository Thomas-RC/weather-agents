"""Centralna konfiguracja — czytana z env, walidowana Pydantic."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Vertex AI / Gemini
    google_cloud_project: str
    google_cloud_location: str = "us-central1"
    google_genai_use_vertexai: bool = True
    gemini_model_router: str = "gemini-2.5-pro"
    gemini_model_caption: str = "gemini-2.5-flash"
    gemini_text_embedding_model: str = "gemini-embedding-001"
    gemini_mm_embedding_model: str = "multimodalembedding@001"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_radar: str = "radar"
    qdrant_collection_satellite: str = "satellite"
    qdrant_collection_text: str = "text_chunks"

    # MinIO / S3
    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str = "http://localhost:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "weather-rag-raw"
    minio_secure: bool = False

    # MariaDB
    mariadb_host: str = "mariadb"
    mariadb_port: int = 3306
    mariadb_user: str
    mariadb_password: str
    mariadb_database: str = "weather_rag"

    # App
    app_log_level: str = "INFO"
    app_env: str = Field(default="dev", pattern="^(dev|staging|prod)$")

    @property
    def mariadb_url(self) -> str:
        """SQLAlchemy URL dla MariaDB (driver PyMySQL)."""
        return (
            f"mysql+pymysql://{self.mariadb_user}:{self.mariadb_password}"
            f"@{self.mariadb_host}:{self.mariadb_port}/{self.mariadb_database}"
            "?charset=utf8mb4"
        )

    @property
    def text_embedding_dim(self) -> int:
        return 3072

    @property
    def mm_embedding_dim(self) -> int:
        return 1408


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
