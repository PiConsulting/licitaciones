"""Verificación de que las citas de un item existen realmente en los chunks fuente (anti-invención)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any
import re
import unicodedata

import structlog

from analysis.extraction.schemas import (
    CITATION_MAX_CHARS,
    CITATION_MIN_CHARS,
    CITATION_PREFERRED_MIN_CHARS,
)

logger = structlog.get_logger(__name__)

_TABLE_CITATION_RE = re.compile(
    r"^\s*Encabezado:\s*(?P<column>.+?)\s*\|\s*Fila:\s*(?P<row>\d+)\s*\|\s*Valor:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_DIGITS_RE = re.compile(r"\d[\d.,]*")
_CITATION_LEAD_IN_CHARS = 45
_MILES_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DECIMAL_RE = re.compile(r"^\d+[.,]\d+$")


def _normalize_for_grounding(text: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split()).lower()


def _is_table_citation(citation: str) -> bool:
    return bool(_TABLE_CITATION_RE.match(citation))


def _citation_verified_in_paragraph_chunk(citation: str, chunk: dict[str, Any]) -> bool:
    normalized_citation = _normalize_for_grounding(citation)
    if not normalized_citation:
        return False
    normalized_content = _normalize_for_grounding(chunk.get("content", ""))
    return normalized_citation in normalized_content


def _expand_short_paragraph_citation(
    citation: str,
    candidate_chunks: list[dict[str, Any]],
    *,
    preferred_snippet: str | None = None,
) -> str:
    citation_text = str(citation or "").strip()
    if len(citation_text) >= CITATION_PREFERRED_MIN_CHARS:
        return citation_text

    normalized_citation = _normalize_for_grounding(citation_text)
    if not normalized_citation:
        return citation_text

    preferred_text = str(preferred_snippet or "").strip()
    normalized_preferred = _normalize_for_grounding(preferred_text)

    if len(preferred_text) >= CITATION_PREFERRED_MIN_CHARS and normalized_preferred:
        for chunk in candidate_chunks:
            if chunk.get("block_type") == "table":
                continue
            normalized_content = _normalize_for_grounding(chunk.get("content", ""))
            if normalized_preferred in normalized_content:
                return clip_citation(preferred_text)
    # Política estricta: no expandir por match de palabra suelta. Si no hay
    # ancla explícita válida, la cita se conserva y el ítem se penaliza luego.
    return citation_text


def _widen_citation_with_chunk_context(
    citation: str,
    candidate_chunks: list[dict[str, Any]],
    *,
    target_chars: int = CITATION_PREFERRED_MIN_CHARS,
) -> str:
    """Ensancha una cita ya verificada usando el texto que la rodea en el chunk
    donde matcheó, hasta que sea evidencia legible por sí sola."""
    collapsed_citation = " ".join(str(citation or "").split())
    if not collapsed_citation or len(collapsed_citation) >= target_chars:
        return citation

    needle = collapsed_citation.lower()
    for chunk in candidate_chunks:
        if chunk.get("block_type") == "table":
            continue
        content = " ".join(str(chunk.get("content", "")).split())
        start = content.lower().find(needle)
        if start < 0:
            continue
        widened = _build_context_citation(
            content, start, start + len(collapsed_citation), min_chars=target_chars
        )

        if len(widened) > len(collapsed_citation) and needle in widened.lower():
            return widened
    return citation


def _candidate_rescue_snippets(item: dict[str, Any], *, category: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for raw_value in [
        item.get("texto_original") if category == "plazos_clave" else None,
        item.get("valor"),
    ]:
        snippet = str(raw_value or "").strip()
        if not snippet:
            continue
        if len(snippet) < CITATION_MIN_CHARS:
            continue
        normalized = _normalize_for_grounding(snippet)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(snippet)

    return candidates


def _rescue_paragraph_citation(
    item: dict[str, Any],
    candidate_chunks: list[dict[str, Any]],
    *,
    category: str,
) -> str | None:
    for snippet in _candidate_rescue_snippets(item, category=category):
        if _verify_reference_grounded(snippet, candidate_chunks):
            return clip_citation(snippet)
    return None


def _citation_verified_in_table_chunk(citation: str, chunk: dict[str, Any]) -> bool:
    match = _TABLE_CITATION_RE.match(citation)
    if not match:
        return False

    table_ref = chunk.get("table_ref")
    if not isinstance(table_ref, dict):
        return False

    try:
        row_index = int(match.group("row").strip())
    except ValueError:
        return False
    if int(table_ref.get("row_index") or -1) != row_index:
        return False

    column_raw = match.group("column").strip()
    headers = [str(header) for header in (table_ref.get("headers") or [])]
    content = str(chunk.get("content", ""))
    column_matches = any(
        _normalize_for_grounding(header) == _normalize_for_grounding(column_raw)
        for header in headers
    ) or (f"{column_raw}:" in content)
    if not column_matches:
        return False

    value = _normalize_for_grounding(match.group("value"))
    if not value:
        return False
    return value in _normalize_for_grounding(content)


def clip_citation(citation: str, max_chars: int = CITATION_MAX_CHARS) -> str:
    """Recorta una cita ya verificada al límite de almacenamiento, cortando en
    un borde de palabra. El recorte preserva el carácter literal de la cita: un
    prefijo de un texto que existe literalmente en el chunk sigue existiendo
    literalmente en el chunk, así que la cita recortada se vuelve a verificar
    igual de bien si el grounding corre otra vez sobre el dato persistido."""
    text = str(citation or "").strip()
    if len(text) <= max_chars:
        return text

    clipped = text[:max_chars]
    last_space = clipped.rfind(" ")
    # Solo cortamos en el último espacio si eso no destruye la cita (nos
    # quedaría por debajo del mínimo discriminante).
    if last_space >= CITATION_MIN_CHARS:
        clipped = clipped[:last_space]
    return clipped.strip()


def _canonical_number(token: str) -> str:
    """Forma canónica de un número escrito de cualquiera de las maneras en que
    aparece entre el pliego y el dato extraído.

    "AR$ 12.000.000" -> "12000000" <- "12000000.0 ARS"

    Los separadores de miles y los decimales nulos son ruido de formato: sin
    normalizarlos, el monto del item nunca matchea el monto de la cita.
    """
    text = str(token or "").strip().strip(".,")
    if _MILES_RE.match(text):
        return text.replace(".", "").replace(",", "")
    if _DECIMAL_RE.match(text):
        entera, _, decimal = text.replace(",", ".").partition(".")
        decimal = decimal.rstrip("0")
        return entera + decimal
    return "".join(ch for ch in text if ch.isdigit())


def _citation_anchor_position(citation: str, item: dict[str, Any]) -> int | None:
    """Dónde, dentro de la cita, está el dato que el item afirma.

    Se prueban tres anclas, de la más fuerte a la más débil:
      1. el `valor` como PALABRA COMPLETA (sin acentos, sin distinguir
         mayúsculas). La palabra completa importa: `valor="Municipal"` matchea
         como subcadena dentro de "Municipalidad" -- que suele estar al
         principio del texto, en el nombre del organismo -- y esa coincidencia
         apuntaría a cualquier lado menos a "Jurisdicción: Municipal";
      2. el `valor` como subcadena, para valores largos (un `causal_rechazo` o
         un `resumen_objeto` son frases enteras que rara vez están literales);
      3. si el valor tiene dígitos, el número, comparado en forma canónica.

    Devuelve None si no se puede ubicar: ahí el recorte cae al prefijo, que es
    el comportamiento de siempre.
    """
    valor = " ".join(str(item.get("valor") or "").split()).strip(" .;:-")
    if not valor:
        return None

    haystack = _normalize_for_grounding(citation)
    if not haystack:
        return None

    needle = _normalize_for_grounding(valor)

    if len(needle) >= 4:
        palabra_completa = re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])", haystack)
        if palabra_completa:
            return palabra_completa.start()

    for candidate in (needle, needle[:40]):
        if len(candidate) >= 12:
            position = haystack.find(candidate)
            if position >= 0:
                return position

    valor_number = _canonical_number(valor.split()[0] if valor.split() else "")
    if len(valor_number) >= 3:
        for match in _DIGITS_RE.finditer(citation):
            if _canonical_number(match.group(0)) == valor_number:
                return match.start()

    return None


def shorten_citation_to_evidence(
    citation: str, item: dict[str, Any], *, max_chars: int = CITATION_MAX_CHARS
) -> str:
    """Recorta una cita larga a la ventana que CONTIENE el dato del item."""
    text = " ".join(str(citation or "").split())
    if len(text) <= max_chars:
        return text

    anchor = _citation_anchor_position(text, item)
    if anchor is None:
        return clip_citation(text, max_chars=max_chars)

    start = max(0, anchor - _CITATION_LEAD_IN_CHARS)
    end = start + max_chars
    if end > len(text):
        start = max(0, len(text) - max_chars)
        end = len(text)

    # Bordes de palabra: nunca partir una palabra al medio, ni al principio ni
    # al final. Si el ajuste dejara la cita por debajo del mínimo, se prefiere
    # el corte crudo antes que perder la cita.
    if start > 0:
        space = text.find(" ", start)
        if 0 <= space < end - CITATION_MIN_CHARS:
            start = space + 1
    if end < len(text):
        space = text.rfind(" ", start, end)
        if space > start + CITATION_MIN_CHARS:
            end = space

    return text[start:end].strip()


def _find_grounding_chunk(
    citation: str, candidate_chunks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Devuelve EL chunk que respalda la cita, o None si ninguno la contiene."""
    citation_text = str(citation or "").strip()
    if not citation_text:
        return None

    if len(citation_text) < CITATION_MIN_CHARS:
        return None

    if _is_table_citation(citation):
        for chunk in candidate_chunks:
            if chunk.get("block_type") != "table":
                continue
            if _citation_verified_in_table_chunk(citation, chunk):
                return chunk
        return None

    # Si el LLM devuelve una cita textual "normal" para un dato que cayó en un
    # chunk de tabla (caso frecuente en carátulas), también debe validarse.
    for chunk in candidate_chunks:
        if _citation_verified_in_paragraph_chunk(citation, chunk):
            return chunk
    return None


def _verify_reference_grounded(citation: str, candidate_chunks: list[dict[str, Any]]) -> bool:
    """Igual que `_find_grounding_chunk` pero en booleano, para los llamadores
    que sólo necesitan saber si la cita se sostiene."""
    return _find_grounding_chunk(citation, candidate_chunks) is not None


def _word_start(text: str, index: int) -> int:
    """Inicio de la palabra que contiene `index`. Expande hacia afuera."""
    index = max(0, min(index, len(text)))
    while index > 0 and not text[index - 1].isspace():
        index -= 1
    return index


def _word_end(text: str, index: int) -> int:
    """Fin (exclusivo) de la palabra que contiene `index - 1`. Expande hacia afuera."""
    index = max(0, min(index, len(text)))
    while index < len(text) and not text[index].isspace():
        index += 1
    return index


def _build_context_citation(
    content: str,
    start: int,
    end: int,
    *,
    min_chars: int = CITATION_MIN_CHARS,
    max_chars: int = CITATION_MAX_CHARS,
) -> str:
    """Ensancha `content[start:end]` con el texto que lo rodea, sin perderlo."""
    text = " ".join(str(content or "").split())
    if not text:
        return ""

    core_start = max(0, min(int(start), len(text)))
    core_end = max(core_start, min(int(end), len(text)))
    core_len = core_end - core_start

    # El núcleo es la evidencia. Si por sí solo excede el techo, se recorta el
    # núcleo: seguimos dentro del texto que respalda el dato.
    if core_len >= max_chars:
        return clip_citation(text[core_start:core_end], max_chars=max_chars)

    budget = max(0, min(max_chars, max(min_chars, core_len)) - core_len)
    lead = budget // 3

    left = _word_start(text, max(0, core_start - lead))
    right = _word_end(text, min(len(text), core_end + (budget - lead)))

    while right - left > max_chars and right > core_end:
        space = text.rfind(" ", core_end, right)
        if space < 0:
            break
        right = space
    while right - left > max_chars and left < core_start:
        space = text.find(" ", left, core_start)
        if space < 0:
            break
        left = space + 1

    snippet = text[left:right].strip()
    return snippet if len(snippet) <= max_chars else clip_citation(snippet, max_chars=max_chars)


def _verify_citation_grounding(
    items: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    category: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Confirma que cada `source_reference` de cada ítem exista de verdad en los
    chunks recuperados (anti-alucinación). Corre dentro de run_extractor porque
    es el único lugar del pipeline que todavía tiene en scope tanto los ítems ya
    parseados como los `chunks` originales pasados al LLM. Sigue el mismo patrón
    de `_warning` + downgrade a "partial" que ya usa `_penalize_unverifiable` en
    graph.py, sin inventar un mecanismo paralelo."""
    # Imports diferidos: normalization y chunk_retrieval importan de este
    # módulo a nivel de módulo (_normalize_for_grounding, etc.); importar acá
    # arriba crearía un ciclo. Sólo esta función necesita estos dos símbolos.
    from analysis.extraction.engine.chunk_retrieval import _attach_chunk_identity
    from analysis.extraction.engine.normalization import _as_page_number

    chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        key = (str(chunk.get("document_id", "")), int(chunk.get("page_number", 0) or 0))
        chunks_by_doc_page[key].append(chunk)

    total_items = 0
    unverified_items = 0
    rescued_items = 0

    for item in items:
        status = str(item.get("extraction_status", ""))
        refs = item.get("source_references") or []
        if status not in {"success", "partial", "not_applicable"} or not refs:
            continue

        total_items += 1
        any_verified = False
        rescued_refs_count = 0
        verified_refs: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            citation = str(ref.get("citation", ""))
            # FIX (2026-08-14): `int(...)` directo reventaba con ValueError ante
            # un `page_number` que el LLM escribiera como "3-4", "12 y 13" o
            # "s/n" -- formas que aparecen cuando una cita cruza dos páginas del
            # pliego. Igual que arriba: un ref raro degrada ese ref, no la
            # categoría entera.
            key = (str(ref.get("document_id", "")), _as_page_number(ref.get("page_number")))
            candidates = chunks_by_doc_page.get(key)
            if not candidates:
                continue
            citation_for_verification = citation
            if len(citation.strip()) < CITATION_MIN_CHARS and category == "plazos_clave":
                preferred = str(item.get("texto_original") or "").strip()
                if preferred and _verify_reference_grounded(preferred, candidates):
                    citation_for_verification = preferred

            rescued_citation: str | None = None
            grounding_chunk = _find_grounding_chunk(citation_for_verification, candidates)
            if grounding_chunk is not None:
                any_verified = True
                normalized_ref = dict(ref)

                _attach_chunk_identity(normalized_ref, grounding_chunk)
                final_citation = citation_for_verification
                if not _is_table_citation(citation):
                    preferred_snippet = None
                    if category == "plazos_clave":
                        preferred_snippet = str(item.get("texto_original") or "").strip() or None
                    final_citation = _expand_short_paragraph_citation(
                        citation_for_verification,
                        candidates,
                        preferred_snippet=preferred_snippet,
                    )

                    if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
                        richer = _rescue_paragraph_citation(item, candidates, category=category)
                        if richer and len(richer) > len(final_citation):
                            final_citation = richer
                    if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
                        final_citation = _widen_citation_with_chunk_context(
                            final_citation, candidates
                        )

                normalized_ref["citation"] = shorten_citation_to_evidence(final_citation, item)

                normalized_ref["citation_llm"] = citation
                normalized_ref["citation_origin"] = (
                    "llm"
                    if _normalize_for_grounding(final_citation)
                    == _normalize_for_grounding(citation)
                    else "ensanchada"
                )
                verified_refs.append(normalized_ref)
                continue

            if not _is_table_citation(citation):
                rescued_citation = _rescue_paragraph_citation(item, candidates, category=category)

            if rescued_citation:
                rescued_refs_count += 1
                normalized_ref = dict(ref)
                normalized_ref["citation"] = rescued_citation
                normalized_ref["citation_llm"] = citation
                normalized_ref["citation_origin"] = "rescatada"
                # La cita rescatada también tiene su chunk de respaldo: es el
                # que hizo pasar `_verify_reference_grounded` dentro de
                # `_rescue_paragraph_citation`.
                _attach_chunk_identity(
                    normalized_ref, _find_grounding_chunk(rescued_citation, candidates)
                )
                verified_refs.append(normalized_ref)

        if verified_refs:
            item["source_references"] = verified_refs

        # Un item que sólo se sostiene con citas rescatadas no está verificado:
        # su evidencia declarada no existía en los chunks (ver arriba).
        if not any_verified and rescued_refs_count:
            rescued_items += 1
            if status == "success":
                item["extraction_status"] = "partial"
            item["_warning"] = "cita_reemplazada_por_rescate"

        if not any_verified and not rescued_refs_count:
            unverified_items += 1
            item["source_references"] = []
            if status == "success":
                item["extraction_status"] = "partial"
            item["_warning"] = "cita_no_verificada"

    if total_items:
        logger.info(
            "citation_grounding_check",
            correlation_id=correlation_id,
            category=category,
            total_items=total_items,
            unverified_items=unverified_items,
            rescued_items=rescued_items,
        )

    return items


def _grounding_chunk_ids_for_item(item: dict[str, Any], chunks: list[dict[str, Any]]) -> set[str]:
    """De qué chunk(s) recuperados sale, literalmente, cada cita del ítem.

    Reusa el mismo matcheo literal que `_verify_citation_grounding` (texto de
    la cita contenido en `chunk['content']`) para no duplicar criterios de
    "qué cuenta como evidencia real" entre dos funciones del pipeline.
    """
    ids: set[str] = set()
    for ref in item.get("source_references") or []:
        if not isinstance(ref, dict):
            continue
        citation = str(ref.get("citation") or "").strip()
        if not citation:
            continue
        for chunk in chunks:
            if _citation_verified_in_paragraph_chunk(citation, chunk):
                chunk_id = chunk.get("id") or chunk.get("chunk_id")
                if chunk_id:
                    ids.add(str(chunk_id))
                break
    return ids
