from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project-root .env takes precedence; backend/.env kept as fallback for backward compatibility.
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

    # Concurrency defaults raised 2026-09-10 after measuring: 4/0/1 baseline ~102s -> 7/8/3 ~72s (-29% multi-doc).
    extraction_max_concurrency: int = Field(
        default=7,
        alias="EXTRACTION_MAX_CONCURRENCY",
        description="Máxima concurrencia para extracción (nodos de categoría en paralelo en el grafo).",
    )
    llm_max_concurrency: int = Field(
        default=8,
        alias="LLM_MAX_CONCURRENCY",
        description=(
            "Freno GLOBAL de llamadas al LLM en vuelo (Paso 1, plan "
            "rag-plan-latencia-2026-09-09). Cuenta la suma de todas las capas "
            "que se paralelizan (temas x documentos del map-reduce x "
            "síntesis), no una sola. 0 = sin límite. Semáforo en "
            "`llm_client.py::_call_llm`. Default 8 para acotar el pico real "
            "cuando `extraction_max_concurrency`/`mapreduce` están altos."
        ),
    )
    extraction_mapreduce_concurrency: int = Field(
        default=3,
        alias="EXTRACTION_MAPREDUCE_CONCURRENCY",
        description=(
            "Paso 2 (plan rag-plan-latencia-2026-09-09). Cuántas llamadas al "
            "LLM por documento corre en paralelo cada extractor map-reduce. "
            "1 = secuencial. > 1 paraleliza los documentos de un mismo tema "
            "(cada documento sigue siendo su propia llamada; nunca se fusionan). "
            "El tope real contra Azure lo pone LLM_MAX_CONCURRENCY."
        ),
    )
    synthesis_max_concurrency: int = Field(
        default=4,
        alias="SYNTHESIS_MAX_CONCURRENCY",
        description=(
            "Paso 5 (plan rag-plan-latencia-2026-09-09). Cuántas síntesis de "
            "categoría corre en paralelo `synthesize_node`. Cada categoría es "
            "una 2da llamada al LLM independiente (items ya mergeados -> "
            "narrativa); antes se hacían las 7-9 en serie. 1 = secuencial "
            "(comportamiento previo). El ensamblado sigue siendo determinista "
            "(orden de NARRATIVE_CATEGORIES) y el enriquecimiento de highlights "
            "queda fuera del pool. El tope real contra Azure lo pone "
            "LLM_MAX_CONCURRENCY."
        ),
    )
    rag_neighbor_expansion_enabled: bool = Field(
        default=False,
        alias="RAG_NEIGHBOR_EXPANSION_ENABLED",
        description=(
            "Expansión de vecinos en retrieval (2026-09-10). Tras el scoring "
            "híbrido, para cada chunk del top_k trae también sus vecinos "
            "posicionales (mismo documento, chunk_index +/- ventana) que ya "
            "estén en el pool recuperado, insertándolos junto al chunk que los "
            "trajo. Recupera enumeraciones partidas en chunks consecutivos "
            "(ej. 'Artículo 16.1: a) ... b) ... c) ...' partido en 7 chunks, "
            "el retrieval trae 3). Solo reordena el pool ya recuperado; no "
            "hace fetch a la DB. Default False."
        ),
    )
    rag_neighbor_expansion_window: int = Field(
        default=1,
        alias="RAG_NEIGHBOR_EXPANSION_WINDOW",
        description="Cuántos chunks a cada lado (chunk_index +/- N) considerar vecinos. 1 = solo adyacentes.",
    )
    rag_llm_judge_enabled: bool = Field(
        default=False,
        alias="RAG_LLM_JUDGE_ENABLED",
        description=(
            "Reranking por LLM-as-judge (experimental, 2026-09-10). Alternativa al "
            "cross-encoder: se le pasa al LLM el top-N de RRF + la definición de la "
            "categoría y devuelve relevancia 0-3 por chunk. +1 llamada barata por "
            "categoría (~$0.01 y ~+6s por pliego). Fallback seguro al orden RRF. "
            "Default False -- se activa solo para experimentar."
        ),
    )
    rag_llm_judge_window: int = Field(
        default=25,
        alias="RAG_LLM_JUDGE_WINDOW",
        description="Cuántos chunks del top de RRF se le mandan al juez LLM para reordenar.",
    )
    extraction_top_k: int = Field(
        default=25,
        alias="EXTRACTION_TOP_K",
        description="Número de chunks a recuperar por categoría (default si glossary no especifica)",
    )
    extraction_group_max_chunks: int = Field(
        default=15,
        alias="EXTRACTION_GROUP_MAX_CHUNKS",
        description=(
            "FIX (2026-09-11, diagnóstico de no-determinismo en garantías): tope de "
            "chunks por llamado al LLM DENTRO de un mismo documento. El map-reduce por "
            "documento (2026-08-21) evita 'lost in the middle' solo si el pliego tiene "
            "varios documentos -- uno de un solo documento sigue mandando el `top_k` "
            "completo de la categoría (hasta 35 en garantías) en un único llamado. "
            "Cuando un grupo supera este tope, `_split_oversized_groups` (item_merging.py) "
            "lo parte en varios llamados más chicos sobre tramos contiguos del documento "
            "(los chunks ya quedan ordenados por `chunk_index`, no por relevancia), y se "
            "mergean con la misma maquinaria de dedup que ya usa map-reduce entre "
            "documentos. <= 0 desactiva el split (comportamiento previo)."
        ),
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
    shared_candidate_pool_augment_on_roundtrip: bool = Field(
        default=False,
        alias="SHARED_CANDIDATE_POOL_AUGMENT_ON_ROUNDTRIP",
        description=(
            "Cuando el pool compartido NO alcanza el purity_threshold y la categoría "
            "hace igual su query específica: si es true (histórico) fusiona el pool con "
            "el resultado específico; si es false lo ignora y usa solo el resultado "
            "específico. Medido 2026-09-10: la fusión cuesta ~-0.021 de recall efectivo "
            "sin ahorrar el roundtrip. Default false para que el pool solo aporte cuando "
            "efectivamente reemplaza la query. (Aun así el pool compartido rinde poco: "
            "a purity_threshold 0.30 y sin merge el recall queda igual pero solo ~11% de "
            "los retrieval por categoría saltan el roundtrip, y hay que sumar la query "
            "del pool -- neto ~break-even. `use_shared_candidate_pool` sigue en false.)"
        ),
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

    highlight_citation_min_length: int = Field(
        default=3,
        alias="HIGHLIGHT_CITATION_MIN_LENGTH",
        description="Longitud mínima de citation para calcular highlights (caracteres)",
    )

    rag_reranking_enabled: bool = Field(
        default=False,
        alias="RAG_RERANKING_ENABLED",
        description=(
            "FIX (2026-09-08): default False tras medir con el dataset de evaluación. "
            "El guardrail que decidía cuándo saltear el reranking comparaba la variable "
            "equivocada (el pool crudo en vez de `rerank_window`, lo que en la práctica "
            "saltaba el reranking casi siempre); al corregirlo y medir el reranking "
            "REALMENTE corriendo, el recall efectivo de producción bajó en promedio "
            "(-0.010, con regresiones reales en identificacion_procedimiento, "
            "plazos_clave y riesgos) contra apagarlo. El modelo "
            "(`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) es multilingüe genérico, "
            "no afinado en español administrativo/legal, y el boost/penalty por "
            "categoría (calibrado con datos reales en esta misma sesión) le gana en la "
            "mayoría de los casos. El resto del fix (guardrail correcto, warm-up, "
            "timeout con margen) queda andando por si se prueba un modelo mejor "
            "(afinado en español/legal, o vía LLM-as-judge con Azure OpenAI) más adelante."
        ),
    )
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
        default=15.0,
        alias="RAG_RERANKING_TIMEOUT_SECONDS",
        description=(
            "Si el reranking no termina en este tiempo, se descarta y se usa el orden RRF (AC3). "
            "FIX (2026-09-08): subido de 5.0 -- medido en CPU real, ~0.045s/par en condiciones "
            "limpias pero con varianza real bajo carga concurrente (hasta ~0.09s/par observado, "
            "ver hallazgo de sesión); a 5.0s hasta pools de 70-90 candidatos (el tamaño normal de "
            "`rerank_window`) caían al fallback casi siempre. La extracción corre en "
            "BackgroundTasks (analysis/routes.py), no bloquea ningún request de usuario, así que "
            "hay margen real para priorizar que el reranking termine sobre recortarlo agresivo."
        ),
    )

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
