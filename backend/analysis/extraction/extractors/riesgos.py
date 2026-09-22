from __future__ import annotations

import json

import structlog

from analysis.extraction.engine.llm_client import _call_llm
from analysis.extraction.engine.prompts import _load_prompt
from analysis.extraction.schemas import SubtipoRiesgo, TipoRiesgo
from analysis.extraction.state import GraphState

logger = structlog.get_logger(__name__)

# REDISEÑO (2026-09-18, pedido explícito de la usuaria tras auditar por qué
# `riesgos` era la categoría con peor desempeño de las 11): la versión
# anterior escaneaba chunks crudos igual que cualquier otra categoría, y le
# pedía al LLM juzgar por su cuenta "¿esto es un riesgo?" sobre texto sin
# procesar -- una tarea inherentemente subjetiva (casi cualquier cláusula
# puede sonar riesgosa si se le agrega una consecuencia negativa). 3 intentos
# de arreglarlo a puro prompt fallaron (ver memoria: regla "NO INCLUIR",
# segunda pasada de verificación -- empeoró todo, ajuste de consolidación).
#
# El propio golden set de referencia reveló el patrón real: cada riesgo
# "bueno" es en realidad un COMENTARIO sobre un hecho que YA está en otra
# categoría (garantías, plazos, requisitos, causales, criterios) -- nunca un
# descubrimiento nuevo del texto crudo. Este extractor ahora refleja eso:
# en vez de volver a leer el pliego, arma un "digest" numerado de lo que esas
# 5 categorías YA extrajeron (y ya verificaron sus propias citas) y le pide
# al LLM que seleccione/priorice los 3-5 MÁS materialmente riesgosos --
# tarea de selección/síntesis, no de juicio sobre texto libre.
#
# `source_references` de cada riesgo final se RESUELVEN EN CÓDIGO a partir
# de los hechos referenciados (`indices`), reusando sus citas ya verificadas
# -- el LLM nunca inventa ni repite una cita, solo apunta a qué hecho(s) se
# refiere. Si no hay ningún hecho fuente con cita real, el riesgo se
# descarta (no se inventa evidencia).
#
# `forma_pago`/`moneda`/`tipo_cambio`/`anticipo_financiero`/
# `responsabilidad_costos_logisticos`/`multas_penalidades` YA NO son
# responsabilidad de esta categoría -- se extraen directo en
# `preview_criterios.txt` (ver ese prompt). El scope de `riesgos` se acota a
# condiciones ESTRUCTURALES: plazos ajustados, garantías onerosas, requisitos
# que direccionan a un proveedor específico, causales de descalificación
# severas, criterios de evaluación desfavorables.
_MAX_DIGEST_ITEMS_PER_CATEGORY = 20
_MAX_VALOR_CHARS = 220

_SOURCE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("garantias", "Garantías"),
    ("plazos", "Plazos clave"),
    ("requisitos_admisibilidad", "Requisitos de admisibilidad"),
    ("causales", "Causales de rechazo"),
    ("criterios", "Criterios de evaluación"),
)

_VALID_TIPOS = {tipo.value for tipo in TipoRiesgo}
_VALID_SUBTIPOS = {subtipo.value for subtipo in SubtipoRiesgo}


def _digest_valor(item: dict) -> str:
    valor = str(item.get("valor") or "").strip()
    if len(valor) > _MAX_VALOR_CHARS:
        valor = valor[:_MAX_VALOR_CHARS].rstrip() + "..."
    return valor


def _build_digest(state: GraphState) -> list[dict]:
    """Lista numerada de hechos ya extraídos (con el item original adjunto
    para poder resolver sus `source_references` después). El índice es
    global a través de las 5 categorías -- es lo que el LLM usa para
    referenciar de qué hecho(s) habla cada riesgo."""
    digest: list[dict] = []
    for state_key, label in _SOURCE_CATEGORIES:
        items = state.get(state_key) or []
        for item in items[:_MAX_DIGEST_ITEMS_PER_CATEGORY]:
            valor = _digest_valor(item)
            if not valor:
                continue
            digest.append(
                {
                    "index": len(digest),
                    "categoria": label,
                    "tipo": str(item.get("tipo") or ""),
                    "valor": valor,
                    "_source_item": item,
                }
            )
    return digest


def _digest_payload(digest: list[dict]) -> list[dict]:
    return [
        {"index": entry["index"], "categoria": entry["categoria"], "tipo": entry["tipo"], "valor": entry["valor"]}
        for entry in digest
    ]


def _valid_indices(digest: list[dict], raw_indices: object) -> list[int]:
    if not isinstance(raw_indices, list):
        return []
    return [idx for idx in raw_indices if isinstance(idx, int) and 0 <= idx < len(digest)]


def _resolve_source_references(digest: list[dict], indices: list[int]) -> list[dict]:
    """Reusa las citas YA VERIFICADAS de los hechos referenciados -- nunca
    genera ni pide una cita nueva al LLM de riesgos."""
    refs: list[dict] = []
    seen: set[str] = set()
    for idx in indices:
        source_item = digest[idx]["_source_item"]
        for ref in source_item.get("source_references") or []:
            signature = f"{ref.get('document_id')}|{ref.get('page_number')}|{ref.get('citation')}"
            if signature in seen:
                continue
            seen.add(signature)
            refs.append(ref)
    return refs


def _resolve_confidence(digest: list[dict], indices: list[int]) -> float:
    confidences = [
        float(digest[idx]["_source_item"].get("confidence", 0.0) or 0.0) for idx in indices
    ]
    if not confidences:
        return 0.5
    return round(sum(confidences) / len(confidences), 2)


def extractor_riesgos(state: GraphState) -> GraphState:
    correlation_id = str(state.get("correlation_id", "riesgos"))
    digest = _build_digest(state)

    if not digest:
        logger.info("riesgos_digest_empty", correlation_id=correlation_id)
        return {"riesgos": [], "riesgos_status": "success"}

    prompt_template = _load_prompt("riesgos.txt")
    prompt = prompt_template.replace(
        "{digest}", json.dumps(_digest_payload(digest), ensure_ascii=False, indent=2)
    )

    messages = [
        (
            "system",
            "Analizás hechos ya extraídos de un pliego de licitación para identificar "
            "los riesgos comerciales más materiales para un oferente. Devolvés solo "
            "JSON válido.",
        ),
        ("human", prompt),
    ]

    try:
        parsed, usage = _call_llm(messages, correlation_id=correlation_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("riesgos_llm_failed", correlation_id=correlation_id, error=str(exc)[:200])
        return {"riesgos": [], "riesgos_status": "failed"}

    raw_riesgos = parsed.get("riesgos")
    if not isinstance(raw_riesgos, list):
        raw_riesgos = []

    items: list[dict] = []
    for raw in raw_riesgos:
        if not isinstance(raw, dict):
            continue
        indices = _valid_indices(digest, raw.get("indices"))
        if not indices:
            continue
        source_refs = _resolve_source_references(digest, indices)
        if not source_refs:
            # Sin ninguna cita ya verificada para respaldarlo -- se descarta
            # en vez de inventar evidencia.
            continue
        explicacion = str(raw.get("explicacion") or "").strip()
        if not explicacion:
            continue

        tipo = str(raw.get("tipo") or "").strip()
        if tipo not in _VALID_TIPOS:
            tipo = TipoRiesgo.OTRO.value
        subtipo = str(raw.get("subtipo") or "").strip()
        if subtipo not in _VALID_SUBTIPOS:
            subtipo = SubtipoRiesgo.OTRO_EXPLICITO.value

        items.append(
            {
                "tipo": tipo,
                "subtipo": subtipo,
                "valor": explicacion,
                "metadata": {"derivado_de_indices": indices},
                "confidence": _resolve_confidence(digest, indices),
                "source_references": source_refs,
                "extraction_status": "success",
            }
        )

    logger.info(
        "riesgos_synthesized",
        correlation_id=correlation_id,
        digest_size=len(digest),
        riesgos_llm_candidatos=len(raw_riesgos),
        riesgos_finales=len(items),
    )

    return {"riesgos": items, "riesgos_status": "success"}
