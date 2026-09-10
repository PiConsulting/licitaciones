"""Reranking por LLM-as-judge (experimental, 2026-09-10).

Alternativa al cross-encoder local: se le pasan al LLM el top-N de RRF y la
definición de la categoría, y devuelve una relevancia 0-3 por chunk. Se
reordena con eso. Fallback seguro al orden RRF si la llamada falla, expira o
devuelve algo no parseable.

Detrás de `RAG_LLM_JUDGE_ENABLED` (default False). Costo ~1 llamada barata por
categoría; ver estimación en la bitácora.
"""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.engine.llm_client import _call_llm

logger = structlog.get_logger(__name__)

# Qué tiene que buscar el juez en cada categoría. Frases derivadas del bloque
# CONCEPTO de cada prompt de extracción (analysis/extraction/prompts/*.txt).
_CATEGORY_BRIEF: dict[str, str] = {
    "objeto_alcance": (
        "QUÉ se licita: objeto y alcance de la contratación, ítems/renglones/lotes y "
        "cantidades, destino, modalidad de adjudicación. NO especificaciones técnicas "
        "de detalle, NO plazos, garantías, requisitos ni criterios."
    ),
    "requisitos_admisibilidad": (
        "Documentación/condiciones OBLIGATORIAS para que la oferta no sea rechazada de "
        "entrada: certificados, inscripciones en registros, constancias fiscales, "
        "balances, DDJJ, capacidad y experiencia mínimas, certificaciones exigidas, y "
        "condiciones técnicas mínimas EXCLUYENTES (si no se cumplen, oferta inadmisible)."
    ),
    "garantias": (
        "Garantías FINANCIERAS que el oferente debe constituir: mantenimiento de oferta, "
        "cumplimiento de contrato, anticipo, impugnación — montos/porcentajes, forma de "
        "constitución (póliza, caución, aval, depósito), vigencia, devolución. NO "
        "garantía técnica de productos (hardware/software)."
    ),
    "plazos_clave": (
        "Hitos temporales que un oferente debe tener en su calendario: presentación de "
        "ofertas, apertura, mantenimiento/validez de la oferta, consultas, impugnaciones, "
        "plazos de entrega o ejecución, firma de contrato. Fechas y duraciones."
    ),
    "criterios_evaluacion": (
        "CÓMO se decide el ganador: método de adjudicación (menor precio, puntaje "
        "ponderado), factores evaluados y su ponderación en % o puntos, puntaje técnico "
        "mínimo, fórmulas de evaluación."
    ),
    "causales_rechazo": (
        "Motivos por los que una oferta se descalifica SIN evaluarla: rechazo formal, "
        "desestimación, exclusión, falta de documentación, garantía insuficiente, "
        "inhabilitación, presentación fuera de término, falsedad de datos."
    ),
    "anexos_obligatorios": (
        "Formularios y anexos que el pliego provee para completar y presentar con la "
        "oferta: planilla de cotización, declaraciones juradas, modelos de nota, "
        "Anexo I/II/III..., formularios oficiales."
    ),
    "identificacion_procedimiento": (
        "Datos que identifican el procedimiento: organismo/jurisdicción convocante, "
        "número de expediente, número y tipo de procedimiento (licitación pública/"
        "privada, concurso, contratación directa), presupuesto oficial."
    ),
    "riesgos": (
        "Riesgos comerciales o de participación para el oferente: multas y penalidades, "
        "plazos de entrega exigentes, moneda y tipo de cambio, forma de pago, alta "
        "competencia, direccionamiento a una marca, causales de rescisión."
    ),
    "preview_criterios": (
        "Condiciones comerciales de decisión rápida: forma de pago, moneda de "
        "cotización, tipo de cambio, anticipo financiero, responsabilidad por costos "
        "logísticos o de instalación."
    ),
    "eventos_temporales": (
        "Eventos e hitos con fecha o plazo del proceso: recepción del pliego, apertura, "
        "adjudicación, firma, entregas, y plazos contados desde esos eventos."
    ),
}

_CHUNK_CHARS = 460


def llm_judge_rerank(
    query: str,
    category: str,
    chunks: list[dict[str, Any]],
    *,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Reordena `chunks` (ya cortados a la ventana del juez) por relevancia
    a `category` según el LLM. Devuelve la lista reordenada; ante cualquier
    fallo, devuelve `chunks` sin tocar."""
    if len(chunks) < 3:
        return chunks

    brief = _CATEGORY_BRIEF.get(category, category)
    lines = []
    for i, ch in enumerate(chunks):
        hp = " > ".join(str(h) for h in (ch.get("heading_path") or [])[-2:])
        body = " ".join(str(ch.get("content") or "").split())[:_CHUNK_CHARS]
        lines.append(f"[{i}] ({hp}) {body}")
    payload = "\n".join(lines)

    system_msg = (
        "Sos un evaluador experto en pliegos de licitación pública argentinos. "
        "Devolvés SOLO JSON válido."
    )
    human_msg = (
        f"Categoría: {category}\nQué buscar: {brief}\n\n"
        f"Consulta de recuperación: {query}\n\n"
        "Para cada fragmento, asigná una relevancia entera de 0 a 3 según cuánto "
        "contenido propio de esta categoría contiene (3 = el fragmento ES de esta "
        "categoría; 0 = no tiene nada). Formato exacto: "
        '{"rel":[{"i":0,"r":3},{"i":1,"r":0}, ...]}\n\n'
        f"Fragmentos:\n{payload}"
    )
    messages = [("system", system_msg), ("human", human_msg)]

    try:
        parsed, _usage = _call_llm(messages, correlation_id=f"{correlation_id}-judge-{category}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "llm_judge_failed_fallback_rrf",
            correlation_id=correlation_id,
            category=category,
            error=str(exc)[:200],
        )
        return chunks

    rows = parsed.get("rel") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or not rows:
        logger.warning(
            "llm_judge_unparseable_fallback_rrf", correlation_id=correlation_id, category=category
        )
        return chunks

    rel: dict[int, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        i, r = row.get("i"), row.get("r")
        if isinstance(i, int) and isinstance(r, (int, float)) and 0 <= i < len(chunks):
            rel[i] = int(r)

    if not rel:
        return chunks

    # orden estable: por relevancia desc, y a igualdad, orden RRF original
    order = sorted(range(len(chunks)), key=lambda i: (-rel.get(i, 0), i))
    reordered = [chunks[i] for i in order]

    moved = sum(1 for pos, i in enumerate(order) if pos != i)
    logger.info(
        "llm_judge_applied",
        correlation_id=correlation_id,
        category=category,
        window=len(chunks),
        scored=len(rel),
        positions_changed=moved,
        top3_rel=[rel.get(i, 0) for i in order[:3]],
    )
    return reordered
