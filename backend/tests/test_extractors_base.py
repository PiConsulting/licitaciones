# Tests para analysis/extraction/extractors/base.py — US-2.2 y US-2.3
# (auditoría RAG 2026-08-12, hallazgos M-2 y M-3)

from __future__ import annotations

import pytest

from analysis.extraction.extractors import base


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

        def fake_search(*, query, analysis_id, top_k, keyword_query):
            return list(candidates)

        monkeypatch.setattr(base, "search_hybrid", fake_search)

        result = base._retrieve_with_category_priority(
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

        def fake_search(*, query, analysis_id, top_k, keyword_query):
            return list(candidates)

        monkeypatch.setattr(base, "search_hybrid", fake_search)

        result = base._retrieve_with_category_priority(
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

        def fake_search(*, query, analysis_id, top_k, keyword_query):
            return list(candidates)

        monkeypatch.setattr(base, "search_hybrid", fake_search)

        result = base._retrieve_with_category_priority(
            query="garantías exigidas",
            analysis_id="analysis-1",
            top_k=2,
            keyword_query="garantia caucion",
            category="garantias",
            correlation_id="corr-1",
        )

        # No debe lanzar excepción y debe devolver ambos chunks.
        assert {c["chunk_index"] for c in result} == {0, 1}


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

        monkeypatch.setattr(base, "_get_token_encoder", lambda: FakeEncoder())

        # Chunk 1: "ab" -> 1 palabra, pero 6 "tokens" con el fake encoder.
        # Chunk 2: "cd" -> ídem.
        # Presupuesto=6: por palabras entrarían los dos (1+1=2 <= 6); por
        # tokens reales el primero solo ya usa el presupuesto entero (6) y
        # el segundo debe quedar afuera.
        chunks = [{"content": "ab"}, {"content": "cd"}]
        kept = base._truncate_to_token_budget(chunks, budget=6)
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
        monkeypatch.setattr(base, "_get_token_encoder", lambda: None)  # conteo por palabras, determinístico

        chunks = [
            {"content": "una dos tres"},  # 3 palabras, entra
            {"content": "cuatro"},  # entraría solo (1 palabra) pero ya no hay presupuesto
            {"content": "cinco seis"},  # tampoco entra
        ]
        import structlog

        with structlog.testing.capture_logs() as captured:
            kept = base._truncate_to_token_budget(
                chunks, budget=3, correlation_id="corr-test", category="plazos_clave"
            )

        assert len(kept) == 1
        warnings = [e for e in captured if e.get("event") == "extraction_chunks_dropped_token_budget"]
        assert len(warnings) == 1, "debe loguear un warning con el descarte"
        assert warnings[0]["chunks_dropped"] == 2
        assert warnings[0]["chunks_kept"] == 1
        assert warnings[0]["category"] == "plazos_clave"
        assert warnings[0]["correlation_id"] == "corr-test"

    def test_no_warning_logged_when_all_chunks_fit(self, monkeypatch):
        """Caso feliz: si todos los chunks entran en el presupuesto, no debe
        loguearse ningún warning de descarte."""
        monkeypatch.setattr(base, "_get_token_encoder", lambda: None)

        import structlog

        with structlog.testing.capture_logs() as captured:
            kept = base._truncate_to_token_budget(
                [{"content": "una dos"}], budget=10, correlation_id="corr-test", category="garantias"
            )

        assert kept == [{"content": "una dos"}]
        assert not any(e.get("event") == "extraction_chunks_dropped_token_budget" for e in captured)

    def test_falls_back_to_word_count_when_encoder_unavailable(self, monkeypatch):
        """Si el encoder no está disponible (p.ej. sin conectividad la
        primera vez que se descarga el archivo de encoding), no debe
        crashear la extracción -- cae al conteo por palabras de antes."""
        monkeypatch.setattr(base, "_get_token_encoder", lambda: None)

        chunks = [{"content": "una dos tres"}]  # 3 palabras
        kept = base._truncate_to_token_budget(chunks, budget=3)
        assert kept == chunks

        kept_over_budget = base._truncate_to_token_budget(
            [{"content": "una dos tres"}, {"content": "cuatro"}], budget=3
        )
        assert len(kept_over_budget) == 1

    def test_count_tokens_never_raises_if_encoder_encode_fails(self, monkeypatch):
        """Si `encoder.encode()` explota en runtime, `_count_tokens` cae al
        conteo por palabras en vez de propagar la excepción."""

        class BrokenEncoder:
            def encode(self, text: str) -> list[int]:
                raise RuntimeError("boom")

        monkeypatch.setattr(base, "_get_token_encoder", lambda: BrokenEncoder())

        assert base._count_tokens("una dos tres") == 3

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
        base._get_token_encoder.cache_clear()
        try:
            token_count = base._count_tokens(text)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"tiktoken no pudo inicializar el encoding en este entorno: {exc}")
        finally:
            base._get_token_encoder.cache_clear()

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

        result = base._augment_identificacion_payload(payload, chunks)

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

        result = base._augment_identificacion_payload(payload, chunks)

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

        result = base._augment_identificacion_payload(payload, chunks)

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

        result = base._augment_identificacion_payload(payload, chunks)

        presupuestos = [item for item in result if item["tipo"] == "presupuesto_oficial"]
        assert len(presupuestos) == 1, f"debería reconocer un presupuesto real; items: {result}"
        assert "3.850.000" in presupuestos[0]["valor"]
        assert "EXPEDIENTE" not in presupuestos[0]["valor"].upper(), (
            "no debería comerse el campo siguiente (Expediente) dentro del valor del presupuesto"
        )
