"""CHK-10: el `except Exception` del loop de chunking convertía errores de
código en pérdida silenciosa de datos.

El `except` está bien pensado para lo que fue escrito: un bloque con datos raros
no debería tumbar el chunking del pliego entero. Pero no distinguía "este bloque
tiene una forma que no esperábamos" de "el código tiene un error", y las dos
cosas terminaban en un `warning` por bloque y en un documento indexado al que le
faltan pedazos. Como el resultado es un análisis *incompleto* y no un análisis
*fallido*, nada aguas abajo lo nota: la persona recibe una respuesta con menos
evidencia y ninguna señal de que falta algo.

No es hipotético. Pasó dos veces durante esta misma auditoría:

  - un `NameError` (variable mal escrita en la rama de tablas de
    `_blocks_data_for`) produjo un documento indexado con CERO chunks de tabla;
  - un `AttributeError` (asumir que `table_ref` es siempre un dict) estuvo a un
    paso de lo mismo, y sólo se vio porque explotó FUERA de este `try`.

En los dos casos el análisis terminó "bien".
"""

from __future__ import annotations

from typing import Any

import pytest

from extraction import chunking
from extraction.chunking import create_chunks


def _parrafo(contenido: str, page: int = 1, source_order: int = 0) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


BLOQUES = [
    _parrafo("El plazo de entrega será de noventa (90) días corridos desde la orden.", 1, 0),
    _parrafo("La garantía de mantenimiento será del 5% del presupuesto oficial.", 1, 1),
]


# ---------------------------------------------------------------------------
# Los errores de programación tienen que propagar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", [NameError, AttributeError, TypeError])
def test_un_error_de_codigo_no_se_traga(monkeypatch: pytest.MonkeyPatch, error: type) -> None:
    """El caso de los dos incidentes reales. Antes esto devolvía una lista de
    chunks incompleta y un warning."""

    def explota(*_args: Any, **_kwargs: Any) -> None:
        raise error("bug del pipeline")

    monkeypatch.setattr(chunking, "classify_chunk_categories", explota)

    with pytest.raises(error):
        create_chunks(BLOQUES, document_id="doc", correlation_id="corr")


def test_el_documento_no_queda_indexado_a_medias_por_un_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lo que importa no es que levante la excepción: es que NO devuelva un
    resultado parcial que aguas abajo se ve idéntico a uno completo."""

    original = chunking.classify_chunk_categories
    llamadas = {"n": 0}

    def falla_en_el_segundo(chunk: dict[str, Any]) -> Any:
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise NameError("chunk_content")
        return original(chunk)

    monkeypatch.setattr(chunking, "classify_chunk_categories", falla_en_el_segundo)

    # Una página por bloque: si van todos en la misma,
    # `_merge_intermediate_blocks` los fusiona en uno solo y el segundo chunk
    # nunca llega a existir.
    with pytest.raises(NameError):
        create_chunks(
            [_parrafo(f"Artículo {n}. Texto suficiente del pliego para producir un chunk.", n + 1, n) for n in range(4)],
            document_id="doc",
            correlation_id="corr",
        )


# ---------------------------------------------------------------------------
# Guardas: el `except` sigue haciendo lo que fue escrito para hacer
# ---------------------------------------------------------------------------


def test_un_bloque_con_datos_raros_sigue_sin_tumbar_el_pliego(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Esa era la razón de ser del `except`, y se conserva: un error que SÍ
    puede venir de los datos no puede costar el documento entero."""

    original = chunking.classify_chunk_categories
    llamadas = {"n": 0}

    def falla_en_el_primero(chunk: dict[str, Any]) -> Any:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise ValueError("un dato con una forma inesperada")
        return original(chunk)

    monkeypatch.setattr(chunking, "classify_chunk_categories", falla_en_el_primero)

    chunks = create_chunks(
        [_parrafo(f"Artículo {n}. Texto suficiente del pliego para producir un chunk.", n + 1, n) for n in range(4)],
        document_id="doc",
        correlation_id="corr",
    )

    assert chunks, "un bloque con datos raros se llevó puesto el pliego entero"


def test_lo_que_se_saltea_queda_contado(monkeypatch: pytest.MonkeyPatch, caplog: Any) -> None:
    """Un warning por bloque se pierde entre el ruido. El conteo agregado en
    nivel error es lo único que hace visible que el documento está incompleto."""
    import logging

    original = chunking.classify_chunk_categories

    def falla_siempre_en_la_pagina_2(chunk: dict[str, Any]) -> Any:
        if chunk.get("page_number") == 2:
            raise ValueError("dato raro")
        return original(chunk)

    monkeypatch.setattr(chunking, "classify_chunk_categories", falla_siempre_en_la_pagina_2)

    with caplog.at_level(logging.ERROR):
        create_chunks(
            [
                _parrafo("Artículo 1. Texto suficiente del pliego para producir un chunk.", 1, 0),
                _parrafo("Artículo 2. Texto suficiente del pliego para producir un chunk.", 2, 1),
            ],
            document_id="doc",
            correlation_id="corr",
        )

    assert "chunking_blocks_skipped_total" in caplog.text


def test_un_pliego_sano_no_reporta_nada_saltado(caplog: Any) -> None:
    """Guarda contra el falso positivo: el log de error no puede aparecer en
    una corrida normal, o deja de significar algo."""
    import logging

    with caplog.at_level(logging.ERROR):
        chunks = create_chunks(BLOQUES, document_id="doc", correlation_id="corr")

    assert chunks
    assert "chunking_blocks_skipped_total" not in caplog.text
