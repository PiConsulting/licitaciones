from __future__ import annotations

from extraction.chunking import _detect_repeated_heading_boilerplate, create_chunks


def _heading(text: str, level: int, page: int, order: int) -> dict:
    return {
        "page_number": page,
        "block_type": "paragraph",
        "content": text,
        "source_order": order,
        "table_ref": None,
        "heading_level": level,
    }


def _para(text: str, page: int, order: int) -> dict:
    return {
        "page_number": page,
        "block_type": "paragraph",
        "content": text,
        "source_order": order,
        "table_ref": None,
    }


def _paragraph_chunks(chunks: list[dict]) -> list[dict]:
    return [chunk for chunk in chunks if chunk["block_type"] == "paragraph" and chunk["content"]]


def test_hermanos_sin_capitulo_envolvente() -> None:
    """Tres 'Artículo N' consecutivos, todos al mismo nivel (como los devuelve
    Document Intelligence en markdown) -- ninguno debe anidarse dentro del
    anterior."""
    blocks = [
        _heading("Artículo 1: OBJETO", 2, 1, 0),
        _para("Contenido del articulo uno.", 1, 1),
        _heading("Artículo 2: OTRA COSA", 2, 1, 2),
        _para("Contenido del articulo dos.", 1, 3),
        _heading("Artículo 3: OTRA MAS", 2, 1, 4),
        _para("Contenido del articulo tres.", 1, 5),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    paths = {chunk["section_path"] for chunk in body_chunks}
    assert paths == {"Artículo 1: OBJETO", "Artículo 2: OTRA COSA", "Artículo 3: OTRA MAS"}
    assert all(">" not in path for path in paths)


def test_numeracion_jerarquica_con_hermanos() -> None:
    blocks = [
        _heading("1. DISPOSICIONES", 2, 1, 0),
        _para("Contenido de disposiciones generales.", 1, 1),
        _heading("1.1. Ambito", 3, 1, 2),
        _para("Contenido de ambito.", 1, 3),
        _heading("1.2. Normativa", 3, 1, 4),
        _para("Contenido de normativa.", 1, 5),
        _heading("2. CONVOCATORIA", 2, 1, 6),
        _para("Contenido de convocatoria.", 1, 7),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    normativa = next(c for c in body_chunks if "Contenido de normativa" in c["content"])
    assert normativa["section_path"] == "1. DISPOSICIONES > 1.2. Normativa"

    convocatoria = next(c for c in body_chunks if "Contenido de convocatoria" in c["content"])
    assert convocatoria["section_path"] == "2. CONVOCATORIA"


def test_jerarquia_real_de_3_niveles_se_preserva() -> None:
    blocks = [
        _heading("3. OFERTAS", 2, 1, 0),
        _para("Contenido de ofertas generales.", 1, 1),
        _heading("3.1. De los Oferentes", 3, 1, 2),
        _para("Contenido de oferentes.", 1, 3),
        _heading("3.1.2. Capacidad tecnica", 4, 1, 4),
        _para("Contenido de capacidad tecnica y financiera.", 1, 5),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    capacidad = next(c for c in body_chunks if "Contenido de capacidad tecnica" in c["content"])
    assert capacidad["section_path"] == "3. OFERTAS > 3.1. De los Oferentes > 3.1.2. Capacidad tecnica"


def test_heading_sin_parrafo_propio_se_conserva_como_chunk() -> None:
    """Portada de un anexo: un encabezado que nunca recibe cuerpo antes del
    siguiente encabezado de igual o menor nivel no debe perderse."""
    blocks = [
        _heading("ANEXO I", 2, 1, 0),
        _heading("ANEXO II", 2, 2, 1),
        _para("Contenido del anexo dos.", 2, 2),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    anexo_uno = next(c for c in body_chunks if c["section_path"] == "ANEXO I")
    assert anexo_uno["content"] == "ANEXO I"

    anexo_dos = next(c for c in body_chunks if "Contenido del anexo dos" in c["content"])
    assert anexo_dos["section_path"] == "ANEXO II"


def test_no_regresion_caso_feliz_capitulo_articulo() -> None:
    blocks = [
        _heading("Capítulo I Disposiciones Generales", 2, 1, 0),
        _para("Contenido general del capitulo uno.", 1, 1),
        _heading("Artículo 1: Objeto", 3, 1, 2),
        _para("Contenido del articulo uno.", 1, 3),
        _heading("Capítulo II Otras Disposiciones", 2, 1, 4),
        _para("Contenido general del capitulo dos.", 1, 5),
        _heading("Artículo 2: Otro Objeto", 3, 1, 6),
        _para("Contenido del articulo dos.", 1, 7),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    articulo_1 = next(c for c in body_chunks if "Contenido del articulo uno" in c["content"])
    assert articulo_1["section_path"] == "Capítulo I Disposiciones Generales > Artículo 1: Objeto"

    articulo_2 = next(c for c in body_chunks if "Contenido del articulo dos" in c["content"])
    assert articulo_2["section_path"] == "Capítulo II Otras Disposiciones > Artículo 2: Otro Objeto"


def test_encabezado_repetido_en_todas_las_paginas_se_filtra() -> None:
    """El caso real de Rosario: Document Intelligence marca el membrete del
    organismo como encabezado de nivel 1 en cada pagina -- si no se filtra,
    queda como ancestro de TODOS los chunks del documento."""
    blocks: list[dict] = []
    order = 0
    for page in range(1, 6):
        blocks.append(_heading("Municipalidad de Rosario", 1, page, order))
        order += 1
        blocks.append(_para(f"Contenido real de la pagina {page}.", page, order))
        order += 1

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    assert not any("municipalidad de rosario" in chunk["content"].lower() for chunk in chunks)
    for page in range(1, 6):
        assert any(f"Contenido real de la pagina {page}." in chunk["content"] for chunk in chunks)


def test_boilerplate_no_filtra_encabezado_corto_no_repetido() -> None:
    blocks = [
        _heading("Bienvenido", 1, 1, 0),
        _para("Contenido pagina uno con informacion relevante del pliego.", 1, 1),
        _para("Contenido pagina dos con mas informacion relevante del pliego.", 2, 2),
    ]

    boilerplate = _detect_repeated_heading_boilerplate(blocks)

    assert boilerplate == set()


def test_boilerplate_no_aplica_en_documentos_cortos() -> None:
    blocks = [
        _heading("Membrete Corto", 1, 1, 0),
        _para("Contenido especifico de pagina uno.", 1, 1),
        _heading("Membrete Corto", 1, 2, 2),
        _para("Contenido especifico de pagina dos.", 2, 3),
    ]

    boilerplate = _detect_repeated_heading_boilerplate(blocks)

    assert boilerplate == set()
