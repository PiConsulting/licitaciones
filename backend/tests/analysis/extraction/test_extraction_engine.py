# Tests para analysis/extraction/engine/base.py — US-2.2 y US-2.3
# (auditoría RAG 2026-08-12, hallazgos M-2 y M-3)

from __future__ import annotations

import time

import pytest
import structlog

from analysis.extraction.engine import base as extractor_base
from analysis.extraction.engine import chunk_retrieval, llm_client, normalization


def _chunk(
    *,
    chunk_index: int,
    content: str = "contenido de prueba",
    primary_category: str | None = None,
    secondary_categories: list[str] | None = None,
    search_score: float | None = None,
) -> dict:
    chunk = {
        "document_id": "doc-1",
        "chunk_index": chunk_index,
        "content": content,
        "primary_category": primary_category,
        "secondary_categories": secondary_categories or [],
    }
    if search_score is not None:
        chunk["search_score"] = search_score
    return chunk


def _rerank_settings(**overrides):
    """Settings falso COMPLETO para los tests del path de reranking. Reranking
    ON (el default de producción es False -- ver config.py -- pero acá se
    ejercita el mecanismo), pool compartido y capas experimentales OFF."""
    from types import SimpleNamespace

    base = {
        "rag_reranking_enabled": True,
        "rag_reranking_timeout_seconds": 15.0,
        "use_shared_candidate_pool": False,
        "shared_candidate_pool_purity_threshold": 0.7,
        "shared_candidate_pool_augment_on_roundtrip": False,
        "rag_neighbor_expansion_enabled": False,
        "rag_neighbor_expansion_window": 1,
        "rag_llm_judge_enabled": False,
        "rag_llm_judge_window": 25,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestCategoryBoostUsesRealScore:
    """US-2.2 (hallazgo M-2): el boost por categoría debe aplicarse sobre el
    search_score real de Azure, no sobre un rank sintético 1/(rank+1)."""

    def test_real_score_magnitude_is_respected_over_rank(self, monkeypatch):
        """Dos chunks con scores de Azure muy distintos no deben quedar
        artificialmente empatados tras el boost, aunque estén en ranks
        consecutivos."""
        # Rank 0: score de Azure altísimo, sin la categoría target.
        # Rank 1: score de Azure ínfimo, con la categoría target (boost +20%).
        # Con 1/(rank+1) el boost casi empataba a ambos (1.0 vs 0.5*1.2=0.6);
        # con el score real, el chunk de rank 0 tiene que seguir ganando
        # ampliamente porque 50.0 >> 0.01 * 1.2.
        candidates = [
            _chunk(chunk_index=0, primary_category="otra_categoria", search_score=50.0),
            _chunk(chunk_index=1, primary_category="garantias", search_score=0.01),
        ]

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(candidates)

        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)

        result = chunk_retrieval._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-1",
        )

        assert [c["chunk_index"] for c in result] == [0, 1], (
            "el chunk con score de Azure real mucho mayor tiene que seguir "
            "primero pese al boost del otro por categoría"
        )

    def test_category_boost_can_still_flip_order_on_comparable_scores(self, monkeypatch):
        """Cuando los scores reales son comparables, el boost por categoría sí
        debe poder cambiar el orden (es la señal para la que existe)."""
        candidates = [
            _chunk(chunk_index=0, primary_category="otra_categoria", search_score=1.0),
            _chunk(chunk_index=1, primary_category="garantias", search_score=0.95),
        ]

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(candidates)

        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)

        result = chunk_retrieval._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-1",
            category_boost=0.20,
        )

        # 0.95 * 1.20 = 1.14 > 1.0
        assert [c["chunk_index"] for c in result] == [1, 0]

    def test_falls_back_to_rank_when_search_score_missing(self, monkeypatch):
        """Retrocompatibilidad: si un chunk no trae `search_score` (fuentes
        legacy o mocks de test que no pasan por _search_azure), no debe
        romper -- cae al rank sintético anterior."""
        candidates = [
            _chunk(chunk_index=0, primary_category=None),  # sin search_score
            _chunk(chunk_index=1, primary_category="garantias"),  # sin search_score
        ]

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(candidates)

        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)

        result = chunk_retrieval._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-1",
        )

        # No debe lanzar excepción y debe devolver ambos chunks.
        assert {c["chunk_index"] for c in result} == {0, 1}

    def test_reranking_is_applied_after_category_scoring(self, monkeypatch):
        """El orden final debe poder cambiar por reranking semántico.
        Sin este paso conectado, el resultado queda congelado en score híbrido."""
        candidates = [
            _chunk(chunk_index=0, primary_category="garantias", search_score=1.0),
            _chunk(chunk_index=1, primary_category="garantias", search_score=0.9),
            _chunk(chunk_index=2, primary_category="garantias", search_score=0.8),
        ]

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(candidates)

        def fake_rerank(query: str, chunks: list[dict], *, top_k: int, **_kwargs):
            assert query == "garantías exigidas"
            assert top_k == 2
            return [chunks[2], chunks[1]]

        monkeypatch.setattr(chunk_retrieval, "get_settings", _rerank_settings)
        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)
        monkeypatch.setattr(chunk_retrieval, "rerank_chunks", fake_rerank)

        result = chunk_retrieval._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-1",
        )

        assert [c["chunk_index"] for c in result] == [2, 1]


class TestRerankingGuardrailByPoolSize:
    def test_reranking_runs_when_pool_within_threshold(self, monkeypatch):
        candidates = [
            _chunk(chunk_index=0, primary_category="garantias", search_score=1.0),
            _chunk(chunk_index=1, primary_category="garantias", search_score=0.9),
            _chunk(chunk_index=2, primary_category="garantias", search_score=0.8),
        ]

        called: dict[str, int] = {"count": 0}

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(candidates)

        def fake_rerank(query: str, chunks: list[dict], *, top_k: int, **_kwargs):
            called["count"] += 1
            return chunks[:top_k]

        monkeypatch.setattr(chunk_retrieval, "get_settings", _rerank_settings)
        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)
        monkeypatch.setattr(chunk_retrieval, "rerank_chunks", fake_rerank)

        result = chunk_retrieval._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-guardrail-low",
        )

        assert called["count"] == 1
        assert len(result) == 2

    def test_reranking_is_skipped_when_merged_pool_exceeds_threshold(self, monkeypatch):
        specific_candidates = [
            {
                **_chunk(
                    chunk_index=i,
                    primary_category="garantias",
                    search_score=1.0 - (i * 0.01),
                ),
                "id": f"specific-{i}",
            }
            for i in range(6)
        ]
        shared_candidates = [
            {
                **_chunk(
                    chunk_index=100 + i,
                    primary_category="otra_categoria",
                    search_score=0.7 - (i * 0.01),
                ),
                "id": f"shared-{i}",
                "document_id": f"doc-shared-{i}",
            }
            for i in range(10)
        ]

        def fake_search(*, query, analysis_id, top_k, keyword_query, category=None):
            return list(specific_candidates)

        def should_not_rerank(*_args, **_kwargs):
            raise AssertionError("rerank_chunks no debe invocarse cuando se activa el guardrail")

        # timeout chico -> rerank_skip_threshold chico (= max(top_k, timeout/costo_par))
        # -> el guardrail salta cuando `rerank_window` (top_k*2) lo supera.
        monkeypatch.setattr(
            chunk_retrieval,
            "get_settings",
            lambda: _rerank_settings(
                use_shared_candidate_pool=True,
                shared_candidate_pool_purity_threshold=1.0,
                rag_reranking_timeout_seconds=0.27,
            ),
        )
        monkeypatch.setattr(chunk_retrieval, "search_hybrid", fake_search)
        monkeypatch.setattr(chunk_retrieval, "rerank_chunks", should_not_rerank)

        with structlog.testing.capture_logs() as captured:
            result = chunk_retrieval._retrieve_with_category_priority(
                query="garantías exigidas",
                analysis_id="analysis-1",
                top_k=2,
                keyword_query="garantia caucion",
                category="garantias",
                correlation_id="corr-guardrail-high",
                global_candidates=shared_candidates,
            )

        assert len(result) == 2
        events = [
            entry for entry in captured if entry.get("event") == "reranking_skipped_window_too_large"
        ]
        assert len(events) == 1
        assert events[0]["rerank_window"] > events[0]["threshold"]


class TestTokenBudgetUsesRealTokenizer:
    """US-2.3 (hallazgo M-3): el presupuesto de contexto se mide con el
    tokenizer real del modelo, no con conteo de palabras."""

    def test_uses_encoder_when_available(self, monkeypatch):
        """Con un encoder disponible, el costo de cada chunk se calcula con
        `encoder.encode()`, no con `len(content.split())`."""

        class FakeEncoder:
            def encode(self, text: str) -> list[int]:
                # Tokenizer determinístico y distinto del conteo por palabras,
                # para poder distinguir en el test cuál ruta se usó: 3 tokens
                # por caracter no-espacio, por ejemplo.
                return [0] * (len(text.replace(" ", "")) * 3)

        monkeypatch.setattr(llm_client, "_get_token_encoder", lambda: FakeEncoder())

        # Chunk 1: "ab" -> 1 palabra, pero 6 "tokens" con el fake encoder.
        # Chunk 2: "cd" -> ídem.
        # Presupuesto=6: por palabras entrarían los dos (1+1=2 <= 6); por
        # tokens reales el primero solo ya usa el presupuesto entero (6) y
        # el segundo debe quedar afuera.
        chunks = [{"content": "ab"}, {"content": "cd"}]
        kept = llm_client._truncate_to_token_budget(chunks, budget=6)
        assert kept == [{"content": "ab"}], (
            "con presupuesto=6 y costo real de 6 tokens para el primer chunk, "
            "el segundo no debería entrar -- si entra, todavía se está "
            "contando por palabras en vez de por tokens"
        )

    def test_logs_warning_with_drop_count_when_budget_exceeded(self, monkeypatch, caplog):
        """FIX (2026-08-13): el descarte por presupuesto de tokens era
        completamente silencioso -- un pliego con muchos hechos relevantes
        para una categoría (plazos, garantías) podía perder chunks recuperados
        como relevantes sin ningún rastro. Ahora debe quedar un warning con
        cuántos chunks se descartaron, para cualquier categoría/pliego."""
        monkeypatch.setattr(
            llm_client, "_get_token_encoder", lambda: None
        )  # conteo por palabras, determinístico

        chunks = [
            {"content": "una dos tres"},  # 3 palabras, entra
            {"content": "cuatro"},  # entraría solo (1 palabra) pero ya no hay presupuesto
            {"content": "cinco seis"},  # tampoco entra
        ]
        import structlog

        with structlog.testing.capture_logs() as captured:
            kept = llm_client._truncate_to_token_budget(
                chunks, budget=3, correlation_id="corr-test", category="plazos_clave"
            )

        assert len(kept) == 1
        warnings = [
            e for e in captured if e.get("event") == "extraction_chunks_dropped_token_budget"
        ]
        assert len(warnings) == 1, "debe loguear un warning con el descarte"
        assert warnings[0]["chunks_dropped"] == 2
        assert warnings[0]["chunks_kept"] == 1
        assert warnings[0]["category"] == "plazos_clave"
        assert warnings[0]["correlation_id"] == "corr-test"

    def test_no_warning_logged_when_all_chunks_fit(self, monkeypatch):
        """Caso feliz: si todos los chunks entran en el presupuesto, no debe
        loguearse ningún warning de descarte."""
        monkeypatch.setattr(llm_client, "_get_token_encoder", lambda: None)

        import structlog

        with structlog.testing.capture_logs() as captured:
            kept = llm_client._truncate_to_token_budget(
                [{"content": "una dos"}],
                budget=10,
                correlation_id="corr-test",
                category="garantias",
            )

        assert kept == [{"content": "una dos"}]
        assert not any(e.get("event") == "extraction_chunks_dropped_token_budget" for e in captured)

    def test_falls_back_to_word_count_when_encoder_unavailable(self, monkeypatch):
        """Si el encoder no está disponible (p.ej. sin conectividad la
        primera vez que se descarga el archivo de encoding), no debe
        crashear la extracción -- cae al conteo por palabras de antes."""
        monkeypatch.setattr(llm_client, "_get_token_encoder", lambda: None)

        chunks = [{"content": "una dos tres"}]  # 3 palabras
        kept = llm_client._truncate_to_token_budget(chunks, budget=3)
        assert kept == chunks

        kept_over_budget = llm_client._truncate_to_token_budget(
            [{"content": "una dos tres"}, {"content": "cuatro"}], budget=3
        )
        assert len(kept_over_budget) == 1

    def test_count_tokens_never_raises_if_encoder_encode_fails(self, monkeypatch):
        """Si `encoder.encode()` explota en runtime, `_count_tokens` cae al
        conteo por palabras en vez de propagar la excepción."""

        class BrokenEncoder:
            def encode(self, text: str) -> list[int]:
                raise RuntimeError("boom")

        monkeypatch.setattr(llm_client, "_get_token_encoder", lambda: BrokenEncoder())

        assert llm_client._count_tokens("una dos tres") == 3

    def test_real_tokenizer_differs_from_word_count_on_spanish_legal_text(self):
        """Comparación real (no mockeada) entre el conteo viejo por palabras y
        el nuevo por tokens, sobre texto en español con acentos y términos
        legales -- el criterio de aceptación explícito de US-2.3.

        Requiere que tiktoken pueda cargar su archivo de encoding (primera
        vez, necesita red). Si no hay conectividad en el entorno donde corre
        el test, se skippea en vez de fallar: no es un problema del código,
        es del entorno de test."""
        text = (
            "El oferente deberá constituir una garantía de mantenimiento de "
            "oferta equivalente al cinco por ciento (5%) del presupuesto "
            "oficial, mediante póliza de caución, aval bancario o pagaré a "
            "la vista, bajo pena de inadmisibilidad de la propuesta."
        )
        llm_client._get_token_encoder.cache_clear()
        try:
            token_count = llm_client._count_tokens(text)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"tiktoken no pudo inicializar el encoding en este entorno: {exc}")
        finally:
            llm_client._get_token_encoder.cache_clear()

        word_count = len(text.split())

        if token_count == word_count:
            pytest.skip(
                "el encoder real no está disponible en este entorno (cayó al "
                "fallback por palabras) -- no hay nada real que comparar aquí"
            )

        assert token_count != word_count, (
            "el conteo de tokens real debería diferir del conteo por "
            "palabras en español con acentos/términos legales"
        )


def _identificacion_chunk(content: str, *, page_number: int = 1) -> dict:
    return {
        "document_id": "doc-1",
        "page_number": page_number,
        "content": content,
    }


class TestAugmentIdentificacionPayloadRejectsGarbage:
    """FIX (2026-08-13): `_augment_identificacion_payload` es un backstop por
    regex (no LLM) que corre DESPUÉS de la extracción para completar datos de
    identificación que el LLM pudo pasar por alto. Bug real detectado en
    producción: sobre un pliego real (Municipalidad de Rosario) donde el
    texto es "...llama a Licitación Privada para la 'Adquisición de
    Servidores...'" -- SIN ningún número de procedimiento en ningún lugar del
    pliego -- el regex igual generaba `numero_procedimiento` con
    valor "Licitación Privada N° para" (capturando la palabra "para" como si
    fuera el número). El mismo pliego tiene "PRESUPUESTO OFICIAL: $ X
    APERTURA: LUGAR: ..." (con "$ X" como placeholder literal, sin monto
    real) y el regex de presupuesto se comía todo el texto siguiente como si
    fuera el valor. Este bug es independiente del LLM: el prompt puede decir
    lo que quiera, este código igual lo pisaba después."""

    def test_no_inventa_numero_de_procedimiento_sobre_texto_sin_numero(self):
        chunks = [
            _identificacion_chunk(
                "La Municipalidad de Rosario llama a Licitación Privada para la "
                "Adquisición de Servidores de aplicaciones y base de datos, en un "
                "todo de acuerdo a lo que se establece en el presente Pliego.",
                page_number=2,
            )
        ]
        # El LLM ya extrajo organismo/tipo/denominación -- pero NO numero_procedimiento
        # (correctamente, porque el pliego no tiene uno).
        payload = [
            {"tipo": "organismo_convocante", "valor": "La Municipalidad de Rosario"},
            {"tipo": "tipo_procedimiento", "valor": "Licitación Privada"},
        ]

        result = normalization._augment_identificacion_payload(payload, chunks)

        tipos = {item["tipo"] for item in result}
        assert "numero_procedimiento" not in tipos, (
            f"no debería inventar numero_procedimiento sobre texto sin número real; "
            f"items generados: {result}"
        )

    def test_si_reconoce_un_numero_real_de_procedimiento(self):
        chunks = [
            _identificacion_chunk(
                "MUNICIPALIDAD DE VILLA NUEVA. Licitación Pública N° 08/2026 para la "
                "contratación del servicio de limpieza integral.",
                page_number=1,
            )
        ]
        payload: list[dict] = []

        result = normalization._augment_identificacion_payload(payload, chunks)

        numeros = [item for item in result if item["tipo"] == "numero_procedimiento"]
        assert len(numeros) == 1, f"debería reconocer un número real; items: {result}"
        assert "08/2026" in numeros[0]["valor"]

    def test_no_inventa_presupuesto_sobre_placeholder_sin_monto(self):
        chunks = [
            _identificacion_chunk(
                "PRESUPUESTO OFICIAL: $ X APERTURA: LUGAR: Dirección General de "
                "Compras y Suministros, Santa Fe 660, Rosario.",
                page_number=1,
            )
        ]
        payload: list[dict] = []

        result = normalization._augment_identificacion_payload(payload, chunks)

        tipos = {item["tipo"] for item in result}
        assert "presupuesto_oficial" not in tipos, (
            f"no debería inventar un presupuesto sobre un placeholder ('$ X') sin monto "
            f"real; items generados: {result}"
        )

    def test_si_reconoce_un_presupuesto_real_sin_comerse_el_campo_siguiente(self):
        chunks = [
            _identificacion_chunk(
                "PRESUPUESTO OFICIAL: $ 3.850.000 EXPEDIENTE: 4521-2026",
                page_number=1,
            )
        ]
        payload: list[dict] = []

        result = normalization._augment_identificacion_payload(payload, chunks)

        presupuestos = [item for item in result if item["tipo"] == "presupuesto_oficial"]
        assert len(presupuestos) == 1, f"debería reconocer un presupuesto real; items: {result}"
        assert "3.850.000" in presupuestos[0]["valor"]
        assert "EXPEDIENTE" not in presupuestos[0]["valor"].upper(), (
            "no debería comerse el campo siguiente (Expediente) dentro del valor del presupuesto"
        )


class TestMapReduceParallelismIsDeterministic:
    """Paso 2 (plan rag-plan-latencia-2026-09-09): paralelizar el map-reduce
    por documento no puede cambiar QUÉ se extrae ni el ORDEN en que se
    ensamblan los ítems -- solo el wall-time. El orden importa porque el
    merge/dedup/detección de conflictos río abajo depende de él.
    """

    def _setup(self, monkeypatch, *, failing_docs: set[str] | None = None):
        failing_docs = failing_docs or set()
        docs = ["doc-a", "doc-b", "doc-c"]

        chunks = [
            {
                "document_id": doc,
                "chunk_index": i,
                "content": f"contenido del {doc}",
                "primary_category": "objeto_alcance",
                "secondary_categories": [],
                "search_score": 1.0,
            }
            for i, doc in enumerate(docs)
        ]

        monkeypatch.setattr(
            extractor_base, "_retrieve_with_category_priority", lambda **kw: list(chunks)
        )
        monkeypatch.setattr(
            extractor_base, "_drop_low_relevance_chunks", lambda chunks, **kw: chunks
        )
        monkeypatch.setattr(
            extractor_base, "_truncate_to_token_budget", lambda chunks, *a, **kw: chunks
        )
        monkeypatch.setattr(extractor_base, "_verify_citation_grounding", lambda *a, **kw: None)
        monkeypatch.setattr(
            extractor_base, "_merge_split_fact_items", lambda items, *a, **kw: items
        )
        monkeypatch.setattr(
            extractor_base, "_normalize_mixed_not_found_items", lambda items, **kw: items
        )
        monkeypatch.setattr(
            "analysis.extraction.engine.validators.detect_cross_contamination",
            lambda *a, **kw: [],
        )

        # Retrasos invertidos: doc-c responde primero, doc-a último. Si el
        # ensamblado dependiera del orden de finalización, el resultado
        # quedaría [c, b, a] en vez de [a, b, c].
        delay_by_doc = {"doc-a": 0.15, "doc-b": 0.08, "doc-c": 0.01}

        def fake_call_llm(*, messages, correlation_id):
            human = messages[-1][1]
            doc = next(d for d in docs if d in human)
            if doc in failing_docs:
                raise RuntimeError(f"fallo simulado en {doc}")
            time.sleep(delay_by_doc[doc])
            return (
                {
                    "objeto_alcance": [
                        {
                            "tipo": "resumen_objeto",
                            "valor": f"item-de-{doc}",
                            "extraction_status": "success",
                            "source_references": [{"document_id": doc, "citation": "x"}],
                        }
                    ]
                },
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

        monkeypatch.setattr(extractor_base, "_call_llm", fake_call_llm)

        class _Settings:
            extraction_top_k = 25
            extraction_max_context_tokens = 16000
            query_expansion_use_semantic_definition = False
            extraction_mapreduce_concurrency = 1

        settings = _Settings()
        monkeypatch.setattr(extractor_base, "get_settings", lambda: settings)
        return settings

    def _run(self):
        state = {"correlation_id": "corr-mapreduce", "analysis_id": "an-mapreduce"}
        delta = extractor_base.run_extractor(
            state=state,
            result_key="objeto_alcance",
            state_field="objeto_alcance",
            status_field="objeto_alcance_status",
            prompt_file_name="objeto_alcance.txt",
            query="objeto y alcance",
        )
        return delta

    def test_parallel_output_matches_sequential(self, monkeypatch):
        settings = self._setup(monkeypatch)

        settings.extraction_mapreduce_concurrency = 1
        seq = self._run()
        settings.extraction_mapreduce_concurrency = 3
        par = self._run()

        seq_valores = [i["valor"] for i in seq["objeto_alcance"]]
        par_valores = [i["valor"] for i in par["objeto_alcance"]]

        assert seq_valores == ["item-de-doc-a", "item-de-doc-b", "item-de-doc-c"]
        assert par_valores == seq_valores, (
            "el orden de ensamblado no puede depender del orden de finalización de las llamadas"
        )
        assert [i["_source_document_id"] for i in par["objeto_alcance"]] == [
            "doc-a",
            "doc-b",
            "doc-c",
        ]
        assert seq["objeto_alcance_status"] == par["objeto_alcance_status"]
        assert par["objeto_alcance_token_usage"]["llm_calls"] == 3

    def test_parallel_one_group_failure_does_not_lose_the_others(self, monkeypatch):
        settings = self._setup(monkeypatch, failing_docs={"doc-b"})
        settings.extraction_mapreduce_concurrency = 3

        delta = self._run()

        valores = [i["valor"] for i in delta["objeto_alcance"]]
        assert valores == ["item-de-doc-a", "item-de-doc-c"], (
            "un fallo en un documento no puede tumbar ni reordenar los demás"
        )
        assert delta["objeto_alcance_status"] != "failed"
        assert delta["objeto_alcance_token_usage"]["llm_calls"] == 2


class TestSingleDocumentGroupSplitting:
    """FIX (2026-09-11, diagnóstico no-determinismo garantías): un pliego de
    un solo documento con muchos chunks en una categoría (ej. garantías,
    top_k=35) debe partirse en varios llamados en vez de uno solo -- el
    map-reduce por documento (2026-08-21) no ayuda en absoluto cuando hay un
    único documento. Ver `_split_oversized_groups` en item_merging.py."""

    def _setup(self, monkeypatch, *, total_chunks: int, group_max_chunks: int):
        chunks = [
            {
                "document_id": "doc-unico",
                # Orden invertido a propósito: el retrieval real ordena por
                # relevancia, no por posición -- `_group_chunks_by_document`
                # debe reordenar por `chunk_index` antes de partir en lotes.
                "chunk_index": total_chunks - 1 - i,
                "content": f"contenido chunk {total_chunks - 1 - i}",
                "primary_category": "garantias",
                "secondary_categories": [],
                "search_score": 1.0,
            }
            for i in range(total_chunks)
        ]

        monkeypatch.setattr(
            extractor_base, "_retrieve_with_category_priority", lambda **kw: list(chunks)
        )
        monkeypatch.setattr(
            extractor_base, "_drop_low_relevance_chunks", lambda chunks, **kw: chunks
        )
        monkeypatch.setattr(
            extractor_base, "_truncate_to_token_budget", lambda chunks, *a, **kw: chunks
        )
        monkeypatch.setattr(extractor_base, "_verify_citation_grounding", lambda *a, **kw: None)
        monkeypatch.setattr(
            extractor_base, "_merge_split_fact_items", lambda items, *a, **kw: items
        )
        monkeypatch.setattr(
            extractor_base, "_normalize_mixed_not_found_items", lambda items, **kw: items
        )
        monkeypatch.setattr(
            "analysis.extraction.engine.validators.detect_cross_contamination",
            lambda *a, **kw: [],
        )

        call_batches: list[list[int]] = []

        def fake_call_llm(*, messages, correlation_id):
            human = messages[-1][1]
            batch_indices = sorted(int(n) for n in __import__("re").findall(r"chunk (\d+)", human))
            call_batches.append(batch_indices)
            items = [
                {
                    "tipo": "mantenimiento_oferta",
                    "valor": f"item-chunk-{idx}",
                    "extraction_status": "success",
                    "source_references": [{"document_id": "doc-unico", "citation": "x"}],
                }
                for idx in batch_indices
            ]
            return (
                {"garantias": items},
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

        monkeypatch.setattr(extractor_base, "_call_llm", fake_call_llm)
        # Aislado de `self_consistency_runs` (glossary.json tiene 2 para
        # "garantias" desde la Fase 2 de la auditoría RAG) -- esta clase
        # prueba específicamente el split por tamaño de grupo, no las
        # corridas repetidas (eso lo cubre `TestSelfConsistencyRuns`).
        monkeypatch.setattr(
            "analysis.extraction.glossary.get_category_self_consistency_runs",
            lambda category, default=1: 1,
        )

        class _Settings:
            extraction_top_k = 35
            extraction_max_context_tokens = 16000
            query_expansion_use_semantic_definition = False
            extraction_mapreduce_concurrency = 1
            extraction_group_max_chunks = group_max_chunks

        settings = _Settings()
        monkeypatch.setattr(extractor_base, "get_settings", lambda: settings)
        return call_batches

    def _run(self):
        state = {"correlation_id": "corr-split", "analysis_id": "an-split"}
        return extractor_base.run_extractor(
            state=state,
            result_key="garantias",
            state_field="garantias",
            status_field="garantias_status",
            prompt_file_name="garantias.txt",
            query="garantias",
        )

    def test_large_single_document_group_splits_into_multiple_calls(self, monkeypatch):
        call_batches = self._setup(monkeypatch, total_chunks=35, group_max_chunks=15)

        delta = self._run()

        # 35 chunks / 15 por lote -> 3 llamados, no 1.
        assert len(call_batches) == 3
        assert delta["garantias_token_usage"]["llm_calls"] == 3

        # Cada lote es un tramo CONTIGUO en orden real del documento (no
        # salteado por score de relevancia).
        assert call_batches[0] == list(range(0, 15))
        assert call_batches[1] == list(range(15, 30))
        assert call_batches[2] == list(range(30, 35))

        # Ningún ítem se pierde en el split: los 35 llegan al resultado final.
        assert len(delta["garantias"]) == 35
        assert {item["valor"] for item in delta["garantias"]} == {
            f"item-chunk-{i}" for i in range(35)
        }

    def test_small_single_document_group_stays_as_one_call(self, monkeypatch):
        call_batches = self._setup(monkeypatch, total_chunks=5, group_max_chunks=15)

        delta = self._run()

        assert len(call_batches) == 1
        assert delta["garantias_token_usage"]["llm_calls"] == 1
        assert len(delta["garantias"]) == 5


class TestSelfConsistencyRuns:
    """Fase 2 (2026-09-14) de la auditoría RAG: con el chunking ya arreglado
    (headings/incisos), el gap que queda en garantías/requisitos_
    admisibilidad/identificacion_procedimiento/riesgos es que el LLM, frente
    a una cláusula con varios datos, saca uno y descarta otro -- de forma no
    determinista entre corridas. `self_consistency_runs` (opt-in por
    categoría en glossary.json) repite cada llamado del map-reduce N veces
    para que el dedup de aguas abajo (`merge_node`) una lo que aparezca en
    cualquiera de las corridas, en vez de depender de una sola."""

    def _setup(self, monkeypatch, *, self_consistency_runs: int):
        chunks = [
            {
                "document_id": "doc-unico",
                "chunk_index": 0,
                "content": "contenido unico",
                "primary_category": "garantias",
                "secondary_categories": [],
                "search_score": 1.0,
            }
        ]

        monkeypatch.setattr(
            extractor_base, "_retrieve_with_category_priority", lambda **kw: list(chunks)
        )
        monkeypatch.setattr(
            extractor_base, "_drop_low_relevance_chunks", lambda chunks, **kw: chunks
        )
        monkeypatch.setattr(
            extractor_base, "_truncate_to_token_budget", lambda chunks, *a, **kw: chunks
        )
        monkeypatch.setattr(extractor_base, "_verify_citation_grounding", lambda *a, **kw: None)
        monkeypatch.setattr(
            extractor_base, "_merge_split_fact_items", lambda items, *a, **kw: items
        )
        monkeypatch.setattr(
            extractor_base, "_normalize_mixed_not_found_items", lambda items, **kw: items
        )
        monkeypatch.setattr(
            "analysis.extraction.engine.validators.detect_cross_contamination",
            lambda *a, **kw: [],
        )
        monkeypatch.setattr(
            "analysis.extraction.glossary.get_category_self_consistency_runs",
            lambda category, default=1: self_consistency_runs,
        )

        call_count = {"n": 0}

        def fake_call_llm(*, messages, correlation_id):
            call_count["n"] += 1
            items = [
                {
                    "tipo": "mantenimiento_oferta",
                    "valor": f"corrida-{call_count['n']}",
                    "extraction_status": "success",
                    "source_references": [{"document_id": "doc-unico", "citation": "x"}],
                }
            ]
            return (
                {"garantias": items},
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )

        monkeypatch.setattr(extractor_base, "_call_llm", fake_call_llm)

        class _Settings:
            extraction_top_k = 35
            extraction_max_context_tokens = 16000
            query_expansion_use_semantic_definition = False
            extraction_mapreduce_concurrency = 1
            extraction_group_max_chunks = 15

        settings = _Settings()
        monkeypatch.setattr(extractor_base, "get_settings", lambda: settings)
        return call_count

    def _run(self):
        state = {"correlation_id": "corr-self-consistency", "analysis_id": "an-self-consistency"}
        return extractor_base.run_extractor(
            state=state,
            result_key="garantias",
            state_field="garantias",
            status_field="garantias_status",
            prompt_file_name="garantias.txt",
            query="garantias",
        )

    def test_default_runs_once_unchanged(self, monkeypatch):
        call_count = self._setup(monkeypatch, self_consistency_runs=1)

        delta = self._run()

        assert call_count["n"] == 1
        assert delta["garantias_token_usage"]["llm_calls"] == 1
        assert len(delta["garantias"]) == 1

    def test_two_runs_calls_twice_and_keeps_both_items(self, monkeypatch):
        call_count = self._setup(monkeypatch, self_consistency_runs=2)

        delta = self._run()

        assert call_count["n"] == 2
        assert delta["garantias_token_usage"]["llm_calls"] == 2
        # Ambos ítems sobreviven a nivel run_extractor -- el dedup entre
        # corridas pasa después, en merge_node (mismo criterio que ya usa
        # para duplicados entre documentos distintos).
        assert [item["valor"] for item in delta["garantias"]] == ["corrida-1", "corrida-2"]
