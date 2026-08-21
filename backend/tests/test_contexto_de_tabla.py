"""CHK-14: los chunks de tabla se llevaban pegado el párrafo anterior entero.

`_preceding_table_context` existe para que la frase que presenta una tabla ("La
evaluación se realizará según la siguiente tabla:") no quede separada de las
filas que explica. Devolvía `previous["content"]`.

El problema es CUÁNDO corre: para entonces el bloque previo ya pasó por
`_merge_intermediate_blocks` y es la fusión de todos los párrafos de su sección.
Así que la tabla no se llevaba la frase introductoria, se llevaba la sección
completa.

Medido en el PET de Bancor (análisis `f33897ba`): el contenido del chunk 15 --
953 caracteres-- aparece **entero** otra vez al principio del chunk 16, que es
su tabla. Lo mismo entre el 13 y el 14. Ese texto queda indexado dos veces,
ocupa lugar dos veces en el presupuesto de contexto del prompt, y hace que dos
chunks compitan entre sí en retrieval diciendo exactamente lo mismo.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import _introductory_tail, create_chunks

# El bloque 15 real de Bancor: un párrafo largo de definición y, al final, el
# encabezado de la tabla de licencias que viene inmediatamente después.
DEFINICION = (
    "Se busca una solución robusta y escalable para alojar soluciones de modernización de "
    "aplicaciones como así también los componentes para la administración centralizada de la "
    "infraestructura virtual de Nube Privada, optimizando el rendimiento y la seguridad del "
    "entorno descripto. La solución debe ser capaz de contar con almacenamiento distribuido y "
    "resiliente, garantizando la alta disponibilidad y redundancia para las cargas críticas."
)
ENCABEZADO_TABLA = (
    "PLATAFORMA INTEGRADA Y GESTIÓN CENTRALIZADA DE NUBE PRIVADA: BROADCOM "
    "VMWARE CLOUD FOUNDATION 9.1 O SUPERIOR"
)


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


def _fila(contenido: str, page: int, source_order: int, row_order: int) -> dict[str, Any]:
    return {
        "content": contenido,
        "page_number": page,
        "source_order": source_order,
        "row_order": row_order,
        "block_type": "table",
        "table_ref": {"table_id": "T1"},
    }


def _bloques_bancor() -> list[dict[str, Any]]:
    return [
        {"heading_level": 1, "content": "3.1.1. Definición de la solución", "page_number": 8, "source_order": 0},
        _parrafo(DEFINICION, 8, 1),
        _parrafo(ENCABEZADO_TABLA, 8, 2),
        _fila("col_1: Duracion\ncol_2: SKU\ncol_3: SUSCRIPCION REQUERIDA", 8, 3, 0),
        _fila("col_1: 36 meses\ncol_2: VCF-CLD-FND-A\ncol_3: Broadcom LICENCIAS VMWARE", 8, 3, 1),
        _fila("col_1: 12 meses\ncol_2: TAM-VCF\ncol_3: Servicios Technical Adoption Manager", 8, 3, 2),
    ]


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_la_tabla_no_se_lleva_el_parrafo_anterior_entero() -> None:
    chunks = create_chunks(_bloques_bancor(), document_id="doc", correlation_id="corr")
    tabla = next(c for c in chunks if c["block_type"] == "table")

    assert "Se busca una solución robusta" not in tabla["content"], (
        "la tabla se llevó pegada la definición completa de la sección"
    )


def test_la_tabla_conserva_la_frase_que_de_verdad_la_introduce() -> None:
    """No alcanza con recortar: el contexto tiene que seguir sirviendo. El
    último párrafo es justamente el encabezado de la tabla de licencias."""
    chunks = create_chunks(_bloques_bancor(), document_id="doc", correlation_id="corr")
    tabla = next(c for c in chunks if c["block_type"] == "table")

    assert "VMWARE CLOUD FOUNDATION 9.1 O SUPERIOR" in tabla["content"]
    assert "VCF-CLD-FND-A" in tabla["content"]


def test_el_texto_deja_de_estar_indexado_dos_veces() -> None:
    """La definición sigue existiendo en SU chunk. Lo que se elimina es la
    segunda copia."""
    chunks = create_chunks(_bloques_bancor(), document_id="doc", correlation_id="corr")

    copias = [c for c in chunks if "Se busca una solución robusta" in c["content"]]

    assert len(copias) == 1, f"la definición quedó en {len(copias)} chunks"


# ---------------------------------------------------------------------------
# Guardas: el contexto sigue existiendo cuando hace falta
# ---------------------------------------------------------------------------


def test_una_frase_introductoria_corta_se_conserva_completa() -> None:
    """Es la razón de ser de la función y no se puede perder."""
    bloques = [
        {"heading_level": 1, "content": "7. Evaluación", "page_number": 5, "source_order": 0},
        _parrafo("La evaluación se realizará según la siguiente tabla:", 5, 1),
        _fila("col_1: Precio\ncol_2: 60%", 5, 2, 0),
        _fila("col_1: Antecedentes\ncol_2: 40%", 5, 2, 1),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")
    tabla = next(c for c in chunks if c["block_type"] == "table")

    assert "La evaluación se realizará según la siguiente tabla:" in tabla["content"]


def test_una_tabla_sin_parrafo_previo_no_inventa_contexto() -> None:
    bloques = [
        {"heading_level": 1, "content": "7. Evaluación", "page_number": 5, "source_order": 0},
        _fila("col_1: Precio\ncol_2: 60%", 5, 1, 0),
        _fila("col_1: Antecedentes\ncol_2: 40%", 5, 1, 1),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")
    tabla = next(c for c in chunks if c["block_type"] == "table")

    assert "Precio" in tabla["content"]


# ---------------------------------------------------------------------------
# `_introductory_tail` directo
# ---------------------------------------------------------------------------


def test_de_un_bloque_fusionado_se_toma_el_ultimo_parrafo() -> None:
    assert _introductory_tail(f"{DEFINICION}\n\n{ENCABEZADO_TABLA}") == ENCABEZADO_TABLA


def test_un_parrafo_unico_y_corto_se_devuelve_tal_cual() -> None:
    frase = "La evaluación se realizará según la siguiente tabla:"

    assert _introductory_tail(frase) == frase


def test_un_ultimo_parrafo_larguisimo_se_recorta_por_el_final() -> None:
    """Lo que empalma con la tabla es el final del párrafo, no su principio."""
    largo = "Palabra de relleno. " * 40 + "Y esta es la frase que presenta la tabla:"

    cola = _introductory_tail(largo)

    assert cola is not None
    assert len(cola) <= 300
    assert cola.endswith("Y esta es la frase que presenta la tabla:")
    assert not cola.startswith(" ")


def test_un_bloque_vacio_no_produce_contexto() -> None:
    assert _introductory_tail("") is None
    assert _introductory_tail(None) is None
    assert _introductory_tail("   \n\n  ") is None


def test_el_recorte_no_parte_una_palabra_al_medio() -> None:
    largo = "x" * 50 + " " + "palabra " * 60

    cola = _introductory_tail(largo)

    assert cola is not None
    assert cola.split()[0] in {"palabra"}
