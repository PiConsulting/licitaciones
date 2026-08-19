"""CHK-13: la tabla de contenidos se indexaba como si fuera contenido.

En el PET de Bancor el índice del pliego produjo tres chunks -- 2.011, 94 y 290
caracteres -- de la forma `col_1: 3.1.2. Virtualización / col_2: 12`. Uno de
ellos dice literalmente `col_1: 5.3. Garantía y servicio post-venta`.

El problema no es el volumen: es que el índice NOMBRA las secciones sin
CONTENERLAS. Una consulta sobre garantías lo recupera con buen score porque
comparte todas las palabras, y después no prueba nada. Compite con la evidencia
real en las ocho categorías, y en atribución produce una cita que remite a un
renglón de un índice.

El riesgo del fix es el inverso y es peor: descartar contenido real. Por eso la
mitad de estos tests son guardas sobre tablas y listas que se le parecen y
tienen que sobrevivir.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import (
    _drop_index_listings,
    _index_entries,
    _looks_like_index_listing,
    create_chunks,
)


def _fila(contenido: str, page: int = 2, table_id: str = "T1", row_order: int = 0) -> dict[str, Any]:
    return {
        "content": contenido,
        "page_number": page,
        "source_order": 100,
        "row_order": row_order,
        "block_type": "table",
        "table_ref": {"table_id": table_id},
    }


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


# El índice real del PET de Bancor, tal como salió en el chunk 3.
INDICE_BANCOR = [
    "Índice",
    "1. Generalidades\t4",
    "1.1. Objetivo\t4",
    "1.2. Alcance\t4",
    "1.3. Arquitectura objetivo y modelo de despliegue\t5",
    "1.4. Confidencialidad\t5",
    "1.5. Consideraciones generales\t5",
    "1.6. Visita técnica obligatoria\t5",
    "1.7. Plazo de entrega\t6",
    "2. Composición de la solución a cotizar\t7",
    "3. Especificaciones técnicas\t8",
    "3.1. Plataforma de software de nube privada\t8",
    "3.1.1. Definición de la solución\t8",
    "3.1.2. Virtualización y gestión de cómputo\t12",
    "3.2. Solución integral de resguardo de información (backup)\t19",
    "5.2. Niveles de servicio (SLA) por criticidad\t39",
]


def _tabla_indice(page: int = 2, table_id: str = "T1") -> list[dict[str, Any]]:
    filas = []
    for orden, entrada in enumerate(INDICE_BANCOR):
        partes = entrada.split("\t")
        contenido = f"col_1: {partes[0]}"
        if len(partes) > 1:
            contenido += f"\ncol_2: {partes[1]}"
        filas.append(_fila(contenido, page=page, table_id=table_id, row_order=orden))
    return filas


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_el_indice_en_forma_de_tabla_se_descarta() -> None:
    bloques = _tabla_indice() + [_parrafo("El presente Pliego tiene por finalidad establecer.", 4, 0)]

    resultado = _drop_index_listings(bloques + [_parrafo("Texto de la página 45.", 45, 0)])

    contenidos = [b["content"] for b in resultado]
    assert not any("3.1.2. Virtualización" in c for c in contenidos)
    assert not any("5.2. Niveles de servicio" in c for c in contenidos)
    assert any("El presente Pliego" in c for c in contenidos), "se llevó puesto contenido real"


def test_la_segunda_mitad_del_indice_tambien_se_descarta() -> None:
    """El índice de Bancor se parte en dos chunks por tamaño y la segunda mitad
    queda con UNA fila: `5.3. Garantía y servicio post-venta / 40`. Sola no
    parece un índice -- por eso se evalúa la tabla entera, no cada fila."""
    filas = _tabla_indice()
    filas.append(_fila("col_1: 5.3. Garantía y servicio post-venta\ncol_2: 40", row_order=99))

    resultado = _drop_index_listings(filas + [_parrafo("Texto de la página 45.", 45, 0)])

    assert not any("Garantía y servicio post-venta" in b["content"] for b in resultado)


def test_el_indice_que_sigue_en_parrafos_tambien_se_descarta() -> None:
    """En la página 3 el índice deja de venir como tabla: cada entrada es un
    párrafo y el número de página a veces viene como su propio bloque."""
    bloques = [
        _parrafo("BANCOR", 3, 0),
        _parrafo("5.4. Penalidades por incumplimiento", 3, 1),
        _parrafo("41", 3, 2),
        _parrafo("6\\. Calidad y antecedentes de los oferentes\n42", 3, 3),
        _parrafo("7\\. Metodología de evaluación y adjudicación\n43", 3, 4),
        _parrafo("7.1. Etapa 1 - Filtro técnico excluyente (Cumple / No cumple)", 3, 5),
        _parrafo("43", 3, 6),
        _parrafo("7.2. Etapa 2 - Comparación económica\n44", 3, 7),
        _parrafo("8\\. Prohibiciones", 3, 8),
        _parrafo("44", 3, 9),
        _parrafo("9\\. Anexos\n45", 3, 10),
        _parrafo("Texto real de la página 45.", 45, 0),
    ]

    resultado = _drop_index_listings(bloques)

    assert not any("Penalidades por incumplimiento" in b["content"] for b in resultado)
    assert any("Texto real" in b["content"] for b in resultado)


def test_el_pipeline_completo_no_produce_chunks_de_indice() -> None:
    bloques = _tabla_indice() + [
        {"heading_level": 1, "content": "1. Generalidades", "page_number": 4, "source_order": 0},
        _parrafo(
            "El presente Pliego de Especificaciones Técnicas tiene por finalidad establecer las "
            "condiciones técnicas para la adquisición de una solución integral de Nube Privada.",
            4,
            1,
        ),
        _parrafo("Texto de la última página del pliego.", 45, 0),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert chunks
    for chunk in chunks:
        assert "3.1.2. Virtualización" not in chunk["content"]
        assert "col_2: 39" not in chunk["content"]
    assert any("El presente Pliego" in c["content"] for c in chunks)


# ---------------------------------------------------------------------------
# Guardas: lo que NO se puede descartar
# ---------------------------------------------------------------------------


def test_un_cronograma_escalonado_no_es_un_indice() -> None:
    """Cumple "lista creciente de números": es el falso positivo que más caro
    saldría, porque son plazos y hay que extraerlos."""
    bloques = [
        _parrafo("Etapa 1 - Relevamiento: 30 días corridos desde la orden de compra. 30", 12, 0),
        _parrafo("Etapa 2 - Diseño de la solución y plan de trabajos. 60", 12, 1),
        _parrafo("Etapa 3 - Implementación e integración en ambos sitios. 90", 12, 2),
        _parrafo("Etapa 4 - Migración de las cargas productivas del Banco. 120", 12, 3),
        _parrafo("Etapa 5 - Capacitación y cierre formal del proyecto. 150", 12, 4),
        _parrafo("Texto de la última página.", 200, 0),
    ]

    assert len(_drop_index_listings(bloques)) == len(bloques)


def test_una_planilla_de_cotizacion_no_es_un_indice() -> None:
    """La tabla de ítems del chunk 14 de Bancor: la última columna es `Cant.`,
    casi siempre 1."""
    filas = [
        _fila("col_1: Ítem\ncol_2: Descripción\ncol_3: Cant.", page=7, row_order=0),
        _fila("col_1: 1\ncol_2: Plataforma de software de Nube Privada.\ncol_3: 1", page=7, row_order=1),
        _fila("col_1: 2\ncol_2: Conectividad de red de centro de datos.\ncol_3: 1", page=7, row_order=2),
        _fila("col_1: 3\ncol_2: Solución integral de resguardo de información.\ncol_3: 1", page=7, row_order=3),
        _fila("col_1: 4\ncol_2: Equipamiento de cómputo para ambos sitios.\ncol_3: 1", page=7, row_order=4),
        _fila("col_1: 5\ncol_2: Servicios profesionales llave en mano.\ncol_3: 1", page=7, row_order=5),
    ]
    bloques = filas + [_parrafo("Texto de la última página.", 45, 0)]

    assert len(_drop_index_listings(bloques)) == len(bloques)


def test_una_lista_de_incisos_numerados_no_es_un_indice() -> None:
    """Empieza con numeración de sección, pero no termina en número de página."""
    bloques = [
        _parrafo("1.1. El oferente deberá acreditar inscripción en el registro.", 9, i)
        for i in range(6)
    ] + [_parrafo("Texto de la última página.", 45, 0)]

    assert len(_drop_index_listings(bloques)) == len(bloques)


def test_una_tabla_de_especificaciones_tecnicas_no_es_un_indice() -> None:
    """Números crecientes y acotados, pero los títulos no son secciones."""
    filas = [
        _fila("col_1: Memoria RAM por nodo (GB)\ncol_2: 512", page=32, row_order=0),
        _fila("col_1: Núcleos físicos por nodo\ncol_2: 32", page=32, row_order=1),
        _fila("col_1: Discos SSD por nodo\ncol_2: 8", page=32, row_order=2),
        _fila("col_1: Interfaces de red 25 Gb\ncol_2: 4", page=32, row_order=3),
        _fila("col_1: Nodos por sitio\ncol_2: 6", page=32, row_order=4),
    ]
    bloques = filas + [_parrafo("Texto de la última página.", 45, 0)]

    assert len(_drop_index_listings(bloques)) == len(bloques)


def test_un_indice_que_apunta_fuera_del_documento_no_se_descarta() -> None:
    """Si los números superan la cantidad de páginas, no son páginas de este
    pliego: no hay razón para creer que es un índice."""
    filas = _tabla_indice()
    bloques = filas + [_parrafo("Documento de 3 páginas.", 3, 0)]

    assert len(_drop_index_listings(bloques)) == len(bloques)


def test_un_grupo_chico_no_se_descarta() -> None:
    """Cuatro entradas no alcanzan para afirmar que es un índice."""
    filas = [
        _fila(f"col_1: {n}. Sección de prueba del pliego\ncol_2: {n + 3}", page=2, row_order=n)
        for n in range(1, 5)
    ]
    bloques = filas + [_parrafo("Texto de la última página.", 45, 0)]

    assert len(_drop_index_listings(bloques)) == len(bloques)


# ---------------------------------------------------------------------------
# Las piezas
# ---------------------------------------------------------------------------


def test_el_numero_suelto_se_pega_a_la_entrada_anterior() -> None:
    entradas = _index_entries(
        [
            _parrafo("5.4. Penalidades por incumplimiento", 3, 0),
            _parrafo("41", 3, 1),
            _parrafo("6\\. Calidad y antecedentes de los oferentes", 3, 2),
            _parrafo("42", 3, 3),
        ]
    )

    assert entradas == [
        "5.4. Penalidades por incumplimiento 41",
        "6. Calidad y antecedentes de los oferentes 42",
    ]


def test_los_prefijos_de_columna_no_cuentan_como_texto() -> None:
    entradas = _index_entries([_fila("col_1: 1.1. Objetivo\ncol_2: 4")])

    assert entradas == ["1.1. Objetivo 4"]


def test_el_numero_de_seccion_exige_el_punto_final() -> None:
    """Sin el punto, la columna `Ítem` de una planilla ("1 Plataforma...")
    contaría como número de sección."""
    entradas = ["1 Plataforma de software de Nube Privada 1"] * 6

    assert not _looks_like_index_listing(entradas, pagina=7, paginas_totales=45)


def test_un_table_ref_que_no_es_dict_no_rompe() -> None:
    """Varios llamadores pasan `table_ref` como string pelado en vez de
    `{"table_id": ...}`. Asumir la forma reventaba con `'str' object has no
    attribute 'get'` -- y dentro de `create_chunks` ese error se lo habría
    comido el `except Exception` ancho (CHK-10), dejando un documento sin
    tablas y sin ninguna señal."""
    bloques = [
        {
            "content": "Renglón de tabla",
            "page_number": 1,
            "source_order": 1,
            "block_type": "table",
            "table_ref": "table-1",
        },
        _parrafo("Texto de la última página.", 45, 0),
    ]

    assert len(_drop_index_listings(bloques)) == len(bloques)
