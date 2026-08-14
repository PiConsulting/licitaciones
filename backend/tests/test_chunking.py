from __future__ import annotations

from extraction.chunking import _detect_incisos, _detect_repeated_heading_boilerplate, create_chunks


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


# ---------------------------------------------------------------------------
# US-3.1: Parent/child chunking para articulos largos con incisos
# ---------------------------------------------------------------------------

_ARTICULO_6_CON_INCISOS = (
    "Los oferentes deberan presentar la totalidad de la documentacion enumerada a "
    "continuacion, en sobre cerrado, dentro del plazo establecido en el presente "
    "pliego de bases y condiciones, bajo apercibimiento de exclusion automatica del "
    "proceso licitatorio sin posibilidad de subsanacion posterior alguna.\n\n"
    "a) Documentacion de personeria juridica del oferente, incluyendo estatuto social "
    "vigente, actas de designacion de autoridades y poder suficiente para obligar a "
    "la sociedad en los terminos de la presente contratacion.\n\n"
    "b) Propuesta economica conforme al modelo adjunto como Anexo II, indicando "
    "precio unitario y total, discriminando impuestos, con vigencia minima de "
    "sesenta dias corridos desde la apertura.\n\n"
    "c) Propuesta tecnica incluyendo cronograma detallado de tareas, metodologia de "
    "trabajo, recursos humanos afectados y antecedentes de trabajos similares "
    "realizados en los ultimos cinco anios.\n\n"
    "d) Declaracion de conformacion de Union Transitoria de Empresas, si "
    "correspondiere, con firma certificada de todos los integrantes ante escribano "
    "publico.\n\n"
    "e) Declaraciones juradas de no encontrarse alcanzado por ninguna causal de "
    "inhabilidad para contratar con el estado provincial ni nacional."
)


def test_detect_incisos_reconoce_estructura_a_b_c() -> None:
    incisos = _detect_incisos(_ARTICULO_6_CON_INCISOS)

    assert len(incisos) == 5
    assert [inciso["label"] for inciso in incisos] == ["a)", "b)", "c)", "d)", "e)"]
    assert incisos[2]["text"].startswith("c) Propuesta tecnica")


def test_detect_incisos_requiere_al_menos_dos() -> None:
    """Un solo 'a)' suelto (ej: una referencia dentro de una oracion) no alcanza
    para justificar la subdivision -- necesita estructura real de lista."""
    content = "El oferente debera cumplir con lo indicado en a) del presente articulo."

    assert _detect_incisos(content) == []


def test_detect_incisos_aborta_si_algun_inciso_es_demasiado_corto() -> None:
    """Mas seguro no partir que partir mal: si el regex matchea pero un
    'inciso' queda con contenido casi vacio, probablemente sea un falso
    positivo (ej: una fecha 'a) 15/05/2024' mal interpretada) -- se aborta
    toda la subdivision, no solo ese inciso."""
    content = "a) si\n\nb) Documentacion completa de personeria juridica del oferente segun corresponda."

    assert _detect_incisos(content) == []


def test_create_chunks_articulo_largo_con_incisos_genera_parent_y_children() -> None:
    blocks = [
        _heading("Articulo 6: DOCUMENTACION A PRESENTAR", 1, 1, 0),
        _para(_ARTICULO_6_CON_INCISOS, 1, 1),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    parents = [c for c in chunks if c["chunk_type"] == "parent"]
    children = [c for c in chunks if c["chunk_type"] == "child"]

    assert len(parents) == 1
    assert len(children) == 5

    parent = parents[0]
    assert parent["content"] == _ARTICULO_6_CON_INCISOS
    assert parent["child_chunk_indices"] == [c["chunk_index"] for c in children]

    for child in children:
        assert child["parent_chunk_index"] == parent["chunk_index"]
        assert child["document_id"] == "doc-1"
        assert child["content"] in _ARTICULO_6_CON_INCISOS

    # Los chunk_index son unicos y consecutivos (parent + 5 children == 6 slots)
    all_indices = [c["chunk_index"] for c in chunks]
    assert sorted(all_indices) == list(range(len(all_indices)))
    assert len(set(all_indices)) == len(all_indices)


def test_create_chunks_no_subdivide_articulo_corto_aunque_tenga_incisos() -> None:
    """Por debajo del umbral de caracteres, no vale la pena la subdivision --
    el chunk queda 'normal' aunque el regex detecte incisos."""
    short_content = "a) Personeria juridica.\n\nb) Propuesta economica."
    blocks = [
        _heading("Articulo 2: Requisitos", 1, 1, 0),
        _para(short_content, 1, 1),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    paragraph_chunks = _paragraph_chunks(chunks)

    assert len(paragraph_chunks) == 1
    assert paragraph_chunks[0]["chunk_type"] == "normal"
    assert paragraph_chunks[0]["content"] == short_content


def test_create_chunks_siguiente_bloque_no_colisiona_con_indices_de_children() -> None:
    """Los indices consumidos por parent+children no deben pisar el indice
    del siguiente bloque del documento (acá una tabla, que nunca se mergea
    con el párrafo anterior por ser de otro block_type)."""
    blocks = [
        _para(_ARTICULO_6_CON_INCISOS, 1, 0),
        {
            "page_number": 1,
            "block_type": "table",
            "content": "Renglon 1 | Renglon 2",
            "source_order": 1,
            "table_ref": "table-1",
        },
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    all_indices = [c["chunk_index"] for c in chunks]
    assert sorted(all_indices) == list(range(len(all_indices)))
    assert len(set(all_indices)) == len(all_indices)

    tabla_chunk = next(c for c in chunks if c["block_type"] == "table")
    assert tabla_chunk["chunk_type"] == "normal"
    assert tabla_chunk["chunk_index"] == max(all_indices)


# ---------------------------------------------------------------------------
# REGRESIÓN CHK-01 (auditoría 2026-08-13): tamaño y duplicación de chunks.
#
# El carry de overlap arrastraba SIEMPRE al menos un párrafo entero (por el
# `carried and` de la condición) y después appendeaba el párrafo que había
# disparado el flush sin revalidar el límite. Con los defaults
# (chunk_size=700, overlap=120) y párrafos de 690 tokens salían chunks de
# 1380 tokens, y el primer chunk quedaba contenido ÍNTEGRAMENTE dentro del
# segundo: 2070 tokens de entrada -> 3450 emitidos.
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 700
_OVERLAP = 120


def _paragraphs_of(count: int, tokens_each: int) -> list[str]:
    """Párrafos con tokens únicos, para poder detectar duplicación exacta."""
    return [" ".join(f"p{index}w{i}" for i in range(tokens_each)) for index in range(count)]


def _split(paragraphs: list[str], chunk_size: int = _CHUNK_SIZE, overlap: int = _OVERLAP) -> list[str]:
    from extraction.chunking import _split_block_into_chunks

    return _split_block_into_chunks("\n\n".join(paragraphs), chunk_size, overlap)


def test_ningun_chunk_supera_el_chunk_size_configurado() -> None:
    """El caso que reprodujo la auditoría: párrafos apenas por debajo del
    límite producían chunks del doble."""
    chunks = _split(_paragraphs_of(3, 690))

    oversized = [len(chunk.split()) for chunk in chunks if len(chunk.split()) > _CHUNK_SIZE]
    assert not oversized, f"chunks que exceden chunk_size={_CHUNK_SIZE}: {oversized}"


def test_ningun_chunk_esta_contenido_dentro_de_otro() -> None:
    """Duplicación total: el chunk 0 entero adentro del chunk 1."""
    chunks = [" ".join(chunk.split()) for chunk in _split(_paragraphs_of(3, 690))]

    contained = [
        (i, j)
        for i, a in enumerate(chunks)
        for j, b in enumerate(chunks)
        if i != j and a in b
    ]
    assert not contained, f"chunks contenidos dentro de otro: {contained}"


def test_no_infla_el_volumen_indexado_en_el_caso_tipico() -> None:
    """8 párrafos de 200 tokens: antes emitía 2200 tokens para 1600 de entrada."""
    paragraphs = _paragraphs_of(8, 200)
    chunks = _split(paragraphs)

    tokens_in = sum(len(p.split()) for p in paragraphs)
    tokens_out = sum(len(c.split()) for c in chunks)

    # Se tolera algo de solapamiento legítimo, pero no un tercio más de índice.
    assert tokens_out <= tokens_in * 1.15, (
        f"redundancia de {100 * (tokens_out - tokens_in) / tokens_in:.0f}% "
        f"({tokens_in} tokens de entrada -> {tokens_out} emitidos)"
    )


def test_no_se_pierde_ningun_parrafo() -> None:
    """La corrección del overlap no puede costar contenido."""
    paragraphs = _paragraphs_of(8, 200)
    joined = " ".join(" ".join(chunk.split()) for chunk in _split(paragraphs))

    for index, paragraph in enumerate(paragraphs):
        assert " ".join(paragraph.split()) in joined, f"se perdió el párrafo {index}"


def test_parrafos_chicos_conservan_solapamiento() -> None:
    """Cuando el párrafo entra en el presupuesto de overlap, se sigue
    arrastrando: la corrección no desactiva el overlap, sólo lo acota."""
    paragraphs = _paragraphs_of(20, 60)
    chunks = _split(paragraphs)

    assert len(chunks) >= 2
    tokens_in = sum(len(p.split()) for p in paragraphs)
    tokens_out = sum(len(c.split()) for c in chunks)
    assert tokens_out > tokens_in, "con párrafos chicos debe seguir habiendo solapamiento"

    # Y el solapamiento no puede pasarse del presupuesto configurado.
    assert tokens_out - tokens_in <= _OVERLAP * (len(chunks) - 1)


def test_parrafo_mas_grande_que_chunk_size_se_parte_con_overlap_real() -> None:
    """Único caso donde se corta texto por el medio: ahí el overlap SÍ importa,
    porque un hecho puede caer sobre el borde."""
    chunks = _split([" ".join(f"g{i}" for i in range(1800))])

    assert len(chunks) >= 3
    assert all(len(chunk.split()) <= _CHUNK_SIZE for chunk in chunks)

    # Chunks consecutivos comparten tokens (eso es el overlap).
    first_tokens = set(chunks[0].split())
    second_tokens = set(chunks[1].split())
    assert first_tokens & second_tokens, "debe haber solapamiento al partir un párrafo"


def test_invariantes_se_sostienen_en_un_barrido_de_tamanos() -> None:
    """Barrido: ningún chunk excede el límite ni queda contenido en otro,
    para cualquier combinación razonable de tamaños de párrafo."""
    for tokens_each in (30, 120, 200, 349, 350, 351, 500, 690, 699):
        paragraphs = _paragraphs_of(6, tokens_each)
        chunks = [" ".join(chunk.split()) for chunk in _split(paragraphs)]

        oversized = [len(c.split()) for c in chunks if len(c.split()) > _CHUNK_SIZE]
        assert not oversized, f"tokens_each={tokens_each}: chunks sobredimensionados {oversized}"

        contained = [(i, j) for i, a in enumerate(chunks) for j, b in enumerate(chunks) if i != j and a in b]
        assert not contained, f"tokens_each={tokens_each}: chunks duplicados {contained}"


# ---------------------------------------------------------------------------
# REGRESIÓN CHK-04 (auditoría 2026-08-13): encabezados sin cuerpo propio.
#
# `_to_intermediate_blocks` fabrica un bloque "puro-encabezado" para cada título
# que no recibe párrafo propio -- toda la maquinaria de `heading_has_body`
# existe para eso, y su docstring dice "igual se conserva como su propio bloque
# puro-encabezado, para no perderlo". Pero `create_chunks` ponía `body = ""` y
# `content_pieces = []`, así que NO emitía ningún chunk. Código muerto con
# pérdida de información: el comentario decía lo contrario de lo que hacía.
# ---------------------------------------------------------------------------


def test_la_portada_de_un_anexo_llega_al_indice() -> None:
    """El caso concreto: "ANEXO III - DECLARACIÓN JURADA..." es un título solo,
    con el formulario en la página siguiente bajo otro encabezado. Sin chunk,
    ese anexo no existe para el retrieval y el sistema informa que el pliego
    no lo pide."""
    blocks = [
        _heading("ANEXO III - DECLARACIÓN JURADA DE APTITUD PARA CONTRATAR", 2, 7, 0),
        _heading("ANEXO IV - PLANILLA DE COTIZACIÓN", 2, 8, 1),
        _para("Complete la planilla con el precio unitario de cada ítem.", 8, 2),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    anexo_iii = next(
        (c for c in chunks if "DECLARACIÓN JURADA" in c["section_path"]), None
    )
    assert anexo_iii is not None, "el anexo desapareció del índice"
    assert "DECLARACIÓN JURADA DE APTITUD" in anexo_iii["content"], (
        "el chunk existe pero sin contenido: no es recuperable ni por BM25 ni por el vector"
    )


def test_el_anexo_sin_cuerpo_queda_clasificado_como_anexo() -> None:
    blocks = [
        _heading("ANEXO III - DECLARACIÓN JURADA DE APTITUD PARA CONTRATAR", 2, 7, 0),
        _heading("ANEXO IV - PLANILLA DE COTIZACIÓN", 2, 8, 1),
        _para("Complete la planilla con el precio unitario de cada ítem.", 8, 2),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    anexo_iii = next(c for c in chunks if "DECLARACIÓN JURADA" in c["section_path"])

    assert anexo_iii["primary_category"] == "anexos_obligatorios"


def test_el_encabezado_sin_cuerpo_no_duplica_el_de_su_seccion_con_cuerpo() -> None:
    """Un encabezado que SÍ recibe cuerpo no debe generar además un chunk con
    su propio título: eso duplicaría contenido en el índice."""
    blocks = [
        _heading("ARTÍCULO 8: MANTENIMIENTO DE OFERTA", 2, 4, 0),
        _para("Los oferentes deberán mantener el precio cotizado sesenta (60) días.", 4, 1),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    assert len(chunks) == 1
    assert chunks[0]["content"].startswith("Los oferentes")


def test_el_chunk_de_encabezado_conserva_su_ruta_de_seccion() -> None:
    blocks = [
        _heading("PLIEGO DE CONDICIONES PARTICULARES", 1, 1, 0),
        _heading("ANEXO I", 2, 1, 1),
        _heading("ANEXO II", 2, 1, 2),
        _para("Contenido del anexo dos.", 1, 3),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    anexo_uno = next(c for c in chunks if c["content"] == "ANEXO I")

    assert anexo_uno["section_path"] == "PLIEGO DE CONDICIONES PARTICULARES > ANEXO I"
    assert anexo_uno["title"] == "ANEXO I"


def test_un_ancestro_con_subsecciones_no_genera_chunk_de_ruido() -> None:
    """Destapado al arreglar CHK-04: sólo se marcaba como "con cuerpo" el
    encabezado más interno, así que cada ancestro de la jerarquía terminaba
    fabricando un bloque puro-encabezado. Mientras esos bloques no generaban
    chunks el error era invisible."""
    blocks = [
        _heading("PLIEGO DE CONDICIONES PARTICULARES", 1, 1, 0),
        _heading("CAPÍTULO II - DE LAS OFERTAS", 2, 1, 1),
        _heading("ARTÍCULO 8: MANTENIMIENTO DE OFERTA", 3, 1, 2),
        _para("Los oferentes deberán mantener el precio cotizado sesenta (60) días.", 1, 3),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    assert len(chunks) == 1, (
        "cada ancestro metió un chunk con sólo su título: "
        f"{[c['content'][:40] for c in chunks]}"
    )
    assert chunks[0]["content"].startswith("Los oferentes")
    assert chunks[0]["section_path"] == (
        "PLIEGO DE CONDICIONES PARTICULARES > CAPÍTULO II - DE LAS OFERTAS > "
        "ARTÍCULO 8: MANTENIMIENTO DE OFERTA"
    )


def test_solo_el_encabezado_sin_ningun_descendiente_genera_chunk_propio() -> None:
    """La distinción que importa: un ancestro está representado por sus
    descendientes; una portada de anexo no está representada por nada."""
    blocks = [
        _heading("PLIEGO", 1, 1, 0),
        _heading("ANEXO I", 2, 1, 1),          # sin nada colgando -> sí
        _heading("ANEXO II", 2, 1, 2),         # tiene cuerpo -> no
        _para("Contenido del anexo dos.", 1, 3),
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    solo_titulo = [c for c in chunks if c["content"] == "ANEXO I"]

    assert len(solo_titulo) == 1
    assert not [c for c in chunks if c["content"] == "PLIEGO"]
    assert not [c for c in chunks if c["content"] == "ANEXO II"]
