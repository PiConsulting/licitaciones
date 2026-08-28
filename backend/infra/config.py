from functools import lru_cache
from pathlib import Path

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
    local_blob_storage_path: str = Field(
        default=_DEFAULT_LOCAL_BLOB_STORAGE_PATH,
        alias="LOCAL_BLOB_STORAGE_PATH",
    )
    azure_blob_connection_string: str = Field(default="", alias="AZURE_BLOB_CONNECTION_STRING")
    azure_blob_container_name: str = Field(default="", alias="AZURE_BLOB_CONTAINER_NAME")
    azure_document_intelligence_endpoint: str = Field(
        default="", alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"
    )
    azure_document_intelligence_key: str = Field(
        default="", alias="AZURE_DOCUMENT_INTELLIGENCE_KEY"
    )
    document_intelligence_timeout_seconds: int = Field(
        default=60, alias="DOCUMENT_INTELLIGENCE_TIMEOUT_SECONDS"
    )
    document_intelligence_retry_attempts: int = Field(
        default=3, alias="DOCUMENT_INTELLIGENCE_RETRY_ATTEMPTS"
    )
    embedding_dimensions: int = Field(default=3072, alias="EMBEDDING_DIMENSIONS")
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_chat_deployment: str = Field(default="", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_embedding_deployment: str = Field(
        default="",
        alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )
    azure_openai_api_version: str = Field(default="", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_embeddings_batch_size: int = Field(
        default=16, alias="AZURE_OPENAI_EMBEDDINGS_BATCH_SIZE"
    )
    azure_openai_retry_attempts: int = Field(default=3, alias="AZURE_OPENAI_RETRY_ATTEMPTS")

    # Extraction configuration
    extraction_max_concurrency: int = Field(
        default=4,
        alias="EXTRACTION_MAX_CONCURRENCY",
        description="Máxima concurrencia para extracción de páginas",
    )
    extraction_top_k: int = Field(
        default=25,
        alias="EXTRACTION_TOP_K",
        description="Número de chunks a recuperar por categoría (default si glossary no especifica)",
    )
    extraction_max_context_tokens: int = Field(
        default=16000,
        alias="EXTRACTION_MAX_CONTEXT_TOKENS",
        description=(
            "Límite de tokens de contexto para extracción, medido con el tokenizer real "
            "del modelo cuando está disponible (ver `_count_tokens`, cae a conteo por "
            "palabras si no). FIX (2026-08-13): subido de 8000 a 16000 -- categorías con "
            "muchos hechos discretos en el mismo pliego (ej. `plazos_clave` con muchos "
            "hitos, `garantias` con varias cláusulas) podían perder chunks relevantes ya "
            "recuperados por descarte silencioso de presupuesto (ver "
            "`extraction_chunks_dropped_token_budget` en los logs). Este límite aplica "
            "por categoría, no por análisis completo, así que el costo adicional es "
            "acotado incluso en el peor caso."
        ),
    )

    # Chunking configuration
    chunking_max_table_tokens: int = Field(
        default=500,
        alias="CHUNKING_MAX_TABLE_TOKENS",
        description="Máximo de tokens por chunk de tabla (aprox). Tablas más grandes se dividen en múltiples chunks.",
    )

    
    chunking_use_semantic_classification: bool = Field(
        default=False,
        alias="CHUNKING_USE_SEMANTIC_CLASSIFICATION",
        description=(
            "Si es true, los chunks sin categoría por heading ni por "
            "keywords del glosario se clasifican por similitud coseno "
            "contra la definición semántica de cada categoría "
            "(category_definitions.json), en vez de quedar sin categoría."
        ),
    )

    
    use_shared_candidate_pool: bool = Field(
        default=False,
        alias="USE_SHARED_CANDIDATE_POOL",
        description=(
            "Si es true, setup_node puebla un candidate pool compartido de "
            "alto recall y cada categoría lo reusa cuando alcanza el "
            "purity_rate mínimo, evitando su round-trip específico a Azure."
        ),
    )
    shared_candidate_pool_top_k: int = Field(
        default=60,
        alias="SHARED_CANDIDATE_POOL_TOP_K",
        description="Cuántos chunks trae la query global de setup_node para el candidate pool compartido.",
    )
    shared_candidate_pool_purity_threshold: float = Field(
        default=0.5,
        alias="SHARED_CANDIDATE_POOL_PURITY_THRESHOLD",
        description=(
            "purity_rate mínimo (fracción de chunks de la categoría target, "
            "0-1) que el pool compartido, ya boosteado para una categoría, "
            "tiene que alcanzar para usarse sin disparar la query específica "
            "de esa categoría. Punto de partida razonable, no calibrado "
            "contra datos reales todavía -- calibrar con el dataset de "
            "evaluación (plan RAG v2, sección 6) antes de confiar en él para "
            "producción."
        ),
    )
    query_expansion_use_semantic_definition: bool = Field(
        default=False,
        alias="QUERY_EXPANSION_USE_SEMANTIC_DEFINITION",
        description=(
            "Si es true, run_extractor() enriquece la query que cada rama "
            "vectoriza para el vector search con la definición semántica "
            "completa de la categoría (category_definitions.json, misma "
            "fuente que usa la Fase 2 / 4.3 para clasificación de chunks), "
            "en vez de usar solo la frase corta que arma cada extractor. La "
            "query de keywords para BM25 (build_keyword_query) no cambia. "
            "Fase 4 del plan RAG v2, sección 4.4."
        ),
    )

    # Highlight configuration
    highlight_citation_min_length: int = Field(
        default=3,
        alias="HIGHLIGHT_CITATION_MIN_LENGTH",
        description="Longitud mínima de citation para calcular highlights (caracteres)",
    )

    # Historia 22.5 (retoma el diseño nunca implementado de la Story 2.18):
    # reranking semántico local con cross-encoder, entre la fusión RRF
    # (Historia 22.4) y el boost por categoría de chunk_retrieval.py.
    rag_reranking_enabled: bool = Field(default=False, alias="RAG_RERANKING_ENABLED")
    rag_reranking_model: str = Field(
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        alias="RAG_RERANKING_MODEL",
        description=(
            "Modelo cross-encoder de sentence-transformers, corre 100% local "
            "(CPU). Multilingüe (incluye español), liviano (~118M params) "
            "para latencia aceptable sobre pools de ~30-90 candidatos."
        ),
    )
    rag_reranking_timeout_seconds: float = Field(
        default=5.0,
        alias="RAG_RERANKING_TIMEOUT_SECONDS",
        description="Si el reranking no termina en este tiempo, se descarta y se usa el orden RRF (AC3).",
    )

    # FIX: Dead code eliminado (#1, #2, #3) - campos legacy de adaptadores locales:
    # - cohere_api_key, cohere_model (solo para CohereAdapter local)
    # - sentence_transformers_model, chroma_persist_directory (solo para Chroma local)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    azure_sdk_log_level: str = Field(default="WARNING", alias="AZURE_SDK_LOG_LEVEL")

    @property
    def is_development(self) -> bool:
        """Development profile: local machine execution for testing."""
        return self.app_env.strip().lower() in {"development", "dev"}

    @property
    def is_production(self) -> bool:
        """Production mode: cloud resources only."""
        return self.app_env.strip().lower() == "production"

    def cloud_required_variables(self) -> dict[str, str]:
        return {
            "AZURE_BLOB_CONNECTION_STRING": self.azure_blob_connection_string,
            "AZURE_BLOB_CONTAINER_NAME": self.azure_blob_container_name,
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": self.azure_document_intelligence_endpoint,
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": self.azure_document_intelligence_key,
            "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
            "AZURE_OPENAI_DEPLOYMENT": self.azure_openai_chat_deployment,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": self.azure_openai_embedding_deployment,
            "AZURE_OPENAI_API_VERSION": self.azure_openai_api_version,
        }

    def missing_cloud_required_variables(self) -> list[str]:
        required = self.cloud_required_variables()
        return [name for name, value in required.items() if not str(value).strip()]

    def validate_cloud_configuration(self) -> None:
        missing = self.missing_cloud_required_variables()
        if missing:
            raise RuntimeError(
                "Configuración cloud incompleta. Variables faltantes: " + ", ".join(sorted(missing))
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
