"""FIX (auditoría 2026-08-12, flujo Cosmos): `extract_and_index_cosmos` corre
como background task tras crear un análisis en modo cosmos_only. Si el primer
`_load_analysis_or_none(analysis_id)` fallaba por un problema transitorio de
Cosmos (throttling, timeout, outage), la excepción se propagaba sin atrapar
-- el análisis quedaba varado en 'queued' para siempre, sin ningún log de
error que lo explique. Este test fija que ahora se atrapa y se loguea."""

from __future__ import annotations

import pytest

import analysis.cosmos_runtime as cosmos_runtime


def test_extract_and_index_no_propaga_si_falla_la_carga_inicial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_analysis_id: str):
        raise RuntimeError("simulated Cosmos outage")

    monkeypatch.setattr(cosmos_runtime, "_load_analysis_or_none", _raise)

    called_query_documents = False

    def _fail_if_called(*_args, **_kwargs):
        nonlocal called_query_documents
        called_query_documents = True
        raise AssertionError("no deberia llegar a consultar documentos si la carga inicial fallo")

    monkeypatch.setattr(cosmos_runtime, "_query_documents", _fail_if_called)

    # No debe levantar -- antes de este fix, RuntimeError se propagaba tal cual.
    cosmos_runtime.extract_and_index_cosmos("analysis-1")

    assert called_query_documents is False


def test_extract_and_index_analysis_inexistente_no_propaga(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caso ya soportado antes del fix: `_load_analysis_or_none` devuelve
    None limpio (análisis realmente no existe) -- sigue sin propagar nada."""
    monkeypatch.setattr(cosmos_runtime, "_load_analysis_or_none", lambda _analysis_id: None)

    cosmos_runtime.extract_and_index_cosmos("analysis-inexistente")


# =============================================================================
# FIX (auditoría 2026-08-12): hallazgos #1 (timeout nunca se hace cumplir en
# cosmos_only), #2 (chequeo de cancelación con huecos + escrituras ciegas que
# "des-cancelan" en silencio) y #6 (sin concurrencia optimista / ETag en
# ningún write de Cosmos). Estos tests usan el fixture `cosmos_only` (definido
# en conftest.py) para ejercitar `cosmos_runtime.py` contra un
# `FakeCosmosContainer` real, en vez de monkeypatchear las funciones internas
# -- así se prueba el contrato completo de lectura/escritura, no solo que una
# función interna haya sido invocada.
# =============================================================================


def _seed_analysis(container, analysis_id: str, **overrides) -> dict:
    item = {
        "id": cosmos_runtime._analysis_item_id(analysis_id),
        "type": "analysis",
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "created_by": "user-1",
        "created_by_name": "Usuario de Prueba",
        "analysis_name": "Pliego de prueba",
        "status": "processing",
        "current_stage": "extracting_text",
        "progress_percentage": 10,
        "current_version_id": None,
        "correlation_id": "corr-1",
        "cancellation_requested": False,
        "error_message": None,
        "started_at": "2026-08-12T10:00:00+00:00",
        "timeout_at": None,
        "timeout_warning_at": None,
        "extraction_metadata": {"timeout_minutes": 8},
        "deleted": False,
        "created_at": "2026-08-12T09:00:00+00:00",
        "updated_at": "2026-08-12T10:00:00+00:00",
    }
    item.update(overrides)
    # upsert_item (no add) para que el item quede con un `_etag` real, igual
    # que cualquier item que de verdad haya pasado por Cosmos -- necesario
    # para poder probar la guarda de concurrencia optimista sobre datos
    # seedeados.
    container.upsert_item(item)
    return item


def test_check_should_stop_cosmos_detecta_cancelacion(cosmos_only) -> None:
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-cancel-1"
    _seed_analysis(container, analysis_id, cancellation_requested=True)

    stopped = cosmos_runtime._check_should_stop_cosmos(analysis_id)

    assert stopped is True
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "cancelled"
    assert stored["error_message"] == "El analisis fue cancelado por el usuario"


def test_check_should_stop_cosmos_detecta_timeout(cosmos_only) -> None:
    """FIX hallazgo #1: antes NADA chequeaba `timeout_at` en cosmos_only --
    un análisis colgado se quedaba en 'processing' para siempre."""
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-timeout-1"
    _seed_analysis(
        container,
        analysis_id,
        timeout_at="2020-01-01T00:00:00+00:00",  # muy en el pasado
        extraction_metadata={"timeout_minutes": 8},
    )

    stopped = cosmos_runtime._check_should_stop_cosmos(analysis_id)

    assert stopped is True
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "error"
    assert "tiempo maximo" in stored["error_message"]
    assert "8 minutos" in stored["error_message"]


def test_check_should_stop_cosmos_continua_si_no_hay_problema(cosmos_only) -> None:
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-ok-1"
    _seed_analysis(
        container,
        analysis_id,
        timeout_at="2099-01-01T00:00:00+00:00",  # muy en el futuro
        cancellation_requested=False,
    )

    stopped = cosmos_runtime._check_should_stop_cosmos(analysis_id)

    assert stopped is False
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "processing"  # sin cambios


def test_finalize_analysis_cosmos_no_pisa_estado_terminal_previo(cosmos_only) -> None:
    """FIX hallazgo #2 -- el bug de "un-cancel" silencioso: si mientras
    `graph.invoke()` corría el usuario canceló (u otro camino ya marcó el
    análisis como terminal), el write final de éxito NO debe pisarlo."""
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-finalize-1"
    _seed_analysis(container, analysis_id, status="cancelled", error_message="El analisis fue cancelado por el usuario")

    wrote = cosmos_runtime._finalize_analysis_cosmos(
        analysis_id,
        "analysis_version_created",
        lambda fresh: fresh.update(status="analyzed", error_message=None),
    )

    assert wrote is False
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "cancelled"  # nunca se convirtió en "analyzed"


def test_finalize_analysis_cosmos_escribe_si_todavia_no_es_terminal(cosmos_only) -> None:
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-finalize-2"
    _seed_analysis(container, analysis_id, status="processing")

    wrote = cosmos_runtime._finalize_analysis_cosmos(
        analysis_id,
        "analysis_version_created",
        lambda fresh: fresh.update(status="analyzed", progress_percentage=100),
    )

    assert wrote is True
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "analyzed"
    assert stored["progress_percentage"] == 100


def test_upsert_analysis_sin_etag_hace_upsert_normal(cosmos_only) -> None:
    """Un item recién creado en memoria (nunca leído de Cosmos) no tiene
    `_etag` todavía -- debe seguir escribiendo sin guarda, como antes."""
    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-new-1"
    analysis = {
        "id": cosmos_runtime._analysis_item_id(analysis_id),
        "partition_key": analysis_id,
        "analysis_id": analysis_id,
        "status": "draft",
    }

    cosmos_runtime._upsert_analysis(analysis, "analysis_created")

    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "draft"
    assert stored["_etag"]  # Cosmos siempre devuelve un etag nuevo, aunque el llamador no lo haya pedido


def test_upsert_analysis_con_etag_desactualizado_no_pisa_en_silencio(cosmos_only) -> None:
    """FIX hallazgo #6: sin ETag, dos escritores concurrentes sobre el mismo
    analysis se resolvían 'last write wins' sin aviso. Simulamos: A lee el
    analysis (etag_1), B escribe primero (etag_2), A intenta escribir con su
    copia vieja (etag_1) -- debe fallar en vez de pisar el cambio de B."""
    from azure.cosmos.exceptions import CosmosAccessConditionFailedError

    container, _user_id, _token = cosmos_only
    analysis_id = "analysis-conflict-1"
    _seed_analysis(container, analysis_id, status="processing")

    # A lee el estado (se lleva el etag_1)
    a_copy = cosmos_runtime._load_analysis_or_none(analysis_id)
    assert a_copy is not None
    assert a_copy.get("_etag")

    # B (ej: el usuario cancelando desde otro request) lee y escribe primero.
    b_copy = cosmos_runtime._load_analysis_or_none(analysis_id)
    b_copy["status"] = "cancelled"
    b_copy["error_message"] = "El analisis fue cancelado por el usuario"
    cosmos_runtime._upsert_analysis(b_copy, "analysis_cancelled")

    # A intenta escribir con su copia desactualizada (etag_1, ya no vigente).
    a_copy["status"] = "analyzed"
    with pytest.raises(CosmosAccessConditionFailedError):
        cosmos_runtime._upsert_analysis(a_copy, "analysis_version_created")

    # El cambio de B (la cancelación) sigue vigente -- A no lo pisó.
    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    assert stored["status"] == "cancelled"


def test_extract_and_index_cosmos_no_revierte_cancelacion_ocurrida_durante_graph_invoke(
    cosmos_only, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test end-to-end del bug de "un-cancel": el usuario cancela MIENTRAS
    `graph.invoke()` está corriendo (el único tramo largo sin ningún chequeo
    de cancelación en el medio, igual que en modo SQL). El write final de
    éxito no debe revertir esa cancelación."""
    container, user_id, _token = cosmos_only
    analysis_id = "analysis-e2e-cancel-1"
    _seed_analysis(
        container,
        analysis_id,
        status="draft",
        current_stage="queued",
        created_by=user_id,
        cancellation_requested=False,
    )
    container.add(
        {
            "id": "document::doc-1",
            "type": "document",
            "partition_key": analysis_id,
            "analysis_id": analysis_id,
            "document_id": "doc-1",
            "filename": "pliego.pdf",
            "blob_name": f"{analysis_id}/doc-1-pliego.pdf",
            "page_count": 1,
            "is_primary": True,
            "deleted": False,
            "uploaded_at": "2026-08-12T09:00:00+00:00",
        }
    )

    class _FakeBlobStorage:
        def generate_download_url(self, _blob_name: str) -> str:
            return "https://example.invalid/fake.pdf"

    def _fake_graph_invoke(_state, config=None):
        # Simula que el usuario cancela DESDE OTRO REQUEST mientras esta
        # llamada (la única sin chequeo intermedio) todavía está en vuelo.
        live = cosmos_runtime._load_analysis_or_none(analysis_id)
        live["cancellation_requested"] = True
        live["status"] = "cancelled"
        live["current_stage"] = "completed"
        live["error_message"] = "El analisis fue cancelado por el usuario"
        cosmos_runtime._upsert_analysis(live, "analysis_cancelled")
        return {"extracted_data": {}, "conflicts": [], "extraction_metadata": {"token_usage": {}}}

    monkeypatch.setattr(cosmos_runtime, "_build_blob_storage", lambda: _FakeBlobStorage())
    monkeypatch.setattr(
        cosmos_runtime,
        "extract_text",
        lambda *_a, **_k: [{"page_number": 1, "content": "contenido"}],
    )
    monkeypatch.setattr(
        cosmos_runtime,
        "create_chunks",
        lambda *_a, **_k: [{"document_id": "doc-1", "page_number": 1, "chunk_index": 0, "content": "x", "token_count": 1}],
    )
    monkeypatch.setattr(cosmos_runtime, "generate_embeddings", lambda chunks, *_a, **_k: chunks)
    monkeypatch.setattr(cosmos_runtime, "upload_chunks", lambda *_a, **_k: None)
    monkeypatch.setattr(cosmos_runtime, "validate_prompt_inventory", lambda: None)
    monkeypatch.setattr(cosmos_runtime.graph, "invoke", _fake_graph_invoke)

    cosmos_runtime.extract_and_index_cosmos(analysis_id)

    stored = container.items[cosmos_runtime._analysis_item_id(analysis_id)]
    # ANTES del fix: esto terminaba en "analyzed", revirtiendo la
    # cancelación del usuario en silencio.
    assert stored["status"] == "cancelled"
    assert stored["current_version_id"] is None
