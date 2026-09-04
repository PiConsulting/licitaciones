"""Entrypoint del extractor genérico usado por todos los extractores de categoría
(objeto_alcance, garantias, riesgos, etc.): retrieval -> LLM (map-reduce por
documento) -> normalización -> merge -> verificación de citas."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.engine.chunk_retrieval import _retrieve_with_category_priority
from analysis.extraction.engine.citation_grounding import _verify_citation_grounding
from analysis.extraction.engine.item_merging import (
    _group_chunks_by_document,
    _merge_items_by_document_section,
    _merge_split_fact_items,
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
    _item_has_substantive_content,
    _normalize_item,
    _normalize_mixed_not_found_items,
)
from analysis.extraction.engine.prompts import (
    _build_messages,
    _format_chunks,
    validate_category_prompt_mapping,
)
from analysis.extraction.glossary import build_keyword_query, build_prompt_glossary_block, build_semantic_expanded_query
from analysis.extraction.state import GraphState
from infra.config import get_settings

logger = structlog.get_logger(__name__)

_DOCUMENT_SECTION_MERGE_CATEGORIES = {"anexos_obligatorios"}


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

    try:
        settings = get_settings()
        keyword_query = build_keyword_query(result_key)

        # FASE 4 del plan RAG v2 (2026-08-24, sección 4.4): la query que se
        # vectoriza para el vector search se enriquece con la definición
        # semántica versionada de la categoría (misma fuente que 4.3), en vez
        # de usar solo la frase corta que arma cada extractor. La query de
        # keywords para BM25 (keyword_query, arriba) NO se toca -- sigue
        # siendo términos discriminantes del glosario. Apagado por default:
        # con el flag en false, retrieval_query == query (comportamiento
        # idéntico al actual).
        retrieval_query = query
        if settings.query_expansion_use_semantic_definition:
            retrieval_query = build_semantic_expanded_query(result_key, query)
            if retrieval_query != query:
                logger.debug(
                    "query_expansion_applied",
                    correlation_id=correlation_id,
                    category=result_key,
                )

        # FIX MEDIUM (#14): Top-K configurable por categoría desde glossary.json
        from analysis.extraction.glossary import get_category_penalty, get_category_top_k

        category_top_k = get_category_top_k(result_key, default=settings.extraction_top_k)

        # FIX (2026-09-03, Fase 1.4 del plan): category_penalty configurable
        # por categoría, mismo mecanismo que category_top_k arriba. Ver el
        # comentario de `get_category_penalty` en glossary.py para el porqué
        # (evidencia empírica de daño en preview_criterios, sin datos aún
        # para las otras categorías -- por eso es un override puntual y no
        # un cambio del default global en chunk_retrieval.py).
        category_penalty = get_category_penalty(result_key, default=0.30)

        chunks = _retrieve_with_category_priority(
            query=retrieval_query,
            analysis_id=analysis_id,
            top_k=category_top_k,
            keyword_query=keyword_query or None,
            category=result_key,
            correlation_id=correlation_id,
            category_penalty=category_penalty,
            global_candidates=state.get("global_candidates"),  # FASE 3 (4.2)
        )

        chunks = _drop_low_relevance_chunks(
            chunks,
            correlation_id=correlation_id,
            category=result_key,
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
            delta[f"{state_field}_token_usage"] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            return delta

        document_labels = state.get("document_labels")
        token_usage_key = f"{state_field}_token_usage"

        if is_object_result:
            # Resultado de un solo objeto agregado (ej. estimación de
            # presupuesto): no aplica "partir por documento y unir" -- se
            # mantiene el llamado único de siempre.
            messages = _build_messages(
                prompt_file_name=prompt_file_name,
                chunks_block=_format_chunks(chunks, document_labels),
                glossary_block=build_prompt_glossary_block(result_key),
                root_key=result_key,
            )
            llm_result, token_usage = _call_llm(messages=messages, correlation_id=correlation_id)
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
            # MAP-REDUCE POR DOCUMENTO (2026-08-21).
            #
            # Un solo llamado con todos los chunks recuperados mezclados sufre
            # "lost in the middle": con un contexto largo y muchos fragmentos
            # parecidos entre sí, el LLM no presta atención uniforme a todo el
            # texto -- lo que queda en el medio se pierde con más frecuencia,
            # y de forma no determinista entre corridas. Medido en este
            # proyecto: con retrieval idéntico verificado chunk por chunk,
            # sólo 1/8 categorías daba el mismo resultado en 5 corridas (ver
            # `docs/docu/PLAN-structured-outputs-EXT-01.md` y comentario en
            # `shared/adapters/azure_openai.py`). Reproducido también en el
            # experimento de `scripts/experimento_full_context.py` sobre
            # `anexos_obligatorios`: mismos 19 chunks, mismo prompt -- "ANEXO
            # V — Plan de Trabajo" aparecía en un modo y no en el otro.
            #
            # Partir por documento (cada pliego/anexo es una unidad lógica
            # natural, ya disponible en `document_id`) reduce cuánto texto
            # compite por atención en cada llamado individual, sin tocar el
            # vocabulario de la extracción -- sigue siendo texto libre, no
            # structured outputs con enums (descartado deliberadamente por la
            # variabilidad de terminología entre pliegos, ver
            # `PLAN-CORRECCION-RAG-VARIANZA.md` Epic 4).
            groups = _group_chunks_by_document(chunks)
            all_items: list[Any] = []
            accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            groups_failed = 0

            for document_id, group_chunks in groups.items():
                group_messages = _build_messages(
                    prompt_file_name=prompt_file_name,
                    chunks_block=_format_chunks(group_chunks, document_labels),
                    glossary_block=build_prompt_glossary_block(result_key),
                    root_key=result_key,
                )
                try:
                    group_result, group_usage = _call_llm(
                        messages=group_messages, correlation_id=correlation_id
                    )
                except Exception as exc:  # noqa: BLE001
                    groups_failed += 1
                    logger.warning(
                        "extractor_map_reduce_group_failed",
                        correlation_id=correlation_id,
                        category=result_key,
                        document_id=document_id,
                        chunks_en_grupo=len(group_chunks),
                        error=str(exc),
                    )
                    continue

                for key in accumulated_usage:
                    accumulated_usage[key] += int(group_usage.get(key, 0) or 0)

                if group_result.get("_diagnostic") == "sin_contenido_recuperado":
                    continue

                group_payload = group_result.get(result_key)
                # FIX (2026-08-24, hallazgo variabilidad anexos_obligatorios):
                # se etiqueta cada ítem crudo con el `document_id` del grupo
                # que lo generó. Los ítems sin ninguna cita verificable (ver
                # `_verify_citation_grounding`, status "partial" +
                # `_warning="cita_no_verificada"`) no tienen forma de saber
                # después de qué documento/sección salieron -- esta etiqueta
                # es la única pista que le queda a `_merge_items_by_document_section`
                # para poder fusionarlos igual, en vez de dejarlos como
                # "anexos" fantasma sueltos. No se persiste como fuente de
                # verdad de nada -- es sólo una pista interna para el merge.
                if isinstance(group_payload, list):
                    for item in group_payload:
                        if isinstance(item, dict):
                            item.setdefault("_source_document_id", document_id)
                            all_items.append(item)
                elif isinstance(group_payload, dict):
                    group_payload.setdefault("_source_document_id", document_id)
                    all_items.append(group_payload)

            # Si el LLM falló en TODOS los grupos, esto no es "no se encontró
            # nada" (not_found) -- es una falla real del sistema. Antes
            # `all_items` quedaba vacío y caía en el mismo camino que un
            # payload legítimamente vacío, perdiendo la señal de que hubo un
            # error real (ver auditoría: reportaba status="not_found" en vez
            # de "failed"). Se eleva para que lo capture el `except` de abajo,
            # que sí marca "failed" correctamente.
            if groups and groups_failed == len(groups):
                raise RuntimeError(
                    f"Todos los grupos ({groups_failed}/{len(groups)}) fallaron al "
                    f"llamar al LLM para la categoría {result_key}"
                )

            delta[token_usage_key] = accumulated_usage
            logger.info(
                "extractor_map_reduce_completed",
                correlation_id=correlation_id,
                category=result_key,
                documentos=len(groups),
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
            normalized_items = [_normalize_item(item) for item in payload if isinstance(item, dict)]
            normalized_items = _normalize_mixed_not_found_items(
                normalized_items, category=result_key
            )
            # Red de seguridad genérica: si el LLM partió un solo hecho en dos
            # ítems (ver docstring de `_merge_split_fact_items`), se fusionan
            # ANTES de la verificación de citas para que ésta trabaje sobre el
            # ítem ya consolidado. Aplica a cualquier categoría y cualquier
            # pliego -- no depende de redacción de un pliego en particular.
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

            # Detectar contaminación cruzada en objeto
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

            # Detectar contaminación cruzada en lista
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

    return delta
