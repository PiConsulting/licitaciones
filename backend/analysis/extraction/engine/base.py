"""Entrypoint del extractor genérico usado por todos los extractores de categoría
(objeto_alcance, garantias, riesgos, etc.): retrieval -> LLM (map-reduce por
documento) -> normalización -> merge -> verificación de citas."""
from __future__ import annotations

import time
from typing import Any

import structlog

from analysis.extraction.engine.chunk_retrieval import _retrieve_with_category_priority
from analysis.extraction.engine.citation_grounding import _verify_citation_grounding
from analysis.extraction.engine.item_merging import (
    _group_chunks_by_document,
    _merge_items_by_document_section,
    _merge_split_fact_items,
    _split_oversized_groups,
)
from analysis.extraction.engine.llm_client import (
    _call_llm,
    _drop_low_relevance_chunks,
    _truncate_to_token_budget,
)
from analysis.extraction.engine.normalization import (
    _aggregate_status,
    _augment_identificacion_payload,
    _default_not_found_item,
    _fill_missing_valor_for_garantias,
    _item_has_substantive_content,
    _normalize_item,
    _normalize_mixed_not_found_items,
)
from analysis.extraction.engine.prompts import (
    _build_messages,
    _format_chunks,
    validate_category_prompt_mapping,
)
from analysis.extraction.glossary import (
    build_keyword_query,
    build_prompt_glossary_block,
    build_semantic_expanded_query,
)
from analysis.extraction.state import GraphState
from infra.config import get_settings

logger = structlog.get_logger(__name__)

_DOCUMENT_SECTION_MERGE_CATEGORIES = {"anexos_obligatorios"}

# Fallback si `settings` no trae `extraction_group_max_chunks` (p.ej. un fake de test).
_DEFAULT_EXTRACTION_GROUP_MAX_CHUNKS = 15


def run_extractor(
    *,
    state: GraphState,
    result_key: str,
    state_field: str,
    status_field: str,
    prompt_file_name: str,
    query: str,
    is_object_result: bool = False,
) -> GraphState:
    correlation_id = state["correlation_id"]
    analysis_id = state["analysis_id"]
    validate_category_prompt_mapping(result_key, prompt_file_name)
    logger.info(
        "extractor_started",
        correlation_id=correlation_id,
        analysis_id=analysis_id,
        category=result_key,
    )

    delta: GraphState = {}

    # Instrumentación: se cuelga del dict de token_usage que ya viaja por el pipeline, sin plumbing nuevo.
    _started = time.monotonic()
    token_usage_key = f"{state_field}_token_usage"

    def _stamp_metrics(current: GraphState) -> GraphState:
        usage = current.get(token_usage_key)
        if not isinstance(usage, dict):
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            current[token_usage_key] = usage
        usage.setdefault("llm_calls", 0)
        usage["wall_time_seconds"] = round(time.monotonic() - _started, 2)
        return current

    try:
        settings = get_settings()
        keyword_query = build_keyword_query(result_key)

        # La query vectorial se enriquece con la definición semántica de la categoría; keyword_query (BM25) no se toca. Apagado por default.
        from analysis.extraction.glossary import get_category_query_expansion

        retrieval_query = query
        if settings.query_expansion_use_semantic_definition or get_category_query_expansion(
            result_key
        ):
            retrieval_query = build_semantic_expanded_query(result_key, query)
            if retrieval_query != query:
                logger.debug(
                    "query_expansion_applied",
                    correlation_id=correlation_id,
                    category=result_key,
                )

        # FIX MEDIUM (#14): Top-K configurable por categoría desde glossary.json
        from analysis.extraction.glossary import (
            get_category_penalty,
            get_category_relevance_min_chunks,
            get_category_relevance_min_ratio,
            get_category_self_consistency_runs,
            get_category_top_k,
        )

        category_top_k = get_category_top_k(result_key, default=settings.extraction_top_k)

        # category_penalty configurable por categoría: evidencia empírica de daño solo en preview_criterios (ver glossary.py::get_category_penalty), por eso es override puntual y no default global.
        category_penalty = get_category_penalty(result_key, default=0.30)
        relevance_min_chunks = get_category_relevance_min_chunks(result_key, default=10)
        relevance_min_ratio = get_category_relevance_min_ratio(result_key, default=0.4)

        chunks = _retrieve_with_category_priority(
            query=retrieval_query,
            analysis_id=analysis_id,
            top_k=category_top_k,
            keyword_query=keyword_query or None,
            category=result_key,
            correlation_id=correlation_id,
            category_penalty=category_penalty,
            global_candidates=state.get("global_candidates"),
        )

        chunks = _drop_low_relevance_chunks(
            chunks,
            correlation_id=correlation_id,
            category=result_key,
            min_chunks=relevance_min_chunks,
            min_ratio=relevance_min_ratio,
        )

        chunks = _truncate_to_token_budget(
            chunks,
            settings.extraction_max_context_tokens,
            correlation_id=correlation_id,
            category=result_key,
        )

        category_distribution: dict[str, int] = {}
        for chunk in chunks:
            primary = chunk.get("primary_category") or "sin_categoria"
            category_distribution[primary] = category_distribution.get(primary, 0) + 1

        # Métrica de pureza: % de chunks que pertenecen a la categoría target
        target_chunks = sum(
            1
            for chunk in chunks
            if chunk.get("primary_category") == result_key
            or result_key in chunk.get("secondary_categories", [])
        )
        purity_rate = target_chunks / len(chunks) if chunks else 0.0

        logger.info(
            "retrieval_metrics",
            correlation_id=correlation_id,
            category=result_key,
            retrieved_chunks=len(chunks),
            category_distribution=category_distribution,
            target_chunks=target_chunks,
            purity_rate=round(purity_rate, 3),
        )

        if not chunks:
            logger.error(
                "extractor_no_chunks_retrieved",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                category=result_key,
                query=query[:160],
            )
            delta[state_field] = _default_not_found_item() if is_object_result else []
            delta[status_field] = "not_found"
            delta[token_usage_key] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            return _stamp_metrics(delta)

        document_labels = state.get("document_labels")

        if is_object_result:
            # Resultado de un solo objeto agregado: no aplica map-reduce por documento.
            messages = _build_messages(
                prompt_file_name=prompt_file_name,
                chunks_block=_format_chunks(chunks, document_labels),
                glossary_block=build_prompt_glossary_block(result_key),
                root_key=result_key,
            )
            llm_result, token_usage = _call_llm(messages=messages, correlation_id=correlation_id)
            token_usage["llm_calls"] = 1
            delta[token_usage_key] = token_usage
            if llm_result.get("_diagnostic") == "sin_contenido_recuperado":
                logger.error(
                    "extractor_empty_content_reported_by_llm",
                    correlation_id=correlation_id,
                    analysis_id=analysis_id,
                    category=result_key,
                )
            payload = llm_result.get(result_key)
        else:
            # Map-reduce por documento evita "lost in the middle" (medido: solo 1/8 categorías daba el mismo resultado en 5 corridas con un solo llamado).
            groups = _group_chunks_by_document(chunks)
            group_max_chunks = int(
                getattr(settings, "extraction_group_max_chunks", None)
                or _DEFAULT_EXTRACTION_GROUP_MAX_CHUNKS
            )
            all_items: list[Any] = []
            accumulated_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "llm_calls": 0,
            }
            groups_failed = 0

            def _run_group(group_chunks: list[dict[str, Any]]):
                group_messages = _build_messages(
                    prompt_file_name=prompt_file_name,
                    chunks_block=_format_chunks(group_chunks, document_labels),
                    glossary_block=build_prompt_glossary_block(result_key),
                    root_key=result_key,
                )
                return _call_llm(messages=group_messages, correlation_id=correlation_id)

            # Se indexa por POSICIÓN, no document_id: un documento partido en varios lotes repite document_id, y una clave por id pisaría el lote anterior.
            groups_items = _split_oversized_groups(groups, max_chunks_per_call=group_max_chunks)

            # Self-consistency: repite cada grupo N veces como "un grupo más"; el dedup existente de merge_node fusiona o separa igual que entre documentos distintos. Opt-in, default 1 = sin cambios.
            self_consistency_runs = get_category_self_consistency_runs(result_key)
            if self_consistency_runs > 1:
                groups_items = [item for item in groups_items for _ in range(self_consistency_runs)]

            # Llamadas en paralelo, ensamblado luego en orden original (mismo resultado que secuencial).
            # Nunca se fusionan chunks de documentos distintos en una llamada: el LLM podría "reconciliar" una contradicción principal-vs-anexo y perderse el aviso de conflicto (merge_node).
            mapreduce_workers = min(
                len(groups_items),
                max(1, int(settings.extraction_mapreduce_concurrency or 1)),
            )
            results_by_index: dict[int, Any] = {}
            if mapreduce_workers <= 1:
                for index, (document_id, group_chunks) in enumerate(groups_items):
                    try:
                        results_by_index[index] = _run_group(group_chunks)
                    except Exception as exc:  # noqa: BLE001
                        results_by_index[index] = exc
            else:
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(
                    max_workers=mapreduce_workers,
                    thread_name_prefix=f"mapreduce-{result_key}",
                ) as pool:
                    future_to_index = {
                        pool.submit(_run_group, group_chunks): index
                        for index, (document_id, group_chunks) in enumerate(groups_items)
                    }
                    for future, index in future_to_index.items():
                        try:
                            results_by_index[index] = future.result()
                        except Exception as exc:  # noqa: BLE001
                            results_by_index[index] = exc

            # Ensamblado determinístico: orden original de los grupos, no orden de llegada.
            for index, (document_id, group_chunks) in enumerate(groups_items):
                outcome = results_by_index.get(index)
                if isinstance(outcome, BaseException):
                    groups_failed += 1
                    logger.warning(
                        "extractor_map_reduce_group_failed",
                        correlation_id=correlation_id,
                        category=result_key,
                        document_id=document_id,
                        chunks_en_grupo=len(group_chunks),
                        error=str(outcome),
                    )
                    continue

                group_result, group_usage = outcome

                for key in accumulated_usage:
                    accumulated_usage[key] += int(group_usage.get(key, 0) or 0)
                # Cuenta para costo/latencia aunque el resultado sea "sin_contenido".
                accumulated_usage["llm_calls"] += 1

                if group_result.get("_diagnostic") == "sin_contenido_recuperado":
                    continue

                group_payload = group_result.get(result_key)
                # Etiqueta cada ítem con el document_id del grupo: única pista para fusionar ítems sin cita verificable en `_merge_items_by_document_section` (no se persiste como fuente de verdad).
                if isinstance(group_payload, list):
                    for item in group_payload:
                        if isinstance(item, dict):
                            item.setdefault("_source_document_id", document_id)
                            all_items.append(item)
                elif isinstance(group_payload, dict):
                    group_payload.setdefault("_source_document_id", document_id)
                    all_items.append(group_payload)

            # Falla real del sistema (no "not_found") si TODOS los grupos fallaron; se eleva para que el except de abajo marque "failed". Compara contra groups_items (lotes reales), no groups (documentos).
            if groups_items and groups_failed == len(groups_items):
                raise RuntimeError(
                    f"Todos los grupos ({groups_failed}/{len(groups_items)}) fallaron al "
                    f"llamar al LLM para la categoría {result_key}"
                )

            delta[token_usage_key] = accumulated_usage
            logger.info(
                "extractor_map_reduce_completed",
                correlation_id=correlation_id,
                category=result_key,
                documentos=len(groups),
                llamadas_llm=len(groups_items),
                documentos_fallidos=groups_failed,
                items_crudos=len(all_items),
            )
            payload = all_items

        if is_object_result:
            if not isinstance(payload, dict):
                payload = _default_not_found_item()
            normalized_object = _normalize_item(
                payload, fallback={"tipo": "estimacion_presupuesto"}
            )
            if normalized_object.get(
                "extraction_status"
            ) == "not_found" and _item_has_substantive_content(normalized_object):
                normalized_object["extraction_status"] = "partial"
            delta[state_field] = normalized_object
        else:
            if not isinstance(payload, list):
                logger.warning(
                    "payload_no_es_lista", category=result_key, tipo=type(payload).__name__
                )
                payload = []
            if result_key == "identificacion_procedimiento":
                payload = _augment_identificacion_payload(payload, chunks)
            if result_key == "garantias":
                payload = _fill_missing_valor_for_garantias(payload)
            normalized_items = [_normalize_item(item) for item in payload if isinstance(item, dict)]
            normalized_items = _normalize_mixed_not_found_items(
                normalized_items, category=result_key
            )
            # Fusiona hechos partidos en dos ítems ANTES de verificar citas, para que trabaje sobre el ítem ya consolidado.
            normalized_items = _merge_split_fact_items(
                normalized_items, chunks, category=result_key, correlation_id=correlation_id
            )
            if result_key in _DOCUMENT_SECTION_MERGE_CATEGORIES:
                normalized_items = _merge_items_by_document_section(
                    normalized_items, chunks, category=result_key, correlation_id=correlation_id
                )
            delta[state_field] = normalized_items

        if is_object_result:
            _verify_citation_grounding(
                [delta[state_field]], chunks, category=result_key, correlation_id=correlation_id
            )

            from analysis.extraction.engine.validators import detect_cross_contamination

            contaminated = detect_cross_contamination([delta[state_field]], category=result_key)
            if contaminated:
                logger.warning(
                    "cross_contamination_detected",
                    correlation_id=correlation_id,
                    category=result_key,
                    contaminated_count=len(contaminated),
                )

            delta[status_field] = str(delta[state_field].get("extraction_status", "not_found"))
        else:
            _verify_citation_grounding(
                delta[state_field], chunks, category=result_key, correlation_id=correlation_id
            )

            from analysis.extraction.engine.validators import detect_cross_contamination

            contaminated = detect_cross_contamination(delta[state_field], category=result_key)
            if contaminated:
                logger.warning(
                    "cross_contamination_detected",
                    correlation_id=correlation_id,
                    category=result_key,
                    contaminated_count=len(contaminated),
                )

            delta[status_field] = _aggregate_status(delta[state_field])
        logger.info(
            "extractor_completed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            category=result_key,
            status=delta[status_field],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "extractor_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            category=result_key,
            error=str(exc),
        )
        delta[state_field] = _default_not_found_item() if is_object_result else []
        delta[status_field] = "failed"

    return _stamp_metrics(delta)
