"""CHK-02 y CHK-03: cada chunk tiene que declarar SUS bloques, no los del vecino.

`source.blocks` es lo que persiste en el índice como "de dónde salió este
texto": para_id, página y bbox de cada párrafo original. De ahí sale la
trazabilidad chunk → bloque → coordenadas.

Dos formas de mentir en ese campo:

  - CHK-02: `_merge_intermediate_blocks` fusiona N párrafos y guarda sus
    `merged_blocks`. Después `_split_block_into_chunks` parte ese bloque en M
    piezas, y CADA pieza recibía la lista completa de los N. Una sección de 5
    párrafos partida en 2 chunks daba un segundo chunk que declaraba los bbox de
    los 5.

  - CHK-03: los chunks `child` se armaban con `{**chunk_dict}`, una copia
    superficial. `source` quedaba siendo el MISMO objeto del parent -- con los
    bloques del artículo completo. Todo el punto de parent/child es que el child
    sea más preciso; con el source heredado, citar el inciso b) resaltaba el
    artículo entero.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import create_chunks


def _parrafo(content: str, para_id: str, page: int = 1, source_order: int = 0) -> dict[str, Any]:
    return {
        "content": content,
        "page_number": page,
        "source_order": source_order,
        "para_id": para_id,
        "bbox": [{"page": page, "x": 10.0, "y": 100.0 * (source_order + 1), "width": 400.0, "height": 20.0}],
    }


def _para_ids(chunk: dict[str, Any]) -> set[str]:
    blocks = (chunk.get("source") or {}).get("blocks") or []
    return {str(block.get("para_id")) for block in blocks if block.get("para_id")}


# ---------------------------------------------------------------------------
# CHK-02: las piezas de un bloque partido
# ---------------------------------------------------------------------------


def test_cada_pieza_declara_solo_los_parrafos_que_contiene() -> None:
    """Cinco párrafos largos que se fusionan y después se parten por tamaño."""
    parrafos = [
        _parrafo(f"Párrafo número {i} del artículo. " + " ".join([f"palabra{i}"] * 60), f"para_{i}", source_order=i)
        for i in range(5)
    ]

    chunks = create_chunks(parrafos, document_id="doc", correlation_id="corr", chunk_size=120)

    assert len(chunks) > 1, "el caso sólo tiene sentido si el bloque se partió"
    for chunk in chunks:
        for block in (chunk.get("source") or {}).get("blocks") or []:
            contenido = str(block.get("content", ""))
            if contenido:
                # Cada bloque declarado tiene que estar en el texto del chunk.
                assert contenido.split()[0] in chunk["content"], (
                    f"el chunk declara el bloque {block.get('para_id')} pero no contiene su texto"
                )


def test_dos_piezas_del_mismo_bloque_no_declaran_los_mismos_parrafos() -> None:
    parrafos = [
        _parrafo(f"Sección {i}. " + " ".join([f"termino{i}"] * 60), f"para_{i}", source_order=i) for i in range(4)
    ]

    chunks = create_chunks(parrafos, document_id="doc", correlation_id="corr", chunk_size=120)
    con_bloques = [chunk for chunk in chunks if _para_ids(chunk)]

    assert len(con_bloques) > 1
    todos_iguales = all(_para_ids(chunk) == _para_ids(con_bloques[0]) for chunk in con_bloques)
    assert not todos_iguales, "todas las piezas declaran exactamente los mismos párrafos"


def test_un_solo_parrafo_conserva_su_trazabilidad() -> None:
    """Guarda: el filtro no puede dejar chunks sin ningún bloque declarado."""
    chunks = create_chunks(
        [_parrafo("Un párrafo corto y solitario del pliego.", "para_1")],
        document_id="doc",
        correlation_id="corr",
    )

    assert chunks
    assert _para_ids(chunks[0]) == {"para_1"}


# ---------------------------------------------------------------------------
# CHK-03: los children de un artículo con incisos
# ---------------------------------------------------------------------------


# Cada inciso tiene que superar `_INCISO_MIN_SUBSTANTIVE_CHARS` (100) y el
# artículo entero `_PARENT_CHILD_MIN_CHARS` para que se generen los children.
ARTICULO_CON_INCISOS = (
    "Artículo 14. Documentación a presentar junto con la oferta económica en el sobre cerrado.\n"
    "a) Constancia de inscripción en el Registro Único de Proveedores de la Municipalidad, "
    "vigente al momento de la apertura de sobres y emitida con no más de treinta días corridos "
    "de antigüedad respecto de la fecha del acto de apertura de la presente licitación.\n"
    "b) Garantía de mantenimiento de oferta equivalente al uno por ciento (1%) del presupuesto "
    "oficial, constituida mediante póliza de seguro de caución a satisfacción del organismo "
    "contratante, con vigencia no inferior al plazo de mantenimiento de la oferta.\n"
    "c) Declaración jurada de no encontrarse en litigio judicial ni administrativo con el "
    "Municipio, ni de haber sido sancionado en los últimos cinco años por incumplimiento "
    "contractual en cualquier jurisdicción del territorio de la República Argentina.\n"
)


# Azure Document Intelligence devuelve un párrafo por inciso, cada uno con su
# propio `para_id` y su propio bbox. `_merge_intermediate_blocks` los fusiona en
# un solo bloque bajo el mismo encabezado, y ahí es donde `merged_blocks` pasa a
# tener cuatro entradas: es el caso en el que el filtro por pieza importa.
INTRO, INCISO_A, INCISO_B, INCISO_C = [
    parte.strip() for parte in ARTICULO_CON_INCISOS.strip().split("\n")
]


def _chunks_del_articulo() -> list[dict[str, Any]]:
    blocks = [{"heading_level": 1, "content": "Artículo 14", "page_number": 3, "source_order": 0}]
    for orden, texto in enumerate([INTRO, INCISO_A, INCISO_B, INCISO_C], start=1):
        blocks.append(_parrafo(texto, f"para_1{orden}", page=3, source_order=orden))
    return create_chunks(blocks, document_id="doc", correlation_id="corr")


def test_el_child_no_comparte_el_objeto_source_con_el_parent() -> None:
    """Era una copia superficial: el mismo dict en memoria. Una mutación en
    cualquiera se propagaba a todos."""
    chunks = _chunks_del_articulo()
    parent = next((c for c in chunks if c.get("chunk_type") == "parent"), None)
    children = [c for c in chunks if c.get("chunk_type") == "child"]

    assert parent is not None, "el artículo de prueba tiene que producir un parent"
    assert children, "el artículo de prueba tiene que producir children"

    for child in children:
        assert child["source"] is not parent["source"]
        assert child["source"]["blocks"] is not parent["source"]["blocks"]


def test_el_child_declara_bloques_acotados_a_su_inciso() -> None:
    chunks = _chunks_del_articulo()
    children = [c for c in chunks if c.get("chunk_type") == "child"]

    assert children, "el artículo de prueba tiene que producir children"

    # Cada inciso vino como su propio párrafo, así que cada child tiene que
    # declarar SU párrafo -- no los cuatro del artículo.
    por_titulo = {child["title"]: _para_ids(child) for child in children}

    assert por_titulo["Artículo 14.a"] == {"para_12"}
    assert por_titulo["Artículo 14.b"] == {"para_13"}
    assert por_titulo["Artículo 14.c"] == {"para_14"}


def test_el_parent_sigue_declarando_el_articulo_completo() -> None:
    """El parent es el que debe traer el contexto entero: es para eso que existe."""
    chunks = _chunks_del_articulo()
    parent = next((c for c in chunks if c.get("chunk_type") == "parent"), None)

    assert parent is not None

    assert "Constancia de inscripción" in parent["content"]
    assert "Declaración jurada" in parent["content"]
    # El parent sí declara los cuatro párrafos: es el chunk de contexto completo.
    assert _para_ids(parent) == {"para_11", "para_12", "para_13", "para_14"}
