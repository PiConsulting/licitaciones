"""Auditoría de chunking (Santa Fe y Rosario, ambos reales): un párrafo de
CUERPO que Document Intelligence corta justo en el salto de página quedaba en
dos chunks separados, sin overlap, aunque compartieran `heading_path` -- el
merge de bloques exigía `page_number` igual.

Casos reales:
- PUBCG Santa Fe (pág. 8→9): "...la UT deberá tener una du-" / "ración
  superior al tiempo que demande la ejecución del contrato..." -- la palabra
  "duración" partida a la mitad.
- PUBCG Santa Fe (pág. 22→23, sección "Formas de Constitución"): "...efectuado
  en el" / "Agente Financiero de la Provincia..." -- corte en límite de
  palabra, sin guion.
- Rosario (pág. 3→4): "...atribuidos a la ignorancia del" / "proveedor
  respecto de la ubicación..." -- mismo patrón.
"""

from __future__ import annotations

from typing import Any

from indexing.chunking import create_chunks


def _heading(contenido: str, page: int, source_order: int, nivel: int = 1) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": nivel,
        "page_number": page,
        "source_order": source_order,
    }


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


def test_palabra_cortada_a_la_mitad_en_el_salto_de_pagina_se_reconstruye() -> None:
    bloques = [
        _heading("3.1.4. Presentación de Uniones Transitorias", 8, 0),
        _parrafo(
            "Una vez presentadas, bajo las figuras antes mencionadas no podrán modificar su "
            "integración. La UT deberá tener una du-",
            8,
            1,
        ),
        _parrafo(
            "ración superior al tiempo que demande la ejecución del contrato, incluido el "
            "plazo de garantía.",
            9,
            2,
        ),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert len(chunks) == 1
    assert "duración superior al tiempo" in chunks[0]["content"]
    assert "du-" not in chunks[0]["content"]


def test_corte_en_limite_de_palabra_sin_guion_se_reconstruye() -> None:
    """El caso de "Formas de Constitución" del PUBCG: no hay guion, la
    oración sencillamente sigue en la página siguiente."""
    bloques = [
        _heading("10.2. Formas de Constitución", 22, 0),
        _parrafo(
            "Las garantías deberán constituirse en alguna de las siguientes formas: a. En "
            "efectivo mediante depósito a la vista realizado en la cuenta bancaria que "
            "establezca la Unidad Rectora Central y a favor de la Jurisdicción o Entidad "
            "contratante, efectuado en el",
            22,
            1,
        ),
        _parrafo(
            "Agente Financiero de la Provincia, salvo disposiciones nacionales o convenios "
            "interjurisdiccionales que establezcan otra entidad financiera distinta.",
            23,
            2,
        ),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert len(chunks) == 1
    assert "efectuado en el Agente Financiero de la Provincia" in chunks[0]["content"]


def test_dos_parrafos_completos_en_paginas_consecutivas_no_se_fusionan() -> None:
    """El fix solo agrega un camino de fusión para el caso de un párrafo
    CORTADO (no termina en un límite real de oración). Si el bloque anterior
    SÍ termina en un punto real, dos párrafos en páginas consecutivas bajo el
    mismo heading siguen sin fusionarse -- mismo comportamiento que ya había
    antes de este fix, sin regresión."""
    bloques = [
        _heading("Artículo 14: OBLIGACIONES DEL ADJUDICATARIO", 5, 0),
        _parrafo("Deberá ajustarse estrictamente a los términos y condiciones del Pliego.", 5, 1),
        _parrafo(
            "Garantía del equipamiento: Deberá extenderse por al menos 3 años.",
            6,
            2,
        ),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert len(chunks) == 2
    assert chunks[0]["content"].endswith("Pliego.")
    assert chunks[1]["content"].startswith("Garantía del equipamiento")


def test_no_fusiona_entre_paginas_no_consecutivas() -> None:
    """Guarda: si hay una página de por medio (ej. una tabla intercalada que
    ya se filtró antes), no se asume continuidad."""
    bloques = [
        _heading("Artículo X", 4, 0),
        _parrafo("Este párrafo termina raro sin punto y aparte-", 4, 1),
        _parrafo("y esto no debería pegarse porque no es la página siguiente.", 6, 2),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert len(chunks) == 2


def test_no_fusiona_entre_headings_distintos_aunque_la_pagina_siga() -> None:
    """Guarda: páginas consecutivas pero heading_path distinto no debe
    fusionarse, aunque el bloque anterior no termine en punto."""
    bloques = [
        _heading("Artículo 5", 4, 0),
        _parrafo("Este párrafo del artículo 5 termina sin punto y aparte-", 4, 1),
        _heading("Artículo 6", 5, 2),
        _parrafo("Este es el cuerpo real del artículo 6, sin relación con el anterior.", 5, 3),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    assert len(chunks) == 2
    assert chunks[0]["content"].endswith("sin punto y aparte-")
    assert chunks[1]["content"].startswith("Este es el cuerpo real")
