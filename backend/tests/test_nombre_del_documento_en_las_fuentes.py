"""CTX-06: la persona nunca veía de qué documento salía el dato.

La lista "Fuentes verificables" que se muestra debajo de cada categoría
renderiza `source.document_name` (`NarrativeBlocks.tsx:209`), y ese nombre era
la constante `"Documento"` (`analysisApi.ts:98` y `:415`; el tercer mapper,
`:248`, lo leía del backend, pero el backend no lo emitía nunca).

Con un solo documento eso era simplemente inútil. En el análisis de Santa Fe
--`18a86363-…`, un pliego y cuatro anexos-- las cinco fuentes se leen igual:

    Documento · pág. 3
    Documento · pág. 2
    Documento · pág. 3

Tres fuentes que pueden ser de tres archivos distintos, y "pág. 3" del
`Pliego - Santa Fe.pdf` se lee igual que "pág. 3" del `ANEXO IV`, que son dos
páginas distintas de dos documentos distintos.

En esa misma salida, las 20 `source_references` traían `"filename": null` y
`"is_primary": null`: los campos existían y nadie los escribía.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.graph import _stampar_nombre_de_documento

PRINCIPAL = "ebe9dca5-ba5d-432f-a658-8d7026974e8b"
ANEXO = "c7ebfe58-c452-414a-a213-4c14410c6330"

ETIQUETAS: dict[str, dict[str, Any]] = {
    PRINCIPAL: {"nombre": "Pliego - Santa Fe.pdf", "es_principal": True},
    ANEXO: {"nombre": "ANEXO IV - Santa Fe.pdf", "es_principal": False},
}


def _referencia(document_id: str, citation: str = "una cita cualquiera del pliego") -> dict[str, Any]:
    return {"document_id": document_id, "page_number": 1, "citation": citation}


# ---------------------------------------------------------------------------
# El caso del hallazgo, con la forma real de la salida de Santa Fe
# ---------------------------------------------------------------------------


def test_las_referencias_de_los_items_dicen_de_que_archivo_salen() -> None:
    datos = {
        "requisitos_admisibilidad": [
            {"valor": "antigüedad mínima de dos (2) años", "source_references": [_referencia(ANEXO)]},
        ],
        "objeto_alcance": [
            {"valor": "sistema de almacenamiento", "source_references": [_referencia(PRINCIPAL)]},
        ],
    }

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    del_anexo = datos["requisitos_admisibilidad"][0]["source_references"][0]
    del_pliego = datos["objeto_alcance"][0]["source_references"][0]
    assert del_anexo["filename"] == "ANEXO IV - Santa Fe.pdf"
    assert del_anexo["is_primary"] is False
    assert del_pliego["filename"] == "Pliego - Santa Fe.pdf"
    assert del_pliego["is_primary"] is True


def test_las_sources_de_la_narrativa_tambien() -> None:
    """Es LA lista que el frontend renderiza: si sólo se estampan las
    referencias de los ítems, la pantalla sigue diciendo "Documento"."""
    datos = {
        "objeto_alcance_narrative": {
            "blocks": [{"type": "paragraph", "text": "…", "source_ids": [0]}],
            "sources": [dict(_referencia(PRINCIPAL), id=0), dict(_referencia(ANEXO), id=1)],
        }
    }

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    sources = datos["objeto_alcance_narrative"]["sources"]
    assert [s["filename"] for s in sources] == ["Pliego - Santa Fe.pdf", "ANEXO IV - Santa Fe.pdf"]
    assert [s["is_primary"] for s in sources] == [True, False]


def test_dos_fuentes_de_la_misma_pagina_de_documentos_distintos_se_distinguen() -> None:
    """El caso concreto que motivó el hallazgo: sin nombre, `pág. 1` y `pág. 1`
    son la misma línea dos veces."""
    datos = {
        "sources": [
            {"id": 0, "document_id": PRINCIPAL, "page_number": 1, "citation": "una cita del pliego"},
            {"id": 1, "document_id": ANEXO, "page_number": 1, "citation": "una cita del anexo"},
        ]
    }

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    renglones = [f"{s['filename']} · pág. {s['page_number']}" for s in datos["sources"]]
    assert renglones == [
        "Pliego - Santa Fe.pdf · pág. 1",
        "ANEXO IV - Santa Fe.pdf · pág. 1",
    ]


def test_el_presupuesto_es_un_objeto_y_no_una_lista() -> None:
    """`estimacion_presupuesto` no tiene la forma `categoria[].source_references[]`
    del resto. Por eso el recorrido es genérico y no una lista de rutas."""
    datos = {"estimacion_presupuesto": {"monto": 100, "source_references": [_referencia(PRINCIPAL)]}}

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    assert datos["estimacion_presupuesto"]["source_references"][0]["filename"] == "Pliego - Santa Fe.pdf"


# ---------------------------------------------------------------------------
# Degradación
# ---------------------------------------------------------------------------


def test_sin_etiquetas_no_se_toca_nada() -> None:
    """`_build_document_labels` devuelve `{}` cuando no hay sesión. Perder los
    nombres no puede corromper la salida ni inventar un nombre."""
    datos = {"sources": [_referencia(PRINCIPAL)]}

    _stampar_nombre_de_documento(datos, {})

    assert datos == {"sources": [_referencia(PRINCIPAL)]}
    assert "filename" not in datos["sources"][0]


def test_un_documento_que_no_esta_en_las_etiquetas_queda_sin_nombre() -> None:
    """Un documento borrado entre la indexación y la síntesis: la referencia se
    conserva tal cual, para que el consumidor caiga a su default."""
    datos = {"sources": [_referencia("uuid-desconocido")]}

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    assert "filename" not in datos["sources"][0]


def test_un_documento_sin_nombre_deja_filename_en_none_pero_marca_el_rol() -> None:
    datos = {"sources": [_referencia(PRINCIPAL)]}

    _stampar_nombre_de_documento(datos, {PRINCIPAL: {"nombre": "", "es_principal": True}})

    assert datos["sources"][0]["filename"] is None
    assert datos["sources"][0]["is_primary"] is True


def test_un_dict_sin_citation_no_es_una_fuente() -> None:
    """`document_id` solo no alcanza: los chunks y el mapeo a blob path también
    lo tienen, y no son referencias a fuentes."""
    datos = {"chunk": {"document_id": PRINCIPAL, "content": "texto del chunk"}}

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    assert "filename" not in datos["chunk"]


def test_estructuras_raras_no_rompen() -> None:
    datos: dict[str, Any] = {
        "vacio": None,
        "numero": 3,
        "lista_de_listas": [[_referencia(PRINCIPAL)]],
        "texto": "no soy un dict",
    }

    _stampar_nombre_de_documento(datos, ETIQUETAS)

    assert datos["lista_de_listas"][0][0]["filename"] == "Pliego - Santa Fe.pdf"


def test_es_idempotente() -> None:
    datos = {"sources": [_referencia(PRINCIPAL)]}

    _stampar_nombre_de_documento(datos, ETIQUETAS)
    primera = dict(datos["sources"][0])
    _stampar_nombre_de_documento(datos, ETIQUETAS)

    assert datos["sources"][0] == primera


# ---------------------------------------------------------------------------
# El contrato: los campos tienen que estar declarados o pydantic los descarta
# ---------------------------------------------------------------------------


def test_source_reference_declara_los_campos() -> None:
    """Mismo bug que ya se corrigió dos veces (`unverified` en ATR y `chunk_id`
    en ATR-05): un campo no declarado sobrevive en el dict pero desaparece en el
    primer `model_validate`."""
    from analysis.extraction.schemas import SourceReference

    ref = SourceReference.model_validate(
        {
            "document_id": PRINCIPAL,
            "page_number": 1,
            "citation": "garantía de mantenimiento de oferta del 5% del presupuesto",
            "filename": "Pliego - Santa Fe.pdf",
            "is_primary": True,
        }
    )

    assert ref.filename == "Pliego - Santa Fe.pdf"
    assert ref.is_primary is True


def test_narrative_source_declara_los_campos() -> None:
    from analysis.extraction.schemas import NarrativeSource

    source = NarrativeSource.model_validate(
        {
            "id": 0,
            "document_id": ANEXO,
            "page_number": 1,
            "citation": "antigüedad mínima de dos (2) años en la actividad",
            "filename": "ANEXO IV - Santa Fe.pdf",
            "is_primary": False,
        }
    )

    assert source.filename == "ANEXO IV - Santa Fe.pdf"
    assert source.is_primary is False


def test_los_campos_son_opcionales_y_el_default_es_none() -> None:
    """Una referencia vieja, ya persistida sin estos campos, tiene que seguir
    validando."""
    from analysis.extraction.schemas import SourceReference

    ref = SourceReference.model_validate(
        {"document_id": PRINCIPAL, "page_number": 1, "citation": "una cita cualquiera del pliego"}
    )

    assert ref.filename is None
    assert ref.is_primary is None
