"""Contrato minimo que un item tiene que cumplir para sobrevivir al merge: cita presente y con largo valido, schema Pydantic valido."""
from __future__ import annotations

import structlog
from pydantic import BaseModel, ValidationError

from analysis.extraction.engine.citation_grounding import shorten_citation_to_evidence
from analysis.extraction.schemas import CITATION_MAX_CHARS, CITATION_MIN_CHARS

logger = structlog.get_logger(__name__)


def _enforce_citation_contract(items: list[dict]) -> list[dict]:
    """Normaliza las citas al contrato de `SourceReference` ANTES de que pydantic
    lo valide: recorta las que exceden el máximo y descarta las que no llegan al
    mínimo.

    Sin esto, una sola cita fuera de rango hacía que `ExtractedData(**...)`
    lanzara ValidationError dentro de merge_node y se perdiera el análisis
    ENTERO -- las ocho categorías, no solo la del ítem defectuoso. Y como el
    largo de una cita depende de cómo redacta cada pliego, el mismo sistema
    fallaba o no según el documento. El contrato se hace cumplir degradando el
    dato afectado, nunca tirando abajo el resto."""
    normalized_items: list[dict] = []
    for item in items:
        refs: list[dict] = []
        for ref in item.get("source_references", []):
            citation = str(ref.get("citation", "") or "").strip()
            if len(citation) < CITATION_MIN_CHARS:
                continue
            if len(citation) > CITATION_MAX_CHARS:
                citation = shorten_citation_to_evidence(citation, item)
            normalized_ref = dict(ref)
            normalized_ref["citation"] = citation
            refs.append(normalized_ref)

        normalized_item = dict(item)
        normalized_item["source_references"] = refs
        normalized_items.append(normalized_item)

    return normalized_items


def _sort_items_by_primary_document(items: list[dict]) -> list[dict]:
    """Ordena items para que los que provienen del documento primario (pliego
    principal, `is_primary=True`) queden primero, y el resto se ordene
    alfabéticamente por `filename` de su primera source_reference. Un item
    sin source_references o sin esos campos queda al final, en orden
    estable respecto a otros items en la misma situación."""

    def _sort_key(item: dict) -> tuple[bool, str]:
        refs = item.get("source_references") or []
        first_ref = refs[0] if refs else {}
        is_primary = bool(first_ref.get("is_primary"))
        filename = str(first_ref.get("filename") or "")
        return (not is_primary, filename)

    return sorted(items, key=_sort_key)


def _keep_schema_valid_items(
    items: list[dict],
    model: type[BaseModel],
    status: str,
    *,
    category: str,
    correlation_id: str,
    quality: dict[str, dict[str, int]] | None = None,
) -> tuple[list[dict], str]:
    """Descarta los items que no cumplen su schema, en vez de dejar que uno solo
    haga fallar la validacion de `ExtractedData` entera.

    `merge_node` construye `ExtractedData(**extracted_data)` con las OCHO
    categorias juntas: si un unico item trae un `tipo` fuera de su enum (caso
    real: `tipo="técnico"` en criterios_evaluacion, donde el enum admite
    "metodo"/"criterio"), pydantic levanta ValidationError y se pierde el
    analisis completo, no solo esa categoria. Y que el LLM emita o no un tipo
    fuera del enum depende de como esta redactado cada pliego -- otra fuente de
    resultados distintos entre documentos equivalentes.

    Validar item por item acota el dano al item defectuoso. Es una red de
    seguridad generica: cubre cualquier violacion de schema (enum, tipo de dato,
    campo faltante), no solo las que anticipamos con los `_canonical_*_tipo`."""
    valid: list[dict] = []
    invalid: list[str] = []

    for item in items:
        try:
            model(**item)
        except ValidationError as exc:
            invalid.append(f"{item.get('tipo')!r}: {exc.errors()[0].get('msg', '')}"[:200])
            continue
        valid.append(item)

    normalized_status = str(status or "unknown")
    if invalid:
        logger.warning(
            "items_descartados_por_schema",
            correlation_id=correlation_id,
            category=category,
            dropped=len(invalid),
            kept=len(valid),
            reasons=invalid[:5],
        )
        if normalized_status in {"success", "unknown"}:
            normalized_status = "partial"

        if quality is not None:
            registro = quality.setdefault(category, {})
            registro["descartados_por_formato"] = registro.get("descartados_por_formato", 0) + len(
                invalid
            )
            registro["conservados"] = len(valid)

    return valid, normalized_status


def _drop_items_without_sources(
    items: list[dict],
    status: str,
    *,
    category: str = "",
    quality: dict[str, dict[str, int]] | None = None,
) -> tuple[list[dict], str]:
    """El contrato final exige al menos una fuente por item persistido.
    Si el grounding dejó items sin citas verificables, se descartan y la
    categoría baja a partial cuando antes figuraba como success.
    """
    items = _enforce_citation_contract(items)
    filtered = [item for item in items if list(item.get("source_references", []))]
    dropped = len(items) - len(filtered)
    normalized_status = str(status or "unknown")

    if dropped and normalized_status in {"success", "unknown"}:
        normalized_status = "partial"

    if quality is not None and category:
        registro = quality.setdefault(category, {})
        if dropped:
            registro["descartados_sin_evidencia"] = (
                registro.get("descartados_sin_evidencia", 0) + dropped
            )
        rescatados = sum(
            1
            for item in filtered
            if str(item.get("_warning", "")) == "cita_reemplazada_por_rescate"
        )
        if rescatados:
            registro["con_evidencia_rescatada"] = (
                registro.get("con_evidencia_rescatada", 0) + rescatados
            )
        registro["conservados"] = len(filtered)

    return filtered, normalized_status
