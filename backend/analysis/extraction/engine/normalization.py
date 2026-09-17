"""Normalización de items extraídos: defaults, dedupe de status, y payload de identificación del procedimiento."""
from __future__ import annotations

from typing import Any
import re

import structlog

from analysis.extraction.engine.citation_grounding import (
    _build_context_citation,
    _normalize_for_grounding,
    clip_citation,
)
from analysis.extraction.schemas import (
    CITATION_MIN_CHARS,
)

logger = structlog.get_logger(__name__)

VALID_EXTRACTION_STATUSES = {"success", "partial", "failed", "not_found", "not_applicable"}
_PROCEDIMIENTO_CON_NUMERO_RE = re.compile(
    r"(?P<tipo>licitaci[oó]n\s+p[úu]blica|licitaci[oó]n\s+privada|contrataci[oó]n\s+directa|concurso\s+de\s+precios|subasta\s+p[úu]blica)\s*"
    r"(?:n[°ºo\.]?\s*)?(?P<numero>[A-Z0-9\-\/.]+)",
    re.IGNORECASE,
)
_EXPEDIENTE_RE = re.compile(
    r"\bexpediente\b\s*[:\-]?\s*(?P<value>[A-Z0-9][A-Z0-9\-\/.]{4,})", re.IGNORECASE
)
_ORGANISMO_RE = re.compile(
    r"\borganismo\b\s*[:\-]?\s*(?P<value>.+?)(?=\bprocedimiento\b|\bobjeto\b|\bpresupuesto\b|\bexpediente\b|$)",
    re.IGNORECASE,
)
_PRESUPUESTO_RE = re.compile(
    r"\bpresupuesto\s+oficial\b\s*[:\-]?\s*(?P<value>.+?)"
    r"(?=\bexpediente\b|\bprocedimiento\b|\bobjeto\b|\bapertura\b|\blugar\b|$)",
    re.IGNORECASE,
)
_TIPOS_IDENTIFICACION_QUE_REQUIEREN_DIGITO = {
    "numero_procedimiento",
    "expediente",
    "presupuesto_oficial",
}


def _default_not_found_item() -> dict[str, Any]:
    return {
        "tipo": "No encontrado",
        "valor": None,
        "confidence": 0.0,
        "source_references": [],
        "extraction_status": "not_found",
    }


# Etiquetas legibles para GarantiaItem.tipo (schemas.TipoGarantia), usadas
# solo para componer `valor` cuando el LLM lo devuelve vacío -- ver
# `_fill_missing_valor_for_garantias`.
_GARANTIA_TIPO_LABELS: dict[str, str] = {
    "mantenimiento_oferta": "Garantía de Mantenimiento de Oferta",
    "cumplimiento_contrato": "Garantía de Cumplimiento de Contrato",
    "anticipo": "Anticipo Financiero",
    "contragarantia": "Contragarantía",
    "impugnacion": "Garantía de Impugnación",
    "fondo_reparo": "Fondo de Reparo",
    "por_vicios_ocultos": "Garantía por Vicios Ocultos",
    "buen_uso_anticipo": "Garantía de Buen Uso del Anticipo",
    "otra": "Garantía",
}


def _compose_garantia_valor(item: dict[str, Any]) -> str | None:
    """Arma un `valor` legible ("Título: descripción") a partir de los campos
    que el propio ítem ya trae -- nunca inventa un dato nuevo, solo reformula
    en una línea lo que ya está en `monto_porcentaje`/`forma_constitucion`/
    `vigencia`, o como último recurso la cita ya verificada.

    Por qué existe (auditoría RAG Fase 2, 2026-09-16, `backend/debug/rag-audit/
    fase2-generacion-2026-09-16.md`): confirmado con un experimento controlado
    que el LLM omite `valor` en una fracción real de las corridas -- incluso
    con un solo chunk limpio, sin ruido, mismo prompt, dos corridas seguidas
    dieron resultados distintos. Es no-determinismo de muestreo, no falta de
    información ni de instrucción en el prompt (que ya pide `valor` obligatorio
    hace tiempo). Reforzar la instrucción en el prompt para TODOS los status
    se probó y tuvo un efecto secundario negativo (indujo al LLM a partir un
    mismo hecho en dos ítems -- uno bien tipificado sin dato, otro mal
    tipificado con el dato -- medido en `extraction_eval.py`: wrong_rate
    0.211->0.292). Por eso el fallback vive acá, en código determinístico,
    después de que el LLM ya decidió cuántos ítems y de qué tipo son.
    """
    tipo = str(item.get("tipo") or "").strip()
    label = _GARANTIA_TIPO_LABELS.get(tipo) or (tipo.replace("_", " ").strip().capitalize() or "Garantía")

    parts: list[str] = []

    monto_porcentaje = item.get("monto_porcentaje")
    monto_valor = item.get("monto_valor")
    moneda = str(item.get("moneda") or "").strip()
    base_calculo = str(item.get("base_calculo") or item.get("sobre_que_se_calcula") or "").strip()

    if monto_porcentaje not in (None, ""):
        monto_txt = f"{monto_porcentaje}%"
        if base_calculo:
            monto_txt += f" de {base_calculo}"
        parts.append(monto_txt)
    elif monto_valor not in (None, ""):
        monto_txt = f"{moneda} {monto_valor}".strip() if moneda else str(monto_valor)
        if base_calculo:
            monto_txt += f" de {base_calculo}"
        parts.append(monto_txt)

    forma = str(item.get("forma_constitucion") or "").strip()
    if forma:
        parts.append(forma if forma.lower().startswith("mediante") else f"mediante {forma}")

    vigencia = str(item.get("vigencia") or "").strip()
    if vigencia:
        parts.append(f"vigencia {vigencia}")

    if parts:
        return f"{label}: " + ", ".join(parts)

    # Sin ningún campo estructurado (común en el caso de exención/
    # not_applicable, donde no hay monto que constituir): la cita ya pasó por
    # `_verify_citation_grounding`, así que es texto real del pliego -- mejor
    # eso que un ítem en blanco.
    refs = item.get("source_references")
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                citation = str(ref.get("citation") or "").strip()
                if citation:
                    return f"{label}: {citation}"

    return None


def _fill_missing_valor_for_garantias(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Red de seguridad determinística: si el LLM no completó `valor` en un
    ítem de garantías, lo compone acá antes de normalizar -- no depende de
    que el LLM recuerde la instrucción del prompt en cada corrida. No cambia
    `tipo`, `extraction_status` ni la cantidad de ítems -- solo evita que
    `valor` llegue vacío al usuario. Se llama sobre el payload crudo del LLM,
    antes de `_normalize_item`, para que si logra componer un valor, el
    status `not_applicable` original (si corresponde) no se baje a `partial`
    por el guard de abajo.
    """
    filled = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("valor") or "").strip():
            continue
        composed = _compose_garantia_valor(item)
        if composed:
            item["valor"] = composed
            filled += 1
    if filled:
        logger.info("garantias_valor_completado_por_fallback", count=filled)
    return items


def _normalize_item(item: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = dict(fallback or {})
    normalized.update(item)

    raw_confidence = normalized.get("confidence")
    try:
        parsed_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        parsed_confidence = None

    if parsed_confidence is None or not (0.0 <= parsed_confidence <= 1.0):
        normalized.pop("confidence", None)
    else:
        normalized["confidence"] = min(parsed_confidence, 1.0)

    raw_refs = normalized.get("source_references")
    normalized["source_references"] = (
        [ref for ref in raw_refs if isinstance(ref, dict)] if isinstance(raw_refs, list) else []
    )
    status = str(normalized.get("extraction_status", "")).strip()
    if status not in VALID_EXTRACTION_STATUSES:
        logger.warning("invalid_extraction_status", received=status[:80])
        status = "partial" if normalized.get("source_references") else "not_found"
    normalized["extraction_status"] = status

    # FIX (2026-09-11, bug encontrado auditando garantías/dell): varias
    # prompts (ej. garantias.txt, Caso 4) exigen explícitamente que todo
    # ítem `not_applicable` traiga `valor` ("es el único texto que le
    # explica al oferente por qué no hay garantía... un not_applicable con
    # valor: null no sirve") -- el LLM viola esa instrucción de todos modos
    # (observado: ítem con cita real pero `valor: null`, mostrando un N/A al
    # usuario sin ninguna explicación legible). Confiar en que el LLM cumpla
    # su propia instrucción no alcanzó -- se lo baja acá de forma
    # determinística en vez de persistir una afirmación N/A sin sustento.
    # `_normalize_mixed_not_found_items`/`_drop_items_without_sources`, río
    # abajo, deciden después si el ítem sobrevive (por sus fuentes) o se
    # descarta -- acá solo se evita la mentira de un N/A "explicado" que no
    # explica nada.
    if normalized["extraction_status"] == "not_applicable" and not str(
        normalized.get("valor") or ""
    ).strip():
        normalized["extraction_status"] = "partial"
        normalized["_warning"] = "not_applicable_sin_valor"

    return normalized


def _item_has_substantive_content(item: dict[str, Any]) -> bool:
    """Detecta si un ítem aporta dato útil más allá del status declarado."""
    text_fields = ("valor", "texto_original", "expresion_relativa", "fecha", "hora", "lugar")
    for field_name in text_fields:
        value = item.get(field_name)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned and cleaned not in {"no encontrado", "not_found"}:
                return True
            continue
        return True

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for meta_value in metadata.values():
            if meta_value is None:
                continue
            if isinstance(meta_value, str):
                cleaned = meta_value.strip().lower()
                if cleaned and cleaned not in {"no_especificado", "no encontrado", "not_found"}:
                    return True
                continue
            return True

    return bool(item.get("source_references"))


def _normalize_mixed_not_found_items(
    items: list[dict[str, Any]], *, category: str
) -> list[dict[str, Any]]:
    """Evita `not_found` a nivel ítem cuando la categoría sí tiene hallazgos.

    Regla pedida por producto: `not_found` solo corresponde cuando la categoría
    completa no encontró nada útil.
    """
    if not items:
        return items

    has_category_findings = any(
        str(item.get("extraction_status", "")).strip() in {"success", "partial", "not_applicable"}
        or _item_has_substantive_content(item)
        for item in items
    )
    if not has_category_findings:
        return items

    normalized_items: list[dict[str, Any]] = []
    converted = 0
    dropped = 0

    for item in items:
        status = str(item.get("extraction_status", "")).strip()
        if status != "not_found":
            normalized_items.append(item)
            continue

        if _item_has_substantive_content(item):
            adjusted = dict(item)
            adjusted["extraction_status"] = "partial"
            normalized_items.append(adjusted)
            converted += 1
        else:
            dropped += 1

    if converted or dropped:
        logger.info(
            "normalized_mixed_not_found_items",
            category=category,
            original_count=len(items),
            kept_count=len(normalized_items),
            converted_to_partial=converted,
            dropped_placeholders=dropped,
        )

    return normalized_items


def _aggregate_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("extraction_status", "not_found")) for item in items}
    if "success" in statuses:
        return "success"
    if "partial" in statuses:
        return "partial"
    if "not_applicable" in statuses:
        return "not_applicable"
    if "not_found" in statuses:
        return "not_found"
    if "failed" in statuses:
        return "failed"
    return "not_found"


def _normalized_identificacion_tipo(raw_tipo: str) -> str:
    text = _normalize_for_grounding(raw_tipo)
    if "organismo" in text:
        return "organismo_convocante"
    if "expediente" in text:
        return "expediente"
    if "numero" in text and "proced" in text:
        return "numero_procedimiento"
    if text in {"procedimiento", "procedimiento_nro", "procedimiento_numero"}:
        return "numero_procedimiento"
    if "tipo" in text and "proced" in text:
        return "tipo_procedimiento"
    if "jurisd" in text:
        return "jurisdiccion"
    if "presupuesto" in text:
        return "presupuesto_oficial"
    return raw_tipo.strip().lower() or "otro"


def _augment_identificacion_payload(
    payload: list[dict[str, Any]], chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    existing_tipos = {
        _normalized_identificacion_tipo(str(item.get("tipo", "")))
        for item in payload
        if isinstance(item, dict)
    }

    additions: list[dict[str, Any]] = []

    sorted_chunks = sorted(
        chunks,
        key=lambda chunk: (
            int(chunk.get("page_number", 0) or 0),
            str(chunk.get("document_id", "")),
        ),
    )

    def add_if_missing(
        tipo: str, valor: str, chunk: dict[str, Any], match_span: tuple[int, int]
    ) -> None:
        canonical_tipo = _normalized_identificacion_tipo(tipo)
        clean_valor = " ".join(str(valor or "").split()).strip(" .;:-")
        if not clean_valor or canonical_tipo in existing_tipos:
            return
        if canonical_tipo in _TIPOS_IDENTIFICACION_QUE_REQUIEREN_DIGITO and not any(
            ch.isdigit() for ch in clean_valor
        ):
            logger.debug(
                "identificacion_augment_rejected_no_digit",
                tipo=canonical_tipo,
                valor_descartado=clean_valor[:80],
            )
            return

        citation = _build_context_citation(
            str(chunk.get("content", "")), match_span[0], match_span[1]
        )
        if len(citation) < CITATION_MIN_CHARS:
            citation = clip_citation(" ".join(str(chunk.get("content", "")).split()))
        if len(citation) < CITATION_MIN_CHARS:
            return

        # Extraer block_id del chunk (de source.blocks o merged_blocks)
        block_id = None
        source_data = chunk.get("source", {})
        if isinstance(source_data, dict):
            blocks = source_data.get("blocks", [])
            if blocks and isinstance(blocks, list) and blocks[0]:
                block_id = str(blocks[0].get("block_id") or blocks[0].get("para_id", ""))

        if not block_id:
            # Fallback: usar para_id directo del chunk (formato legacy)
            block_id = str(chunk.get("para_id", "")) if chunk.get("para_id") else None

        additions.append(
            {
                "tipo": canonical_tipo,
                "valor": clean_valor,
                "metadata": {},
                "confidence": 0.78,
                "source_references": [
                    {
                        "document_id": str(chunk.get("document_id", "")),
                        "page_number": int(chunk.get("page_number", 0) or 0),
                        "citation": citation,
                        "block_id": block_id,
                    }
                ],
                "extraction_status": "success",
            }
        )
        existing_tipos.add(canonical_tipo)

    for chunk in sorted_chunks:
        content = " ".join(str(chunk.get("content", "")).split())
        if not content:
            continue

        if "organismo_convocante" not in existing_tipos:
            match = _ORGANISMO_RE.search(content)
            if match:
                add_if_missing("organismo_convocante", match.group("value"), chunk, match.span())

        if "expediente" not in existing_tipos:
            match = _EXPEDIENTE_RE.search(content)
            if match:
                add_if_missing("expediente", match.group("value"), chunk, match.span("value"))

        match = _PROCEDIMIENTO_CON_NUMERO_RE.search(content)
        if match:
            if "tipo_procedimiento" not in existing_tipos:
                add_if_missing("tipo_procedimiento", match.group("tipo"), chunk, match.span("tipo"))
            if "numero_procedimiento" not in existing_tipos:
                numero_text = f"{match.group('tipo')} N° {match.group('numero')}"
                add_if_missing("numero_procedimiento", numero_text, chunk, match.span())

        if "presupuesto_oficial" not in existing_tipos:
            match = _PRESUPUESTO_RE.search(content)
            if match:
                add_if_missing(
                    "presupuesto_oficial", match.group("value"), chunk, match.span("value")
                )

    if not additions:
        return payload
    return [*payload, *additions]


def _as_page_number(value: Any) -> int:
    """El número de página de una referencia, tolerando lo que emita el LLM.

    "3" -> 3 | 3 -> 3 | "3-4" -> 3 | "pág. 12" -> 12 | "s/n" -> 0
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0
