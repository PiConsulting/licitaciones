"""Entrypoint del grafo de extraccion (LangGraph): setup (carga documentos + candidate pool) -> extractores en paralelo -> merge (dedupe + confianza) -> synthesize (narrativa)."""
from __future__ import annotations

from collections import defaultdict
import re
import time
import unicodedata

import structlog
from langgraph.graph import END, StateGraph

from analysis.extraction.extractors import (
    extractor_anexos_obligatorios,
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_eventos_temporales,
    extractor_garantias,
    extractor_identificacion_procedimiento,
    extractor_objeto_alcance,
    extractor_plazos,
    extractor_requisitos_admisibilidad,
    extractor_riesgos,
    extractor_preview_criterios,
)
from analysis.extraction.graph.canonicalization import (
    _canonical_causal_tipo,
    _canonical_garantia_tipo,
    _canonical_identificacion_tipo,
    _canonical_riesgo_subtipo,
    _garantia_dedup_value,
    _normalized_referencia_key,
    _plazo_dedup_value,
)
from analysis.extraction.graph.confidence import (
    _category_confidence,
    _normalize_confidence,
    _penalize_unverifiable,
)
from analysis.extraction.graph.dedup_merge import (
    _merge_duplicate_items_by_key,
    _merge_duplicate_typed_items,
    _normalized_valor_key,
)
from analysis.extraction.graph.documents import (
    _build_document_labels,
    _build_document_mapping,
    _cleanup_temp_highlights,
    _stampar_nombre_de_documento,
)
from analysis.extraction.engine.item_merging import _merge_singleton_tipo_duplicates
from analysis.extraction.graph.validation import (
    _drop_items_without_sources,
    _keep_schema_valid_items,
    _sort_items_by_primary_document,
)
from analysis.extraction.schemas import (
    NOT_ANALYZED_STATUS,
    AnexoObligatorioItem,
    CausalRechazoItem,
    CriterioEvaluacionItem,
    ExtractedData,
    GarantiaItem,
    IdentificacionProcedimientoItem,
    ObjetoAlcanceItem,
    PlazoItem,
    TipoObjetoAlcance,
    PreviewCriterioItem,
    RequisitoAdmisibilidadItem,
    RiesgoItem,
)
from analysis.extraction.state import GraphState
from analysis.extraction.synthesis import (
    NARRATIVE_CATEGORIES,
    enrich_narrative_with_highlights,
    run_synthesis,
)

logger = structlog.get_logger(__name__)

_TABLE_COLUMN_MARKER_RE = re.compile(r"\bcol_\d+\s*:\s*", re.IGNORECASE)
_ONLY_TABLE_MARKERS_RE = re.compile(r"^(?:\s*col_\d+\s*:\s*)+$", re.IGNORECASE)
_NON_PROCEDURAL_TEMPORAL_RE = re.compile(
    r"\b(forma\s+de\s+pago|vencimientos?\s+de\s+pago|cheques?\s+de\s+pago|"
    r"pago\s+diferido|factura(?:s)?|reajuste|actualizacion\s+de\s+precio|"
    r"actualización\s+de\s+precio|vigencia\s+de\s+la\s+licencia)\b",
    re.IGNORECASE,
)
_PROCEDURAL_EVENT_HINT_RE = re.compile(
    r"\b(apertura|presentacion|presentación|adjudicacion|adjudicación|"
    r"notificacion|notificación|firma|suscripcion|suscripción|recepcion|"
    r"recepción|entrega|inicio|cierre|consulta|impugnacion|impugnación|"
    r"evaluacion|evaluación)\b",
    re.IGNORECASE,
)

_GLOBAL_CANDIDATE_POOL_QUERY = (
    "Información relevante de un pliego de licitación pública: objeto y "
    "alcance de la contratación, requisitos de admisibilidad, plazos y "
    "fechas clave, garantías financieras, causales de rechazo de la oferta, "
    "anexos y formularios obligatorios, criterios de evaluación y "
    "adjudicación, identificación del procedimiento y del organismo "
    "convocante, y riesgos comerciales para el oferente."
)


def _normalize_temporal_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    lowered = without_accents.lower()
    cleaned = re.sub(r"\s+", " ", lowered)
    return cleaned.strip()


def _clean_temporal_fragment(fragment: str | None) -> str | None:
    if not fragment:
        return fragment
    cleaned = _TABLE_COLUMN_MARKER_RE.sub(" ", str(fragment))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or fragment


def _is_non_procedural_temporal_hito(nombre: str, fragmento: str | None) -> bool:
    normalized_name = _normalize_temporal_text(nombre)
    normalized_fragment = _normalize_temporal_text(fragmento)
    combined = f"{normalized_name} {normalized_fragment}".strip()

    # Duraciones de vigencia/licenciamiento son condiciones comerciales, no
    # hitos operativos del proceso temporal del timeline.
    if "vigencia de la licencia" in combined:
        return True

    if not _NON_PROCEDURAL_TEMPORAL_RE.search(combined):
        return False

    # Si hay una señal procesal fuerte, no filtramos para evitar falsos
    # negativos en eventos legítimos que mencionen pago en su contexto.
    return _PROCEDURAL_EVENT_HINT_RE.search(combined) is None


def _is_usable_temporal_hito(nombre: str, fragmento: str | None) -> bool:
    normalized_name = _normalize_temporal_text(nombre)
    if not normalized_name:
        return False

    if _ONLY_TABLE_MARKERS_RE.match(nombre or ""):
        return False

    if _is_non_procedural_temporal_hito(nombre, fragmento):
        return False

    cleaned_fragment = _clean_temporal_fragment(fragmento) or ""
    cleaned_normalized = _normalize_temporal_text(cleaned_fragment)
    if cleaned_normalized.startswith("col_") and len(cleaned_normalized) < 24:
        return False

    return True


def _build_shared_candidate_pool(analysis_id: str, correlation_id: str) -> list[dict]:
    """Fase 3 del plan RAG v2 (2026-08-24, sección 4.2): UNA query de alto
    recall, sin boost de categoría, para poblar `state["global_candidates"]`.
    Cada rama de extracción (`_retrieve_with_category_priority` en
    `extractors/base.py`) la reusa antes de decidir si hace falta su propia
    query específica -- ver esa función para el resto del mecanismo.

    La query es deliberadamente genérica (los conceptos de las 9 categorías,
    no vocabulario de un pliego puntual) porque el objetivo acá no es
    precisión para una categoría, es cobertura amplia del análisis completo.
    Si la query falla (embeddings caídos, análisis no indexado, etc.) se
    degrada a `[]` -- cada rama, al recibir un pool vacío, hace exactamente
    su query específica de siempre, así que una falla acá nunca bloquea la
    extracción.
    """
    from infra.config import get_settings

    settings = get_settings()
    if not settings.use_shared_candidate_pool:
        return []

    try:
        from infra.ports.pgvector_search import search_hybrid

        candidates = search_hybrid(
            query=_GLOBAL_CANDIDATE_POOL_QUERY,
            analysis_id=analysis_id,
            top_k=settings.shared_candidate_pool_top_k,
            keyword_query=None,
            category=None,
        )
        logger.info(
            "shared_candidate_pool_built",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            pool_size=len(candidates),
            requested_top_k=settings.shared_candidate_pool_top_k,
        )
        return candidates
    except Exception as exc:  # noqa: BLE001
        # No debe tumbar setup_node -- el pool compartido es una optimización,
        # no un requisito. Cada rama hace su query específica igual si esto
        # queda vacío.
        logger.warning(
            "shared_candidate_pool_build_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            error=str(exc)[:300],
        )
        return []


def setup_node(state: GraphState) -> GraphState:
    logger.info(
        "setup_node_started",
        correlation_id=state["correlation_id"],
        analysis_id=state["analysis_id"],
    )
    cached_mapping = state.get("document_id_to_blob_path")
    cached_labels = state.get("document_labels")
    cached_candidates = state.get("global_candidates")

    can_reuse = (
        isinstance(cached_mapping, dict)
        and isinstance(cached_labels, dict)
        and isinstance(cached_candidates, list)
        and bool(cached_mapping)
    )

    if can_reuse:
        document_mapping = cached_mapping
        document_labels = cached_labels
        global_candidates = cached_candidates
        logger.info(
            "setup_node_reused",
            correlation_id=state["correlation_id"],
            analysis_id=state["analysis_id"],
            documents=len(document_mapping),
            candidates=len(global_candidates),
        )
    else:
        document_mapping = _build_document_mapping(state["analysis_id"], state.get("db_session"))
        document_labels = _build_document_labels(state["analysis_id"], state.get("db_session"))
        global_candidates = _build_shared_candidate_pool(state["analysis_id"], state["correlation_id"])
        logger.info(
            "setup_node_computed",
            correlation_id=state["correlation_id"],
            analysis_id=state["analysis_id"],
            documents=len(document_mapping),
            candidates=len(global_candidates),
        )

    state.update(
        {
            "preview_criterios": [],
            "preview_criterios_status": "pending",
            "objeto_alcance": [],
            "objeto_alcance_status": "pending",
            "requisitos_admisibilidad": [],
            "requisitos_admisibilidad_status": "pending",
            "plazos": [],
            "plazos_status": "pending",
            "garantias": [],
            "garantias_status": "pending",
            "causales": [],
            "causales_status": "pending",
            "anexos": [],
            "anexos_status": "pending",
            "criterios": [],
            "criterios_status": "pending",
            "identificacion": [],
            "identificacion_status": "pending",
            "conflicts": [],
            "document_id_to_blob_path": document_mapping,
            "document_labels": document_labels,
            "global_candidates": global_candidates,
        }
    )
    logger.info("setup_node_completed", correlation_id=state["correlation_id"])
    return state


def merge_node(state: GraphState) -> GraphState:
    correlation_id = state["correlation_id"]
    logger.info(
        "merge_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"]
    )

    plazos = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("plazos", [])
    ]
    objeto_alcance = [
        _normalize_confidence(_penalize_unverifiable(item))
        for item in state.get("objeto_alcance", [])
    ]
    requisitos_admisibilidad = [
        _normalize_confidence(_penalize_unverifiable(item))
        for item in state.get("requisitos_admisibilidad", [])
    ]
    garantias = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("garantias", [])
    ]
    causales = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("causales", [])
    ]
    anexos = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("anexos", [])
    ]
    criterios = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("criterios", [])
    ]
    identificacion = [
        _normalize_confidence(_penalize_unverifiable(item))
        for item in state.get("identificacion", [])
    ]
    preview_criterios = [
        _normalize_confidence(_penalize_unverifiable(item))
        for item in state.get("preview_criterios", [])
    ]
    riesgos = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("riesgos", [])
    ]
    
    # Timeline: un solo extractor fusionado ("eventos_temporales") que ya
    # decide él mismo, leyendo el pliego completo, qué es un hito con fecha
    # propia y qué es un plazo relativo a otro hito -- ver
    # `analysis/extraction/prompts/eventos_temporales.txt`. Para no tocar
    # nada río abajo (materializer.py, frontend, tests), acá derivamos las
    # DOS vistas legacy (`eventos_temporales`/`plazos_relativos`) de esa
    # única lista fusionada, con la forma exacta que tenían cuando salían de
    # dos extractores independientes.
    hitos_temporales = state.get("eventos_temporales", [])

    eventos_temporales: list[dict] = []
    plazos_relativos: list[dict] = []
    seen_event_names: set[str] = set()
    seen_plazos: set[tuple] = set()

    for h in hitos_temporales:
        nombre = str(h.get("nombre") or "").strip()
        fuente_fragmento = _clean_temporal_fragment(h.get("fuente_fragmento"))
        if not _is_usable_temporal_hito(nombre, fuente_fragmento):
            logger.info(
                "timeline_hito_filtrado",
                correlation_id=correlation_id,
                analysis_id=state["analysis_id"],
                nombre=nombre,
            )
            continue

        event_name_key = _normalize_temporal_text(nombre)
        if event_name_key not in seen_event_names:
            seen_event_names.add(event_name_key)
            eventos_temporales.append(
                {
                    "nombre": nombre,
                    "fecha_explicita": h.get("fecha_explicita"),
                    "origen_fecha": h.get("origen_fecha"),
                    # True salvo que el LLM marque explícitamente que este hito solo
                    # se agregó para poder referenciarlo como evento_disparador de
                    # otro ítem (regla 2/mencion_propia del prompt) -- default True
                    # (no False) para no marcar como "inferido" a un hito real si el
                    # LLM omitiera el campo en alguna corrida.
                    "mencion_propia": h.get("mencion_propia", True),
                    "fuente_documento_id": h.get("fuente_documento_id"),
                    "fuente_pagina": h.get("fuente_pagina"),
                    "fuente_fragmento": fuente_fragmento,
                    "_source_document_id": h.get("_source_document_id"),
                }
            )

        evento_disparador = str(h.get("evento_disparador") or "").strip()
        if not evento_disparador:
            continue

        plazo_payload = {
            "descripcion": nombre,
            "cantidad": h.get("cantidad"),
            "unidad": h.get("unidad"),
            "tipo_dias": h.get("tipo_dias"),
            "evento_disparador": evento_disparador,
            "direccion": h.get("direccion"),
            "es_plazo_maximo": h.get("es_plazo_maximo", False),
            "fuente_documento_id": h.get("fuente_documento_id"),
            "fuente_pagina": h.get("fuente_pagina"),
            "fuente_fragmento": fuente_fragmento,
            "_source_document_id": h.get("_source_document_id"),
        }
        dedup_key = (
            _normalize_temporal_text(nombre),
            _normalize_temporal_text(evento_disparador),
            int(h.get("cantidad") or 0),
            str(h.get("unidad") or ""),
            str(h.get("tipo_dias") or ""),
            str(h.get("direccion") or ""),
        )
        if dedup_key in seen_plazos:
            continue
        seen_plazos.add(dedup_key)
        plazos_relativos.append(plazo_payload)

    # Diagnóstico: si el LLM extrajo hitos pero NINGUNO tiene
    # evento_disparador, es una señal fuerte de que se está saltando la
    # mitad "plazo relativo" de la categoría (ver regla 0 del prompt) -- no
    # bloquea nada, pero deja rastro en logs para no tener que adivinar la
    # próxima vez que alguien reporte "no aparecen los plazos relativos".
    if hitos_temporales and not plazos_relativos:
        logger.warning(
            "eventos_temporales_sin_plazos_relativos",
            correlation_id=correlation_id,
            analysis_id=state["analysis_id"],
            hitos_extraidos=len(hitos_temporales),
        )

    # FIX (2026-08-22): ya no se canonicaliza `tipo` (eliminado del schema,
    # ver PlazoItem en `schemas.py`). El agrupamiento para dedup usa el valor
    # del plazo (`_plazo_dedup_value`) solo -- sin combinarlo con un tipo, que
    # ya no existe.
    plazos = _merge_duplicate_items_by_key(plazos, lambda item: (_plazo_dedup_value(item),))

    for garantia in garantias:
        garantia["tipo"] = _canonical_garantia_tipo(str(garantia.get("tipo", "")))
    garantias = _merge_duplicate_typed_items(garantias, _garantia_dedup_value)
    objeto_alcance = _merge_duplicate_items_by_key(
        objeto_alcance, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    # FIX (2026-09-14, Fase 2 de la auditoría RAG): el dedup de arriba solo
    # fusiona duplicados con el MISMO valor -- no detecta dos ítems del mismo
    # `tipo` SINGLETON ("UN ítem resumen_objeto", "UN ítem lugar_entrega",
    # ver objeto_alcance.txt) con valores DISTINTOS, que el split de lotes
    # dentro de un documento (`_split_oversized_groups`, `base.py`) puede
    # producir -- cada lote ve un subconjunto de chunks distinto, y uno que no
    # tiene el dato igual emite el ítem singleton con un placeholder mientras
    # otro sí lo encuentra. `item` es el único tipo de esta categoría que
    # puede repetirse legítimamente (uno por renglón/ítem licitado).
    objeto_alcance = _merge_singleton_tipo_duplicates(
        objeto_alcance,
        {tipo.value for tipo in TipoObjetoAlcance if tipo != TipoObjetoAlcance.ITEM},
        category="objeto_alcance",
        correlation_id=correlation_id,
    )
    requisitos_admisibilidad = _merge_duplicate_items_by_key(
        requisitos_admisibilidad,
        lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item)),
    )
    for causal in causales:
        causal["tipo"] = _canonical_causal_tipo(str(causal.get("tipo", "")))
    causales = _merge_duplicate_items_by_key(causales, lambda item: (_normalized_valor_key(item),))
    anexos = _merge_duplicate_items_by_key(
        anexos, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    criterios = _merge_duplicate_items_by_key(
        criterios, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    identificacion = _merge_duplicate_items_by_key(
        identificacion, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    preview_criterios = _merge_duplicate_items_by_key(
        preview_criterios,
        lambda item: (str(item.get("tipo", "")),),
    )
    for riesgo in riesgos:
        riesgo["subtipo"] = _canonical_riesgo_subtipo(str(riesgo.get("subtipo", "")))
    riesgos = _merge_duplicate_items_by_key(
        riesgos,
        lambda item: (
            str(item.get("tipo", "")),
            str(item.get("subtipo", "")),
            _normalized_valor_key(item),
        ),
    )
    calidad: dict[str, dict[str, int]] = {}

    objeto_alcance, objeto_alcance_status = _drop_items_without_sources(
        objeto_alcance,
        str(state.get("objeto_alcance_status", "unknown")),
        category="objeto_alcance",
        quality=calidad,
    )
    requisitos_admisibilidad, requisitos_admisibilidad_status = _drop_items_without_sources(
        requisitos_admisibilidad,
        str(state.get("requisitos_admisibilidad_status", "unknown")),
        category="requisitos_admisibilidad",
        quality=calidad,
    )
    plazos, plazos_status = _drop_items_without_sources(
        plazos, str(state.get("plazos_status", "unknown")), category="plazos_clave", quality=calidad
    )
    garantias, garantias_status = _drop_items_without_sources(
        garantias,
        str(state.get("garantias_status", "unknown")),
        category="garantias",
        quality=calidad,
    )
    causales, causales_status = _drop_items_without_sources(
        causales,
        str(state.get("causales_status", "unknown")),
        category="causales_rechazo",
        quality=calidad,
    )
    anexos, anexos_status = _drop_items_without_sources(
        anexos,
        str(state.get("anexos_status", "unknown")),
        category="anexos_obligatorios",
        quality=calidad,
    )
    criterios, criterios_status = _drop_items_without_sources(
        criterios,
        str(state.get("criterios_status", "unknown")),
        category="criterios_evaluacion",
        quality=calidad,
    )
    identificacion, identificacion_status = _drop_items_without_sources(
        identificacion,
        str(state.get("identificacion_status", "unknown")),
        category="identificacion_procedimiento",
        quality=calidad,
    )
    preview_criterios, preview_criterios_status = _drop_items_without_sources(
        preview_criterios,
        str(state.get("preview_criterios_status", "unknown")),
        category="preview_criterios",
        quality=calidad,
        keep_not_found_without_sources=True,
    )
    riesgos, riesgos_status = _drop_items_without_sources(
        riesgos,
        str(state.get("riesgos_status", "unknown")),
        category="riesgos",
        quality=calidad,
    )
    identificacion_canonica: list[dict] = []
    for item in identificacion:
        canonical_tipo = _canonical_identificacion_tipo(str(item.get("tipo", "")))
        if canonical_tipo is None:
            continue
        canonical_item = dict(item)
        canonical_item["tipo"] = canonical_tipo
        identificacion_canonica.append(canonical_item)
    objeto_alcance, objeto_alcance_status = _keep_schema_valid_items(
        objeto_alcance,
        ObjetoAlcanceItem,
        objeto_alcance_status,
        category="objeto_alcance",
        correlation_id=correlation_id,
        quality=calidad,
    )
    requisitos_admisibilidad, requisitos_admisibilidad_status = _keep_schema_valid_items(
        requisitos_admisibilidad,
        RequisitoAdmisibilidadItem,
        requisitos_admisibilidad_status,
        category="requisitos_admisibilidad",
        correlation_id=correlation_id,
        quality=calidad,
    )
    requisitos_admisibilidad = _sort_items_by_primary_document(requisitos_admisibilidad)
    plazos, plazos_status = _keep_schema_valid_items(
        plazos,
        PlazoItem,
        plazos_status,
        category="plazos_clave",
        correlation_id=correlation_id,
        quality=calidad,
    )
    garantias, garantias_status = _keep_schema_valid_items(
        garantias,
        GarantiaItem,
        garantias_status,
        category="garantias",
        correlation_id=correlation_id,
        quality=calidad,
    )
    causales, causales_status = _keep_schema_valid_items(
        causales,
        CausalRechazoItem,
        causales_status,
        category="causales_rechazo",
        correlation_id=correlation_id,
        quality=calidad,
    )
    anexos, anexos_status = _keep_schema_valid_items(
        anexos,
        AnexoObligatorioItem,
        anexos_status,
        category="anexos_obligatorios",
        correlation_id=correlation_id,
        quality=calidad,
    )
    criterios, criterios_status = _keep_schema_valid_items(
        criterios,
        CriterioEvaluacionItem,
        criterios_status,
        category="criterios_evaluacion",
        correlation_id=correlation_id,
        quality=calidad,
    )
    identificacion_canonica, identificacion_status = _keep_schema_valid_items(
        identificacion_canonica,
        IdentificacionProcedimientoItem,
        identificacion_status,
        category="identificacion_procedimiento",
        correlation_id=correlation_id,
        quality=calidad,
    )
    preview_criterios, preview_criterios_status = _keep_schema_valid_items(
        preview_criterios,
        PreviewCriterioItem,
        preview_criterios_status,
        category="preview_criterios",
        correlation_id=correlation_id,
        quality=calidad,
    )
    riesgos, riesgos_status = _keep_schema_valid_items(
        riesgos,
        RiesgoItem,
        riesgos_status,
        category="riesgos",
        correlation_id=correlation_id,
        quality=calidad,
    )

    extracted_data = {
        "calidad_por_categoria": calidad,
        "objeto_alcance": objeto_alcance,
        "objeto_alcance_extraction_status": objeto_alcance_status,
        "objeto_alcance_confidence": _category_confidence(objeto_alcance),
        "requisitos_admisibilidad": requisitos_admisibilidad,
        "requisitos_admisibilidad_extraction_status": requisitos_admisibilidad_status,
        "requisitos_admisibilidad_confidence": _category_confidence(requisitos_admisibilidad),
        "plazos_clave": plazos,
        "plazos_clave_extraction_status": plazos_status,
        "plazos_clave_confidence": _category_confidence(plazos),
        "plazos": plazos,
        "plazos_extraction_status": plazos_status,
        "garantias": garantias,
        "garantias_extraction_status": garantias_status,
        "garantias_confidence": _category_confidence(garantias),
        "causales_rechazo": causales,
        "causales_rechazo_extraction_status": causales_status,
        "causales_extraction_status": causales_status,
        "causales_rechazo_confidence": _category_confidence(causales),
        "anexos_obligatorios": anexos,
        "anexos_obligatorios_extraction_status": anexos_status,
        "anexos_obligatorios_confidence": _category_confidence(anexos),
        "identificacion_procedimiento": identificacion_canonica,
        "identificacion_procedimiento_extraction_status": identificacion_status,
        "preview_criterios": preview_criterios,
        "preview_criterios_extraction_status": preview_criterios_status,
        "preview_criterios_confidence": _category_confidence(preview_criterios),
        "datos_procedimiento": identificacion,
        "datos_procedimiento_extraction_status": identificacion_status,
        "datos_procedimiento_confidence": _category_confidence(identificacion),
        "riesgos": riesgos,
        "riesgos_extraction_status": riesgos_status,
        "riesgos_confidence": _category_confidence(riesgos),
        "eventos_temporales": eventos_temporales,
        "eventos_temporales_extraction_status": state.get("eventos_temporales_status", "unknown"),
        "plazos_relativos": plazos_relativos,
        # Ya no hay un extractor separado para plazos_relativos -- ambas
        # vistas legacy se derivan de la misma extracción fusionada
        # ("eventos_temporales"), así que comparten su status.
        "plazos_relativos_extraction_status": state.get("eventos_temporales_status", "unknown"),
        "documentos_requeridos": [],
        "documentos_extraction_status": NOT_ANALYZED_STATUS,
        "criterios_evaluacion": criterios,
        "criterios_evaluacion_extraction_status": criterios_status,
        "criterios_evaluacion_confidence": _category_confidence(criterios),
        "restricciones_participacion": [],
        "restricciones_extraction_status": NOT_ANALYZED_STATUS,
        "cronograma_proceso": [],
        "cronograma_extraction_status": NOT_ANALYZED_STATUS,
        "estimacion_presupuesto": None,
        "presupuesto_extraction_status": NOT_ANALYZED_STATUS,
    }

    token_usage = {
        "objeto_alcance": state.get("objeto_alcance_token_usage", {}),
        "requisitos_admisibilidad": state.get("requisitos_admisibilidad_token_usage", {}),
        "plazos_clave": state.get("plazos_token_usage", {}),
        "garantias": state.get("garantias_token_usage", {}),
        "causales_rechazo": state.get("causales_token_usage", {}),
        "anexos_obligatorios": state.get("anexos_token_usage", {}),
        "criterios_evaluacion": state.get("criterios_token_usage", {}),
        "identificacion_procedimiento": state.get("identificacion_token_usage", {}),
        "preview_criterios": state.get("preview_criterios_token_usage", {}),
        "eventos_temporales": state.get("eventos_temporales_token_usage", {}),
    }

    conflicts: list[dict] = []

    def _conflict_document_ids(items: list[dict]) -> set[str]:
        ids: set[str] = set()
        for item in items:
            for ref in item.get("source_references") or []:
                if isinstance(ref, dict) and ref.get("document_id"):
                    ids.add(str(ref["document_id"]))
        return ids

    # FIX (2026-09-11, pregunta: "¿se avisa si dos chunks se contradicen
    # dentro del MISMO pliego?"): la detección de abajo agrupa por
    # `referencia`/`tipo` y compara valores -- nunca miró `document_id`, así
    # que YA avisaba igual si la contradicción era entre el cuerpo del
    # pliego y su propio anexo (mismo documento) que si era entre dos
    # documentos distintos. Lo único que estaba mal era el texto fijo
    # "en distintos documentos", que mentía en el caso intra-documento y
    # podía hacer pensar a quien revisa que el conflicto involucra un
    # archivo aparte cuando en realidad está en dos secciones del mismo PDF.
    # Ahora se verifica de verdad contra los `document_id` de las citas.

    # FIX (2026-08-22): se agrupaba por `tipo` (enum de 17 valores + "otro").
    # Como la enorme mayoría de los plazos caía en "otro" (ver
    # `_normalized_referencia_key`), este bloque terminaba comparando fechas
    # de plazos sin ninguna relación entre sí solo porque compartían el balde
    # "otro" -- falsos conflictos. Ahora agrupa por `referencia` (texto libre
    # que describe a qué plazo se refiere): dos ítems solo se comparan si el
    # LLM los tituló igual, que es una señal mucho más fuerte de que hablan
    # del mismo hito.
    plazos_by_referencia: dict[str, list[dict]] = defaultdict(list)
    for plazo in plazos:
        clave = _normalized_referencia_key(plazo)
        if clave:
            plazos_by_referencia[clave].append(plazo)

    for items in plazos_by_referencia.values():
        if len(items) > 1:
            fechas = {item.get("fecha") for item in items}
            if len(fechas) > 1:
                misma_referencia_en_un_solo_documento = len(_conflict_document_ids(items)) <= 1
                conflicts.append(
                    {
                        "category": "plazos",
                        "tipo": str(items[0].get("referencia") or "dato"),
                        "values": items,
                        "reason": (
                            "Fechas diferentes dentro del mismo documento"
                            if misma_referencia_en_un_solo_documento
                            else "Fechas diferentes en distintos documentos"
                        ),
                    }
                )

    garantias_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for garantia in garantias:
        garantias_by_tipo[str(garantia.get("tipo", ""))].append(garantia)

    for tipo, items in garantias_by_tipo.items():
        if tipo and len(items) > 1:
            montos = {(item.get("monto_porcentaje"), item.get("monto_valor")) for item in items}
            if len(montos) > 1:
                mismo_tipo_en_un_solo_documento = len(_conflict_document_ids(items)) <= 1
                conflicts.append(
                    {
                        "category": "garantias",
                        "tipo": tipo,
                        "values": items,
                        "reason": (
                            "Montos diferentes dentro del mismo documento"
                            if mismo_tipo_en_un_solo_documento
                            else "Montos diferentes en distintos documentos"
                        ),
                    }
                )

    validated = ExtractedData(**extracted_data)
    state["extracted_data"] = validated.model_dump()
    state["conflicts"] = conflicts
    state["extraction_metadata"] = {"token_usage": token_usage, "calidad_por_categoria": calidad}

    logger.info(
        "merge_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        conflicts_count=len(conflicts),
    )
    return state


def _build_chunk_indexes(
    analysis_id: str, correlation_id: str
) -> tuple[dict[str, dict], dict[tuple[str, int], list[dict]]]:
    """Enumera los chunks del análisis UNA vez y deriva los dos índices que
    necesita la síntesis.
    """
    try:
        from infra.ports.pgvector_search import fetch_all_analysis_chunks

        all_chunks, truncated = fetch_all_analysis_chunks(analysis_id)

        chunks_by_id: dict[str, dict] = {}
        chunks_by_doc_page: dict[tuple[str, int], list[dict]] = {}

        for chunk in all_chunks:
            chunk_id = chunk.get("id")
            if not chunk_id:
                analysis_id_field = chunk.get("analysis_id")
                document_id = chunk.get("document_id")
                chunk_index = chunk.get("chunk_index")
                if analysis_id_field and document_id is not None and chunk_index is not None:
                    chunk_id = f"{analysis_id_field}--{document_id}--{chunk_index}"

            if chunk_id:
                chunk["chunk_id"] = chunk_id
                chunks_by_id[chunk_id] = chunk

            doc_id = chunk.get("document_id")
            page = chunk.get("page_number")
            if doc_id and page:
                chunks_by_doc_page.setdefault((str(doc_id), int(page)), []).append(chunk)

        logger.info(
            "chunk_indexes_built",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            total_chunks=len(all_chunks),
            indexed_by_id=len(chunks_by_id),
            unique_doc_pages=len(chunks_by_doc_page),
            truncated=truncated,
        )

        return chunks_by_id, chunks_by_doc_page

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chunk_indexes_build_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            error=str(exc),
            message="Evidence-based highlighting no disponible",
        )
        return {}, {}


def synthesize_node(state: GraphState) -> GraphState:
    """Convierte cada categoria ya mergeada en una respuesta de experto (bloques
    en lenguaje natural), una llamada LLM liviana por categoria (no vuelve a
    buscar chunks). Si una categoria falla la sintesis, simplemente no lleva
    `_narrative` en `extracted_data` — el frontend cae a su propio fallback, asi
    que un fallo aca nunca deja una categoria sin respuesta ni tumba el resto.
    """
    correlation_id = state["correlation_id"]
    logger.info(
        "synthesize_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"]
    )

    extracted_data = state.get("extracted_data", {})
    metadata = state.get("extraction_metadata", {})
    token_usage_by_category = dict(metadata.get("token_usage", {}))
    document_mapping = state.get("document_id_to_blob_path", {})
    if not document_mapping:
        from infra.config import get_settings

        settings = get_settings()
        if settings.is_production:
            logger.warning(
                "highlight_unavailable_no_document_mapping",
                correlation_id=correlation_id,
                analysis_id=state["analysis_id"],
                reason="document_mapping is empty - highlights will not be computed",
            )

    chunks_by_id, chunks_by_doc_page = _build_chunk_indexes(state["analysis_id"], correlation_id)

    conflicts = state.get("conflicts") or []
    pending = [
        category_key
        for category_key in NARRATIVE_CATEGORIES
        if isinstance(extracted_data.get(category_key, []), list)
    ]

    def _synthesize_one(category_key: str):
        """Una categoría: 2da llamada al LLM (items ya mergeados -> narrativa).
        Devuelve `(narrative, token_usage)` o `None`. NO hace enriquecimiento de
        highlights -- eso queda para el ensamblado secuencial (PyMuPDF + I/O de
        blobs, fuera del pool)."""
        _syn_started = time.monotonic()
        result = run_synthesis(
            category_key=category_key,
            items=extracted_data.get(category_key, []),
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
            conflicts=conflicts,
        )
        if result is None:
            return None
        narrative, token_usage = result
        # Instrumentación (Paso 0.1): la síntesis es una 2da pasada al LLM por
        # categoría -- se cuenta aparte para ver cuánto pesa en costo/latencia.
        if isinstance(token_usage, dict):
            token_usage.setdefault("llm_calls", 1 if token_usage.get("total_tokens") else 0)
            token_usage["wall_time_seconds"] = round(time.monotonic() - _syn_started, 2)
        return narrative, token_usage

    # Paso 5 (plan rag-plan-latencia-2026-09-09): las 7-9 síntesis de categoría
    # son llamadas al LLM independientes entre sí (cada una parte de los items
    # YA mergeados de su categoría), así que se corren en paralelo con el mismo
    # patrón que el map-reduce de extracción: pool acotado + ensamblado
    # determinista recorriendo `NARRATIVE_CATEGORIES` en orden, con lo cual el
    # `extracted_data` resultante es idéntico al del modo secuencial -- lo único
    # que cambia es el wall-time. El tope real contra Azure lo pone el semáforo
    # global de `_call_llm` (LLM_MAX_CONCURRENCY). `SYNTHESIS_MAX_CONCURRENCY<=1`
    # = secuencial = comportamiento previo.
    from infra.config import get_settings

    synthesis_workers = min(
        len(pending),
        max(1, int(get_settings().synthesis_max_concurrency or 1)),
    )
    results_by_category: dict[str, object] = {}
    if synthesis_workers <= 1:
        for category_key in pending:
            try:
                results_by_category[category_key] = _synthesize_one(category_key)
            except Exception as exc:  # noqa: BLE001
                results_by_category[category_key] = exc
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(
            max_workers=synthesis_workers, thread_name_prefix="synthesis"
        ) as pool:
            future_to_category = {
                pool.submit(_synthesize_one, category_key): category_key
                for category_key in pending
            }
            for future, category_key in future_to_category.items():
                try:
                    results_by_category[category_key] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results_by_category[category_key] = exc

    synthesized = 0
    for category_key in pending:
        outcome = results_by_category.get(category_key)
        if isinstance(outcome, BaseException):
            logger.warning(
                "synthesis_category_failed",
                correlation_id=correlation_id,
                category=category_key,
                error=str(outcome),
            )
            continue
        if outcome is None:
            continue
        narrative, token_usage = outcome
        if document_mapping:
            narrative = enrich_narrative_with_highlights(
                narrative=narrative,
                document_id_to_blob_path=document_mapping,
                correlation_id=correlation_id,
                category_key=category_key,
                analysis_id=state["analysis_id"],
                chunks_by_doc_page=chunks_by_doc_page,
            )

        extracted_data[f"{category_key}_narrative"] = narrative.model_dump()
        token_usage_by_category[f"{category_key}_synthesis"] = token_usage
        synthesized += 1

    _stampar_nombre_de_documento(extracted_data, state.get("document_labels") or {})

    # `_sort_items_by_primary_document` ya corre en `merge_node`, pero ahí
    # `filename`/`is_primary` todavía no existen en source_references --
    # `_stampar_nombre_de_documento` recién los escribe acá arriba. Se
    # reordena de nuevo con los datos ya completos para que el orden
    # realmente refleje documento primario primero en el pipeline completo.
    if extracted_data.get("requisitos_admisibilidad"):
        extracted_data["requisitos_admisibilidad"] = _sort_items_by_primary_document(
            extracted_data["requisitos_admisibilidad"]
        )

    metadata["token_usage"] = token_usage_by_category
    state["extracted_data"] = extracted_data
    state["extraction_metadata"] = metadata

    logger.info(
        "synthesize_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        categories_synthesized=synthesized,
    )

    _cleanup_temp_highlights(state["analysis_id"])

    return state


builder = StateGraph(GraphState)

builder.add_node("setup", setup_node)
builder.add_node("extract_objeto_alcance", extractor_objeto_alcance)
builder.add_node("extract_plazos", extractor_plazos)
builder.add_node("extract_garantias", extractor_garantias)
builder.add_node("extract_causales", extractor_causales)
builder.add_node("extract_anexos", extractor_anexos_obligatorios)
builder.add_node("extract_requisitos", extractor_requisitos_admisibilidad)
builder.add_node("extract_criterios", extractor_criterios_evaluacion)
builder.add_node("extract_identificacion", extractor_identificacion_procedimiento)
builder.add_node("extract_preview_criterios", extractor_preview_criterios)
builder.add_node("extract_riesgos", extractor_riesgos)
builder.add_node("extract_eventos_temporales", extractor_eventos_temporales)
builder.add_node("merge", merge_node)
builder.add_node("synthesize", synthesize_node)

builder.set_entry_point("setup")

extractor_nodes = [
    "extract_objeto_alcance",
    "extract_plazos",
    "extract_garantias",
    "extract_causales",
    "extract_anexos",
    "extract_requisitos",
    "extract_criterios",
    "extract_identificacion",
    "extract_riesgos",
    "extract_eventos_temporales",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", "synthesize")
builder.add_edge("synthesize", END)

graph = builder.compile()


# FASE 1 ampliada (2026-09-03, pedido de reducir redundancia entre preview y
# categorias): garantias, plazos_clave, requisitos_admisibilidad y riesgos se
# promueven a fase 1 CON SU PROMPT COMPLETO de siempre -- no una version
# liviana -- porque preview_criterios ahora proyecta 4 de sus 10 items desde
# los resultados de estas 4 categorias (garantias_cauciones <- garantias,
# tiempo_entrega/mantenimiento_oferta <- plazos_clave,
# requisitos_tecnicos_excluyentes <- requisitos_admisibilidad filtrado,
# multas_penalidades <- riesgos filtrado) en vez de volver a preguntarselo al
# LLM con su propio query diluido. Fase 2 ya no las vuelve a correr -- ver
# `_PHASE1_EXTRACTED_KEYS`/`_PHASE2_EXTRACTED_KEYS` en `analysis/extraction/runner.py`.
#
# `extract_preview_criterios` deja de depender solo de "setup": ahora depende
# de que las 4 categorias fuente ya hayan terminado, porque su extractor lee
# `state["garantias"]`, `state["plazos"]`, `state["requisitos_admisibilidad"]`
# y `state["riesgos"]` para armar la proyeccion antes de llamar al LLM
# (liviano) por los 6 campos que no tienen categoria propia.
#
# FIX (2026-09-03) -- intento 1, insuficiente: la primera version de este
# grafo dejaba, ADEMAS de garantias/plazos/requisitos/riesgos ->
# extract_preview_criterios, los edges ORIGINALES garantias/plazos/
# requisitos/riesgos -> merge (diamante). Se saco ese camino directo, pero
# el error `InvalidUpdateError: At key 'preview_criterios': Can receive only
# one value per step` siguio pasando IDENTICO.
#
# FIX (2026-09-03) -- intento 2, tambien insuficiente: se encadenaron
# garantias -> plazos -> requisitos -> riesgos -> extract_preview_criterios
# en secuencia (un solo edge de entrada cada una) para sacarle a
# extract_preview_criterios sus 4 edges de entrada. Elimino ESE error, pero
# hizo aparecer el MISMO error en otra clave: `At key 'plazos'`. Log:
# "merge_node_started"/"merge_node_completed" corrian EN PARALELO con
# extract_plazos (arrancaba "plazos_clave" al mismo timestamp que
# "merge_node_started") -- es decir, "merge" (con 3 edges de entrada:
# objeto_alcance, identificacion, extract_preview_criterios) se disparaba en
# cuanto objeto_alcance/identificacion terminaban, SIN esperar a que la
# cadena secuencial (todavia en su segundo eslabon) llegara a
# extract_preview_criterios. Esto prueba que un nodo con edges de entrada de
# DISTINTA profundidad (algunos a 1 salto de "setup", otros a varios) NO
# espera de forma confiable a todos en esta version de LangGraph -- el
# patron que sí funciona ("merge" con 6-10 edges en el grafo completo,
# `graph` mas abajo) solo funciona porque TODOS esos edges estan a la MISMA
# profundidad (1 salto desde "setup"), no por una barrera real de "esperar a
# todos".
#
# FIX (2026-09-03) -- intento 3 (DESCARTADO, no se llego a commitear): cadena
# lineal de los 7 extractores, uno detras de otro, sin ningun fan-in. Sacaba
# el error pero mataba el paralelismo -- el usuario freno esto explicitamente
# ("las de categorias tienen que seguir como estaban antes en paralelo").
#
# CAUSA RAIZ REAL (encontrada leyendo el source de langgraph==1.2.10, no
# adivinando): `StateGraph.add_edge(start, end)` se comporta DISTINTO segun
# el tipo de `start`:
#   - Si `start` es un solo string, cada llamada arma un writer que empuja a
#     un canal `EphemeralValue(guard=False)` compartido por TODOS los edges
#     que apunten al mismo `end` (langgraph/graph/state.py:_add_edge, canal
#     "branch:to:<end>"). Ese canal es OR: `end` se agenda apenas CUALQUIERA
#     de sus predecesores escribe ahi (ver `_triggers()` en
#     langgraph/pregel/_algo.py -- itera los canales trigger del nodo y basta
#     con que UNO este disponible/mas nuevo que lo ya visto). Por eso, cuando
#     habiamos armado los fan-in con un `for nodo in lista: builder.add_edge(
#     nodo, "merge")`, "merge"/"extract_preview_criterios" se disparaban en
#     cuanto terminaba el PRIMER predecesor, sin esperar al resto.
#   - Si `start` es una LISTA de nombres, `add_edge` arma un canal
#     `NamedBarrierValue(names=set(starts))` (langgraph/channels/
#     named_barrier_value.py): acumula en `seen` los nombres que ya
#     escribieron, EN CUALQUIER superstep (no exige que lleguen en el mismo
#     paso), y solo queda "disponible" cuando `seen == names`, es decir
#     cuando escribieron TODOS. Esto es un join real, verdadero AND, y es
#     agnostico a la profundidad de cada predecesor -- literal en el
#     docstring de `add_edge`: "When multiple start nodes are provided, the
#     graph will wait for ALL of the start nodes to complete before
#     executing the end node."
#
# El "merge" del grafo completo (`graph` mas abajo, 10 extractores) nunca dio
# este error de casualidad: usa el MISMO patron de loop (`for nodo in
# extractor_nodes: builder.add_edge(nodo, "merge")`, canal OR), pero como los
# 10 predecesores estan a la MISMA profundidad (1 salto de "setup"), Pregel
# los corre a TODOS en el mismo superstep y no avanza al siguiente hasta que
# terminen todos -- el join "funciona" por la barrera sincronica de Pregel
# entre supersteps, no porque el canal realmente espere a todos. En fase 1,
# como objeto_alcance/identificacion (1 salto) y preview_criterios (varios
# saltos, via garantias/plazos/requisitos/riesgos) quedaban a profundidades
# distintas, esa coincidencia se rompia.
#
# FIX real: usar `add_edge([...], end)` con LISTA en cada punto de fan-in.
# Restaura el paralelismo original -- garantias/plazos/requisitos/riesgos
# corren en paralelo (barrera real antes de preview_criterios), y
# objeto_alcance/identificacion corren en paralelo entre si y con esas 4
# (barrera real antes de merge, sin importar que preview_criterios termine
# mas tarde por depender de las otras 4).

# Nodos extractores de fase 1 (7). Simétrico con `extractor_nodes_phase2`:
# tras el refactor de fases (garantias/plazos/requisitos/riesgos promovidos a
# fase 1) esta lista no existía y el builder de abajo agregaba los nodos
# inline. Se expone para tests y para tener el inventario de la fase en un
# solo lugar.
extractor_nodes_phase1 = [
    "extract_objeto_alcance",
    "extract_identificacion",
    "extract_garantias",
    "extract_plazos",
    "extract_requisitos",
    "extract_riesgos",
    "extract_preview_criterios",
]

builder_phase1 = StateGraph(GraphState)
builder_phase1.add_node("setup", setup_node)
builder_phase1.add_node("extract_preview_criterios", extractor_preview_criterios)
builder_phase1.add_node("extract_objeto_alcance", extractor_objeto_alcance)
builder_phase1.add_node("extract_identificacion", extractor_identificacion_procedimiento)
builder_phase1.add_node("extract_garantias", extractor_garantias)
builder_phase1.add_node("extract_plazos", extractor_plazos)
builder_phase1.add_node("extract_requisitos", extractor_requisitos_admisibilidad)
builder_phase1.add_node("extract_riesgos", extractor_riesgos)
builder_phase1.add_node("merge", merge_node)
builder_phase1.add_node("synthesize", synthesize_node)
builder_phase1.set_entry_point("setup")

# objeto_alcance/identificacion arrancan apenas termina "setup", en paralelo
# con la tanda de garantias/plazos/requisitos/riesgos (edges 1-a-1 desde un
# solo nodo -- eso nunca fue el problema, el fan-in solo se rompe del lado
# de las llegadas, no de las salidas).
_MERGE_DIRECT_NODES = ["extract_objeto_alcance", "extract_identificacion"]
for node in _MERGE_DIRECT_NODES:
    builder_phase1.add_edge("setup", node)

# garantias/plazos/requisitos/riesgos: las 4 fuentes que preview_criterios
# proyecta. Corren en paralelo entre si (todas cuelgan directo de "setup").
_PREVIEW_SOURCE_NODES = [
    "extract_garantias",
    "extract_plazos",
    "extract_requisitos",
    "extract_riesgos",
]
for node in _PREVIEW_SOURCE_NODES:
    builder_phase1.add_edge("setup", node)

# Fan-in real (lista en una sola llamada -> NamedBarrierValue): recien acá
# se agenda extract_preview_criterios, cuando las 4 terminaron, sin importar
# el orden en que vayan llegando.
builder_phase1.add_edge(_PREVIEW_SOURCE_NODES, "extract_preview_criterios")

# Fan-in real hacia "merge": objeto_alcance, identificacion y
# preview_criterios (que a su vez ya esperó a las 4 fuentes) tienen que
# terminar los tres, sin importar que preview_criterios llegue varios
# supersteps mas tarde que los otros dos.
builder_phase1.add_edge(
    [*_MERGE_DIRECT_NODES, "extract_preview_criterios"],
    "merge",
)

builder_phase1.add_edge("merge", "synthesize")
builder_phase1.add_edge("synthesize", END)

graph_phase1 = builder_phase1.compile()


# FASE 2: ya no corre garantias/plazos_clave/requisitos_admisibilidad/riesgos
# -- se promovieron a fase 1 (ver comentario arriba). Solo quedan las
# categorias que preview_criterios no necesita.
extractor_nodes_phase2 = [
    "extract_causales",
    "extract_anexos",
    "extract_criterios",
    "extract_eventos_temporales",
]


builder_phase2 = StateGraph(GraphState)
builder_phase2.add_node("setup", setup_node)
builder_phase2.add_node("extract_causales", extractor_causales)
builder_phase2.add_node("extract_anexos", extractor_anexos_obligatorios)
builder_phase2.add_node("extract_criterios", extractor_criterios_evaluacion)
builder_phase2.add_node("extract_eventos_temporales", extractor_eventos_temporales)
builder_phase2.add_node("merge", merge_node)
builder_phase2.add_node("synthesize", synthesize_node)
builder_phase2.set_entry_point("setup")

for node in extractor_nodes_phase2:
    builder_phase2.add_edge("setup", node)
for node in extractor_nodes_phase2:
    builder_phase2.add_edge(node, "merge")

builder_phase2.add_edge("merge", "synthesize")
builder_phase2.add_edge("synthesize", END)

graph_phase2 = builder_phase2.compile()
