from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root (repo/.env) regardless of CWD.
# Keep backend/.env as a fallback for backward compatibility.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (
    _PROJECT_ROOT / ".env",
    _BACKEND_ROOT / ".env",
)
_DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/licitaciones"
_DEFAULT_LOCAL_BLOB_STORAGE_PATH = str(_PROJECT_ROOT / "local_blob_storage")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    app_env: str = Field(default="", alias="APP_ENV")
    database_url: str = Field(
        default=_DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
    )
    secret_key: str = Field(
        default="replace-with-32-byte-random-secret-value",
        alias="SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, alias="JWT_EXPIRATION_HOURS")
    use_local_adapters: bool = Field(default=True, alias="USE_LOCAL_ADAPTERS")
    local_blob_storage_path: str = Field(
        default=_DEFAULT_LOCAL_BLOB_STORAGE_PATH,
        alias="LOCAL_BLOB_STORAGE_PATH",
    )
    azure_blob_connection_string: str = Field(default="", alias="AZURE_BLOB_CONNECTION_STRING")
    azure_blob_container_name: str = Field(default="", alias="AZURE_BLOB_CONTAINER_NAME")
    azure_document_intelligence_endpoint: str = Field(default="", alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    azure_document_intelligence_key: str = Field(default="", alias="AZURE_DOCUMENT_INTELLIGENCE_KEY")
    document_intelligence_timeout_seconds: int = Field(default=60, alias="DOCUMENT_INTELLIGENCE_TIMEOUT_SECONDS")
    document_intelligence_retry_attempts: int = Field(default=3, alias="DOCUMENT_INTELLIGENCE_RETRY_ATTEMPTS")
    azure_search_endpoint: str = Field(default="", alias="AZURE_SEARCH_ENDPOINT")
    azure_search_key: str = Field(default="", alias="AZURE_SEARCH_KEY")
    azure_search_index_name: str = Field(default="", alias="AZURE_SEARCH_INDEX_NAME")
    azure_search_embedding_dimensions: int = Field(default=3072, alias="AZURE_SEARCH_EMBEDDING_DIMENSIONS")
    azure_search_upload_batch_size: int = Field(default=1000, alias="AZURE_SEARCH_UPLOAD_BATCH_SIZE")
    azure_search_retry_attempts: int = Field(default=3, alias="AZURE_SEARCH_RETRY_ATTEMPTS")
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_chat_deployment: str = Field(default="", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_embedding_deployment: str = Field(
        default="",
        alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )
    azure_openai_api_version: str = Field(default="", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_embeddings_batch_size: int = Field(default=16, alias="AZURE_OPENAI_EMBEDDINGS_BATCH_SIZE")
    azure_openai_retry_attempts: int = Field(default=3, alias="AZURE_OPENAI_RETRY_ATTEMPTS")

    cohere_api_key: str = Field(default="", alias="COHERE_API_KEY")
    cohere_model: str = Field(default="command-r-plus", alias="COHERE_MODEL")

    sentence_transformers_model: str = Field(default="BAAI/bge-m3", alias="SENTENCE_TRANSFORMERS_MODEL")
    chroma_persist_directory: str = Field(
        default=str(_PROJECT_ROOT / "local_blob_storage" / "chroma"),
        alias="CHROMA_PERSIST_DIRECTORY",
    )

    markitdown_enabled: bool = Field(default=True, alias="MARKITDOWN_ENABLED")
    extraction_max_concurrency: int = Field(default=4, alias="EXTRACTION_MAX_CONCURRENCY")
    extraction_top_k: int = Field(default=25, alias="EXTRACTION_TOP_K")
    extraction_max_context_tokens: int = Field(default=12000, alias="EXTRACTION_MAX_CONTEXT_TOKENS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    persistence_mode: str = Field(default="sql", alias="PERSISTENCE_MODE")
    cosmos_endpoint: str = Field(default="", alias="COSMOS_ENDPOINT")
    cosmos_key: str = Field(default="", alias="COSMOS_KEY")
    cosmos_database: str = Field(default="", alias="COSMOS_DATABASE")
    cosmos_container: str = Field(default="", alias="COSMOS_CONTAINER")

    @property
    def is_development(self) -> bool:
        """Development profile: local machine execution for testing."""
        if self.app_env.strip().lower() in {"development", "dev"}:
            return True
        if self.app_env.strip().lower() == "production":
            return False
        return self.use_local_adapters

    @property
    def is_production(self) -> bool:
        return not self.is_development

    def persistence_mode_normalized(self) -> str:
        return (self.persistence_mode or "sql").strip().lower()

    def is_cosmos_temporal_mode(self) -> bool:
        return self.persistence_mode_normalized() == "cosmos_temporal"

    def is_cosmos_only_mode(self) -> bool:
        return self.persistence_mode_normalized() == "cosmos_only"

    def cloud_required_variables(self) -> dict[str, str]:
        required = {
            "AZURE_BLOB_CONNECTION_STRING": self.azure_blob_connection_string,
            "AZURE_BLOB_CONTAINER_NAME": self.azure_blob_container_name,
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": self.azure_document_intelligence_endpoint,
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": self.azure_document_intelligence_key,
            "AZURE_SEARCH_ENDPOINT": self.azure_search_endpoint,
            "AZURE_SEARCH_KEY": self.azure_search_key,
            "AZURE_SEARCH_INDEX_NAME": self.azure_search_index_name,
            "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
            "AZURE_OPENAI_DEPLOYMENT": self.azure_openai_chat_deployment,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": self.azure_openai_embedding_deployment,
            "AZURE_OPENAI_API_VERSION": self.azure_openai_api_version,
            "PERSISTENCE_MODE": self.persistence_mode,
        }

        mode = self.persistence_mode_normalized()
        if mode in {"cosmos", "dual_write", "cosmos_temporal", "cosmos_only"}:
            required.update(
                {
                    "COSMOS_ENDPOINT": self.cosmos_endpoint,
                    "COSMOS_KEY": self.cosmos_key,
                    "COSMOS_DATABASE": self.cosmos_database,
                    "COSMOS_CONTAINER": self.cosmos_container,
                }
            )
        return required

    def missing_cloud_required_variables(self) -> list[str]:
        required = self.cloud_required_variables()
        return [name for name, value in required.items() if not str(value).strip()]

    def validate_cloud_configuration(self) -> None:
        mode = self.persistence_mode_normalized()
        if mode not in {"sql", "cosmos", "dual_write", "cosmos_temporal", "cosmos_only"}:
            raise RuntimeError(
                "PERSISTENCE_MODE debe ser uno de: sql, cosmos, dual_write, cosmos_temporal, cosmos_only"
            )

        if mode not in {"cosmos_temporal", "cosmos_only", "cosmos"}:
            parsed = urlparse(self.database_url)
            host = (parsed.hostname or "").strip().lower()
            if host in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError(
                    "DATABASE_URL no puede apuntar a localhost en production. "
                    "Configura una base de datos remota."
                )

        missing = self.missing_cloud_required_variables()
        if missing:
            raise RuntimeError(
                "Configuración cloud incompleta. Variables faltantes: " + ", ".join(sorted(missing))
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
