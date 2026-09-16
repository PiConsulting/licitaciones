"""Carga y validación de prompts de extracción, y construcción de mensajes para el LLM."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

BASE_SYSTEM_PROMPT_FILE = "_base_system.txt"
RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"
CANONICAL_PROMPT_FILES = {
    BASE_SYSTEM_PROMPT_FILE,
    RESPONSE_BASE_PROMPT_FILE,
    "_output_schema.txt",
    "_verification_pass_system.txt",
    "_verification_pass.txt",
    "objeto_alcance.txt",
    "requisitos_admisibilidad.txt",
    "garantias.txt",
    "plazos_clave.txt",
    "criterios_evaluacion.txt",
    "causales_rechazo.txt",
    "anexos_obligatorios.txt",
    "identificacion_procedimiento.txt",
    "preview_criterios.txt",
    "riesgos.txt",
    "eventos_temporales.txt",
}
CANONICAL_CATEGORY_PROMPT_MAP = {
    "objeto_alcance": "objeto_alcance.txt",
    "requisitos_admisibilidad": "requisitos_admisibilidad.txt",
    "garantias": "garantias.txt",
    "plazos_clave": "plazos_clave.txt",
    "criterios_evaluacion": "criterios_evaluacion.txt",
    "causales_rechazo": "causales_rechazo.txt",
    "anexos_obligatorios": "anexos_obligatorios.txt",
    "identificacion_procedimiento": "identificacion_procedimiento.txt",
    "preview_criterios": "preview_criterios.txt",
    "riesgos": "riesgos.txt",
    "eventos_temporales": "eventos_temporales.txt",
}


@lru_cache(maxsize=32)
def _load_prompt(prompt_file_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / prompt_file_name
    return prompt_path.read_text(encoding="utf-8")


def validate_prompt_inventory() -> None:
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    actual_files = {path.name for path in prompts_dir.glob("*.txt")}

    missing = sorted(CANONICAL_PROMPT_FILES - actual_files)
    extras = sorted(actual_files - CANONICAL_PROMPT_FILES)
    if missing or extras:
        details: list[str] = []
        if missing:
            details.append(f"faltan prompts canónicos: {', '.join(missing)}")
        if extras:
            details.append(f"sobran prompts no permitidos: {', '.join(extras)}")
        raise ValueError("Configuración inválida de prompts de extracción: " + " | ".join(details))


def validate_category_prompt_mapping(result_key: str, prompt_file_name: str) -> None:
    expected_prompt = CANONICAL_CATEGORY_PROMPT_MAP.get(result_key)
    if not expected_prompt:
        raise ValueError(
            f"Categoría de extracción no canónica: '{result_key}'. "
            f"Permitidas: {', '.join(sorted(CANONICAL_CATEGORY_PROMPT_MAP))}"
        )

    if prompt_file_name != expected_prompt:
        raise ValueError(
            "Mapeo categoría->prompt inválido: "
            f"{result_key} debe usar '{expected_prompt}', no '{prompt_file_name}'"
        )


def _build_messages(
    *,
    prompt_file_name: str,
    chunks_block: str,
    glossary_block: str,
    root_key: str,
) -> list[tuple[str, str]]:
    system_prompt = (
        _load_prompt(BASE_SYSTEM_PROMPT_FILE)
        .replace("{glossary_terms}", glossary_block or "(sin sinónimos configurados)")
        .replace("{root_key}", root_key)
    )
    user_prompt = (
        _load_prompt(prompt_file_name)
        .replace("{chunks}", chunks_block)
        .replace("{root_key}", root_key)
    )
    return [("system", system_prompt), ("human", user_prompt)]


def _describe_document(document_id: str, labels: dict[str, dict[str, Any]] | None) -> str:
    """Cómo se nombra la fuente en el encabezado del fragmento (CTX-05).

    Sin etiquetas se devuelve el UUID solo, que es lo que hacía antes de que un
    análisis pudiera tener varios documentos. Con etiquetas se antepone el
    nombre y el rol, porque el modelo necesita saber si está leyendo el pliego o
    un anexo antes de decidir qué hacer cuando dicen cosas distintas.

    El UUID no se saca nunca: el prompt exige copiarlo en
    `source_references[].document_id`, y de ahí sale el resaltado.
    """
    if not document_id:
        return "desconocido"

    datos = (labels or {}).get(document_id)
    if not isinstance(datos, dict):
        return document_id

    nombre = str(datos.get("nombre") or "").strip()
    rol = "PLIEGO PRINCIPAL" if datos.get("es_principal") else "ANEXO"
    if not nombre:
        return f"{rol} ({document_id})"
    return f"{nombre} [{rol}] ({document_id})"


def _format_chunks(
    chunks: list[dict[str, Any]],
    document_labels: dict[str, dict[str, Any]] | None = None,
) -> str:
    if not chunks:
        return ""

    formatted: list[str] = []
    for position, chunk in enumerate(chunks, start=1):
        header = (
            f"[Fragmento: F{position}, "
            f"Documento: {_describe_document(str(chunk.get('document_id') or ''), document_labels)}, "
            f"Página: {chunk.get('page_number', 0)}, "
            f"Sección: {chunk.get('section_path', 'general')}, "
            f"Tipo: {'TABLA' if chunk.get('block_type') == 'table' else 'PÁRRAFO'}"
            f"{_table_hint(chunk)}]"
        )
        formatted.append(f"{header}\n{chunk.get('content', '')}")
    return "\n\n".join(formatted)


def _table_hint(chunk: dict[str, Any]) -> str:
    table_ref = chunk.get("table_ref")
    if not isinstance(table_ref, dict):
        return ""
    table_id = table_ref.get("table_id")
    row_index = table_ref.get("row_index")
    if table_id is None or row_index is None:
        return ""
    return f", Tabla: {table_id}, Fila: {row_index}"
