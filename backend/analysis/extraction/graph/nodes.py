"""Entrypoint del grafo de extraccion (LangGraph): setup (carga documentos + candidate pool) -> extractores en paralelo -> merge (dedupe + confianza) -> synthesize (narrativa)."""
from __future__ import annotations

from collections import defaultdict

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
    extractor_plazos_relativos,
    extractor_requisitos_admisibilidad,
    extractor_riesgos,
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
from analysis.extraction.graph.confidence import _category_confidence, _normalize_confidence, _penalize_unverifiable
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

_GLOBAL_CANDIDATE_POOL_QUERY = (
    "Información relevante de un pliego de licitación pública: objeto y "
    "alcance de la contratación, requisitos de admisibilidad, plazos y "
    "fechas clave, garantías financieras, causales de rechazo de la oferta, "
    "anexos y formularios obligatorios, criterios de evaluación y "
    "adjudicación, identificación del procedimiento y del organismo "
    "convocante, y riesgos comerciales para el oferente."
)


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
        from infra.ports.azure_search import search_hybrid

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
    document_mapping = _build_document_mapping(state["analysis_id"], state.get("db_session"))
    document_labels = _build_document_labels(state["analysis_id"], state.get("db_session"))
    global_candidates = _build_shared_candidate_pool(state["analysis_id"], state["correlation_id"])

    state.update(
        {
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
    riesgos = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("riesgos", [])
    ]
    
    # Timeline: eventos temporales y plazos relativos
    eventos_temporales = state.get("eventos_temporales", [])
    plazos_relativos = state.get("plazos_relativos", [])
    
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
        "datos_procedimiento": identificacion,
        "datos_procedimiento_extraction_status": identificacion_status,
        "datos_procedimiento_confidence": _category_confidence(identificacion),
        "riesgos": riesgos,
        "riesgos_extraction_status": riesgos_status,
        "riesgos_confidence": _category_confidence(riesgos),
        "eventos_temporales": eventos_temporales,
        "eventos_temporales_extraction_status": state.get("eventos_temporales_status", "unknown"),
        "plazos_relativos": plazos_relativos,
        "plazos_relativos_extraction_status": state.get("plazos_relativos_status", "unknown"),
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
        "eventos_temporales": state.get("eventos_temporales_token_usage", {}),
        "plazos_relativos": state.get("plazos_relativos_token_usage", {}),
    }

    conflicts: list[dict] = []

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
                conflicts.append(
                    {
                        "category": "plazos",
                        "tipo": str(items[0].get("referencia") or "dato"),
                        "values": items,
                        "reason": "Fechas diferentes en distintos documentos",
                    }
                )

    garantias_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for garantia in garantias:
        garantias_by_tipo[str(garantia.get("tipo", ""))].append(garantia)

    for tipo, items in garantias_by_tipo.items():
        if tipo and len(items) > 1:
            montos = {(item.get("monto_porcentaje"), item.get("monto_valor")) for item in items}
            if len(montos) > 1:
                conflicts.append(
                    {
                        "category": "garantias",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Montos diferentes en distintos documentos",
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
        from infra.ports.azure_search import fetch_all_analysis_chunks

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

    synthesized = 0
    for category_key in NARRATIVE_CATEGORIES:
        items = extracted_data.get(category_key, [])
        if not isinstance(items, list):
            continue
        result = run_synthesis(
            category_key=category_key,
            items=items,
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
            conflicts=state.get("conflicts") or [],
        )
        if result is None:
            continue
        narrative, token_usage = result
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
builder.add_node("extract_riesgos", extractor_riesgos)
builder.add_node("extract_eventos_temporales", extractor_eventos_temporales)
builder.add_node("extract_plazos_relativos", extractor_plazos_relativos)
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
    "extract_plazos_relativos",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", "synthesize")
builder.add_edge("synthesize", END)

graph = builder.compile()
