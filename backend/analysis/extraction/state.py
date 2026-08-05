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

    presupuesto: dict[str, Any]
    presupuesto_status: str

    extracted_data: dict[str, Any]
    conflicts: list[dict[str, Any]]
    extraction_metadata: dict[str, Any]

    plazos_token_usage: dict[str, int]
    objeto_alcance_token_usage: dict[str, int]
    garantias_token_usage: dict[str, int]
    causales_token_usage: dict[str, int]
    anexos_token_usage: dict[str, int]
    documentos_token_usage: dict[str, int]
    criterios_token_usage: dict[str, int]
    restricciones_token_usage: dict[str, int]
    identificacion_token_usage: dict[str, int]
    cronograma_token_usage: dict[str, int]
    presupuesto_token_usage: dict[str, int]

    # Información para persistencia
    created_by: str | None
    db_session: Any
