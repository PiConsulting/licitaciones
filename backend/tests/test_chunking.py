from __future__ import annotations

from extraction.chunking import _detect_repeated_boilerplate_lines, create_chunks


def _paragraph_chunks(chunks: list[dict]) -> list[dict]:
    return [chunk for chunk in chunks if chunk["block_type"] == "paragraph"]


def test_hermanos_sin_capitulo_envolvente() -> None:
    pages = [
        {
            "page_number": 1,
            "content": (
                "Artículo 1: OBJETO\n"
                "Contenido del articulo uno.\n\n"
                "Artículo 2: OTRA COSA\n"
                "Contenido del articulo dos.\n\n"
                "Artículo 3: OTRA MAS\n"
                "Contenido del articulo tres.\n"
            ),
        }
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    paths = {chunk["section_path"] for chunk in body_chunks}
    assert paths == {"Artículo 1: OBJETO", "Artículo 2: OTRA COSA", "Artículo 3: OTRA MAS"}
    assert all(">" not in path for path in paths)


def test_numeracion_jerarquica_con_hermanos() -> None:
    pages = [
        {
            "page_number": 1,
            "content": (
                "1. DISPOSICIONES\n"
                "Contenido de disposiciones generales.\n\n"
                "1.1. Ambito\n"
                "Contenido de ambito.\n\n"
                "1.2. Normativa\n"
                "Contenido de normativa.\n\n"
                "2. CONVOCATORIA\n"
                "Contenido de convocatoria.\n"
            ),
        }
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    normativa = next(c for c in body_chunks if "Contenido de normativa" in c["content"])
    assert normativa["section_path"] == "1. DISPOSICIONES > 1.2. Normativa"

    convocatoria = next(c for c in body_chunks if "Contenido de convocatoria" in c["content"])
    assert convocatoria["section_path"] == "2. CONVOCATORIA"


def test_jerarquia_real_de_3_niveles_se_preserva() -> None:
    pages = [
        {
            "page_number": 1,
            "content": (
                "3. OFERTAS\n"
                "Contenido de ofertas generales.\n\n"
                "3.1. De los Oferentes\n"
                "Contenido de oferentes.\n\n"
                "3.1.2. Capacidad tecnica\n"
                "Contenido de capacidad tecnica y financiera.\n"
            ),
        }
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    capacidad = next(c for c in body_chunks if "Contenido de capacidad tecnica" in c["content"])
    assert capacidad["section_path"] == "3. OFERTAS > 3.1. De los Oferentes > 3.1.2. Capacidad tecnica"


def test_indice_no_genera_chunk_fantasma() -> None:
    toc_leader = "…" * 10
    pages = [
        {
            "page_number": 1,
            "content": (
                "ÍNDICE\n"
                f"4. Apertura Y Evaluación De Las Ofertas{toc_leader}10\n"
                f"10. Garantías{toc_leader}23\n"
            ),
        },
        {
            "page_number": 2,
            "content": (
                "4. APERTURA Y EVALUACIÓN DE LAS OFERTAS\n"
                "El acto de apertura de las ofertas se realizará en la fecha y hora "
                "indicadas en el pliego, ante los oferentes que deseen presenciarlo.\n"
            ),
        },
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    real_chunk = next(c for c in body_chunks if "APERTURA Y EVALUACIÓN" in c["section_path"])
    assert "El acto de apertura de las ofertas" in real_chunk["content"]

    assert not any("…" in chunk["content"] for chunk in chunks)
    assert not any(chunk["content"].strip() == "ÍNDICE" for chunk in chunks)


def test_no_regresion_caso_feliz_capitulo_articulo() -> None:
    pages = [
        {
            "page_number": 1,
            "content": (
                "Capítulo I Disposiciones Generales\n"
                "Contenido general del capitulo uno.\n\n"
                "Artículo 1: Objeto\n"
                "Contenido del articulo uno.\n\n"
                "Capítulo II Otras Disposiciones\n"
                "Contenido general del capitulo dos.\n\n"
                "Artículo 2: Otro Objeto\n"
                "Contenido del articulo dos.\n"
            ),
        }
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")
    body_chunks = _paragraph_chunks(chunks)

    articulo_1 = next(c for c in body_chunks if "Contenido del articulo uno" in c["content"])
    assert articulo_1["section_path"] == "Capítulo I Disposiciones Generales > Artículo 1: Objeto"

    articulo_2 = next(c for c in body_chunks if "Contenido del articulo dos" in c["content"])
    assert articulo_2["section_path"] == "Capítulo II Otras Disposiciones > Artículo 2: Otro Objeto"


def test_boilerplate_repetido_se_filtra_de_los_chunks() -> None:
    pages = [
        {
            "page_number": page_number,
            "content": f"Municipalidad de Rosario\nContenido real de la pagina {page_number}.",
        }
        for page_number in range(1, 6)
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1")

    assert not any("municipalidad de rosario" in chunk["content"].lower() for chunk in chunks)
    for page_number in range(1, 6):
        assert any(f"Contenido real de la pagina {page_number}." in chunk["content"] for chunk in chunks)


def test_boilerplate_no_filtra_contenido_corto_no_repetido() -> None:
    pages = [
        {"page_number": 1, "content": "Bienvenido.\nContenido pagina uno con informacion relevante del pliego."},
        {"page_number": 2, "content": "Contenido pagina dos con mas informacion relevante del pliego."},
    ]

    boilerplate = _detect_repeated_boilerplate_lines(pages)

    assert boilerplate == set()


def test_boilerplate_no_filtra_parrafos_largos_coincidentes_por_casualidad() -> None:
    long_sentence = (
        "Esta clausula estandar se repite en cada pagina del pliego porque asi lo "
        "exige la normativa vigente aplicable."
    )
    pages = [
        {"page_number": page_number, "content": f"{long_sentence}\nContenido especifico de la pagina {page_number}."}
        for page_number in range(1, 4)
    ]

    boilerplate = _detect_repeated_boilerplate_lines(pages)

    assert long_sentence.lower() not in boilerplate


def test_boilerplate_no_aplica_en_documentos_cortos() -> None:
    pages = [
        {"page_number": 1, "content": "Membrete Corto\nContenido especifico de pagina uno."},
        {"page_number": 2, "content": "Membrete Corto\nContenido especifico de pagina dos."},
    ]

    boilerplate = _detect_repeated_boilerplate_lines(pages)

    assert boilerplate == set()
