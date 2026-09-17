"""Armado del prompt de sintesis (prompt base + items serializados + bloque de conflictos) y narrativas vacias/placeholder."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from analysis.extraction.schemas import CategoryNarrative, CONFIDENCE_NO_EVIDENCE

logger = structlog.get_logger(__name__)

RESPONSE_BASE_PROMPT_FILE = "_response_base.txt"
OUTPUT_SCHEMA_FILE = "_output_schema.txt"
_USABLE_STATUSES = {"success", "partial", "not_applicable"}
_PREVIEW_BULLET_RESUMEN_SCHEMA = (
    "\n\nRegla adicional para category_key=preview_criterios:\n"
    "- En cada item de bullet_list incluir también `resumen` (string corto, ideal <= 6 palabras).\n"
    "- `resumen` debe salir del mismo dato usado en `text` (sin invención).\n"
    "- Si extraction_status del item referenciado es not_found o failed, `resumen` debe ser exactamente \"No informado\".\n"
)
_CONFLICT_CATEGORY_TO_NARRATIVE = {
    "plazos": "plazos_clave",
    "garantias": "garantias",
}


def _empty_category_narrative(category_label: str) -> CategoryNarrative:
    """Mensaje canonico de "sin evidencia" para una categoria, armado en
    codigo -- nunca por el LLM. Cierra el loophole por el que un bloque sin
    fuentes reales podia llegar disfrazado de la excepcion "sin contenido
    util" que antes autorizaba el prompt."""
    return CategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": f"No se encontró información sobre {category_label} en los documentos del pliego.",
                    "confidence_level": CONFIDENCE_NO_EVIDENCE,  # Constante desde schemas
                    "source_ids": [],
                }
            ],
            "sources": [],
        }
    )


@lru_cache(maxsize=1)
def _load_response_base_prompt(category_key: str | None = None) -> str:
    """Carga el prompt base y el schema de output, concatenándolos."""
    # Este módulo vive en analysis/extraction/synthesis/ (un nivel más
    # profundo que el synthesis.py original) -- parent.parent sigue
    # apuntando a analysis/extraction/.
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    base_prompt = (prompts_dir / RESPONSE_BASE_PROMPT_FILE).read_text(encoding="utf-8")
    output_schema = (prompts_dir / OUTPUT_SCHEMA_FILE).read_text(encoding="utf-8")
    preview_schema = _PREVIEW_BULLET_RESUMEN_SCHEMA if category_key == "preview_criterios" else ""
    return f"{base_prompt}\n\n---\n\n{output_schema}{preview_schema}"


def _serialize_items(items: list[dict[str, Any]]) -> str:
    """Serializa los items para el prompt, exponiendo `item_index` (posicion
    0-based) explicitamente: es el unico identificador que el LLM puede usar
    en `item_refs`, y depender de que cuente bien la posicion en un array es
    mas fragil que dárselo ya resuelto."""
    indexed = [{"item_index": position, **item} for position, item in enumerate(items)]
    return json.dumps(indexed, ensure_ascii=False, indent=2, default=str)


def _has_usable_content(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("extraction_status", "")) in _USABLE_STATUSES for item in items)


def _conflict_block(category_key: str, conflicts: list[dict[str, Any]] | None) -> str:
    """El bloque de prompt que le avisa al redactor qué datos se contradicen."""
    if not conflicts:
        return "(sin contradicciones detectadas)"

    relevantes = [
        conflict
        for conflict in conflicts
        if _CONFLICT_CATEGORY_TO_NARRATIVE.get(str(conflict.get("category", ""))) == category_key
    ]
    if not relevantes:
        return "(sin contradicciones detectadas)"

    lineas: list[str] = []
    for conflict in relevantes:
        valores = []
        for item in conflict.get("values", []) or []:
            etiqueta = (
                item.get("valor")
                or item.get("fecha")
                or item.get("expresion_relativa")
                or item.get("monto_porcentaje")
                or item.get("monto_valor")
            )
            paginas = sorted(
                {
                    str(ref.get("page_number"))
                    for ref in (item.get("source_references") or [])
                    if ref.get("page_number")
                }
            )
            ubicacion = f" (pág. {', '.join(paginas)})" if paginas else ""
            if etiqueta is not None:
                valores.append(f"{etiqueta}{ubicacion}")
        if valores:
            lineas.append(
                f"- `{conflict.get('tipo', 'dato')}`: {conflict.get('reason', 'valores en conflicto')} "
                f"-> {' vs. '.join(valores)}"
            )

    return "\n".join(lineas) if lineas else "(sin contradicciones detectadas)"
