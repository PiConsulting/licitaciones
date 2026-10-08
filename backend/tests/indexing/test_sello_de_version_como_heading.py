"""Auditoría de chunking (PLIEGO_5443-26, real): un sello de version/revision
de plantilla ("V 1.13") quedó marcado por Document Intelligence como heading
de nivel 4, anidado bajo "12. Forma de Presentación de Ofertas" -- una sola
aparición en todo el documento, sin cuerpo propio. Como se apilaba en
`heading_stack`, generaba su propio chunk título-sin-cuerpo.

Fix: se extiende `_is_bullet_marker_heading` (el mismo mecanismo que ya
demueve viñetas/"ITEM N"/columnas falsamente marcadas como heading) para
reconocer también un sello de versión puro ("V 1.13", "v2.0", "Rev. 3",
"Versión 4") -- convención genérica de plantillas, no vocabulario de un
pliego puntual.

Segunda vuelta (verificación en vivo tras reindexar): una vez demovido de
heading, "V 1.13" seguía sobreviviendo como su propio chunk de 5 caracteres
-- cae justo en un salto de página, entre dos secciones distintas, sin
párrafo vecino con el que fusionarse. Fix: `_drop_page_counters`
(page_furniture.py) ahora también reconoce el sello de versión como párrafo
de cuerpo, no solo como heading -- mismo patrón `_VERSION_STAMP_RE`.
"""

from __future__ import annotations

from typing import Any

from indexing.chunking import create_chunks
from indexing.chunking.headings import _is_bullet_marker_heading
from indexing.chunking.page_furniture import _drop_page_counters


def _bloque_heading(contenido: str, page: int, source_order: int, nivel: int) -> dict[str, Any]:
    return {
        "content": contenido,
        "page_number": page,
        "source_order": source_order,
        "heading_level": nivel,
    }


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


# ---------------------------------------------------------------------------
# `_is_bullet_marker_heading`: reconoce el sello de versión
# ---------------------------------------------------------------------------


def test_sellos_de_version_se_reconocen() -> None:
    for texto in ("V 1.13", "v1.2", "Rev. 3", "Revisión 1.0", "REV 2", "Versión 4"):
        assert _is_bullet_marker_heading(texto), f"{texto!r} debería reconocerse como sello"


def test_headings_reales_que_empiezan_con_v_no_se_confunden() -> None:
    """Guarda: "V. DISPOSICIONES GENERALES" es un título real (numeración
    romana), no un sello de versión -- no debe demoverse."""
    for texto in (
        "V. DISPOSICIONES GENERALES",
        "Ver Anexo 3",
        "Versión 2026 del Pliego",
        "ARTÍCULO 12: PLAZO DE ENTREGA",
    ):
        assert not _is_bullet_marker_heading(texto), f"{texto!r} no debería tratarse como sello"


# ---------------------------------------------------------------------------
# Pipeline completo: no queda como heading_path ni como chunk título-sin-cuerpo
# ---------------------------------------------------------------------------


def test_el_sello_de_version_no_genera_un_chunk_titulo_sin_cuerpo() -> None:
    bloques = [
        _bloque_heading("12. Forma de Presentación de Ofertas", 5, 0, 1),
        _parrafo("Conforme Artículo 24, 25 y 26 del Reglamento de Contrataciones.", 5, 1),
        _bloque_heading("V 1.13", 5, 2, 2),
        _bloque_heading("13. Apertura de Ofertas", 6, 0, 1),
        _parrafo("Conforme Artículos 48 y 49 del Reglamento de Contrataciones.", 6, 1),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    for chunk in chunks:
        assert "V 1.13" not in (chunk.get("heading_path") or [])
        assert chunk["content"].strip() != "V 1.13"


def test_el_sello_de_version_como_parrafo_huerfano_tambien_se_descarta() -> None:
    """Caso real (segunda vuelta): tras demoverse de heading, "V 1.13" cae
    justo en un salto de página entre dos secciones distintas -- sin párrafo
    vecino con el que fusionarse, sobrevive como su propio chunk de 5
    caracteres. `_drop_page_counters` lo saca antes de llegar a chunking."""
    bloques = [
        {"content": "Conforme Artículo 24, 25 y 26 del Reglamento de Contrataciones.", "page_number": 5, "source_order": 0},
        {"content": "V 1.13", "page_number": 6, "source_order": 0},
        {"content": "Conforme Artículos 48 y 49 del Reglamento de Contrataciones.", "page_number": 6, "source_order": 1},
    ]

    resultado = _drop_page_counters(bloques)

    assert [b["content"] for b in resultado] == [
        "Conforme Artículo 24, 25 y 26 del Reglamento de Contrataciones.",
        "Conforme Artículos 48 y 49 del Reglamento de Contrataciones.",
    ]


def test_el_sello_de_version_marcado_heading_por_di_no_sobrevive_al_pipeline_completo() -> None:
    """Forma real del bug: DI marca "V 1.13" con `heading_level` (no como
    párrafo suelto) -- el primer `_drop_page_counters` (antes del loop de
    encabezados en `_to_intermediate_blocks`) lo salta a propósito, porque en
    ESE punto todavía no se sabe que es un artefacto y no un heading real.
    `_is_bullet_marker_heading` lo demueve a párrafo DENTRO del loop, pero
    hacía falta un segundo paso de `_drop_page_counters` al final para que no
    sobreviva como su propio chunk huérfano."""
    bloques = [
        {"heading_level": 1, "content": "12. Forma de Presentación de Ofertas", "page_number": 5, "source_order": 0},
        {"content": "Conforme Artículo 24, 25 y 26 del Reglamento de Contrataciones.", "page_number": 5, "source_order": 1},
        {"heading_level": 2, "content": "V 1.13", "page_number": 5, "source_order": 2},
        {"heading_level": 1, "content": "13. Apertura de Ofertas", "page_number": 6, "source_order": 0},
        {"content": "Conforme Artículos 48 y 49 del Reglamento de Contrataciones.", "page_number": 6, "source_order": 1},
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    for chunk in chunks:
        assert chunk["content"].strip() != "V 1.13"
