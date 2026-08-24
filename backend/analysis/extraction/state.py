from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """Estado compartido del pipeline de extracción."""

    analysis_id: str
    correlation_id: str
    max_concurrency: int

    plazos: list[dict[str, Any]]
    plazos_status: str

    objeto_alcance: list[dict[str, Any]]
    objeto_alcance_status: str

    garantias: list[dict[str, Any]]
    garantias_status: str

    requisitos_admisibilidad: list[dict[str, Any]]
    requisitos_admisibilidad_status: str

    causales: list[dict[str, Any]]
    causales_status: str

    anexos: list[dict[str, Any]]
    anexos_status: str

    documentos: list[dict[str, Any]]
    documentos_status: str

    criterios: list[dict[str, Any]]
    criterios_status: str

    restricciones: list[dict[str, Any]]
    restricciones_status: str

    cronograma: list[dict[str, Any]]
    cronograma_status: str

    identificacion: list[dict[str, Any]]
    identificacion_status: str

    riesgos: list[dict[str, Any]]
    riesgos_status: str

    presupuesto: dict[str, Any]
    presupuesto_status: str

    extracted_data: dict[str, Any]
    conflicts: list[dict[str, Any]]
    extraction_metadata: dict[str, Any]
    document_id_to_blob_path: dict[str, str]  # Para highlight pre-computado
    document_labels: dict[str, dict[str, Any]]

    # FASE 3 del plan RAG v2 (2026-08-24, sección 4.2): candidate pool
    # compartido entre las 9 ramas de extracción. `setup_node` lo puebla UNA
    # sola vez con una query de alto recall, sin boost de categoría, si
    # `USE_SHARED_CANDIDATE_POOL=true`. `_retrieve_with_category_priority`
    # (extractors/base.py) lo usa para evitar un round-trip a Azure por
    # categoría cuando el pool ya alcanza. Ausente o `[]` si el flag está
    # apagado o si la query global falló -- en ambos casos el retrieval por
    # categoría se comporta exactamente igual que antes de esta fase.
    global_candidates: list[dict[str, Any]]

    plazos_token_usage: dict[str, int]
    objeto_alcance_token_usage: dict[str, int]
    garantias_token_usage: dict[str, int]
    requisitos_admisibilidad_token_usage: dict[str, int]
    causales_token_usage: dict[str, int]
    anexos_token_usage: dict[str, int]
    documentos_token_usage: dict[str, int]
    criterios_token_usage: dict[str, int]
    restricciones_token_usage: dict[str, int]
    identificacion_token_usage: dict[str, int]
    cronograma_token_usage: dict[str, int]
    presupuesto_token_usage: dict[str, int]
    created_by: str | None
    db_session: Any
