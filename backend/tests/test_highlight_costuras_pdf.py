"""El resaltado fallaba en las costuras del maquetado del PDF.

`compute_highlight_regions` usaba `page.search_for(cita)`, que busca la cadena
LITERAL en el texto del PDF. La cita, en cambio, salió del texto que devuelve
Azure Document Intelligence: reflowed, con los renglones unidos y la puntuación
normalizada. Son dos textos distintos del mismo documento.

Medido contra el pliego real del usuario (Licitación Privada de servidores,
Municipalidad de Rosario), 3 de 6 citas devolvían CERO rectángulos:

  - "...la oferta econó|mica."            -> el PDF corta la palabra al renglón
  - "...de cinco |(5) días hábiles"       -> salto de renglón en el medio
  - 'llama a Licitación P|RIVADA para la "Adquisición...'
        -> el título está maquetado con espaciado entre letras, así que
           "PRIVADA" son dos spans, y las comillas del PDF son tipográficas
           (“ ”) mientras que las de la cita son rectas (")

Cuando esto pasaba, `compute_highlights_for_sources` caía a un fallback que
emitía el bbox del PÁRRAFO entero — de ahí el "resaltado por párrafo".

Estos tests arman PDFs sintéticos que reproducen cada costura.
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF no instalado")

from analysis.extraction.highlight import compute_highlight_regions


def _pdf_con_lineas(tmp_path, lineas: list[str], *, nombre: str = "p.pdf") -> str:
    """Un PDF de una página con cada string en su propio renglón."""
    doc = fitz.open()
    page = doc.new_page()
    y = 100
    for linea in lineas:
        page.insert_text((57, y), linea, fontsize=10)
        y += 14
    ruta = tmp_path / nombre
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def _alto_total(regions: list[dict]) -> float:
    if not regions:
        return 0.0
    top = min(r["y"] for r in regions)
    bottom = max(r["y"] + r["height"] for r in regions)
    return bottom - top


# ---------------------------------------------------------------------------
# 1. Cada costura, por separado
# ---------------------------------------------------------------------------


def test_una_palabra_cortada_al_renglon_se_encuentra_igual(tmp_path) -> None:
    """El caso "la oferta econó|mica." del pliego real."""
    ruta = _pdf_con_lineas(
        tmp_path,
        ["Se rechazará la Oferta del Proponente en cuyo sobre no obre la oferta econó", "mica."],
    )

    regions = compute_highlight_regions(
        ruta, 1, "Se rechazará la Oferta del Proponente en cuyo sobre no obre la oferta económica.",
        correlation_id="t",
    )

    assert regions, "la cita cruza el corte de palabra: antes daba 0 rectángulos"
    assert len(regions) == 2, "una región por renglón"


def test_un_salto_de_renglon_en_el_medio_no_rompe_la_busqueda(tmp_path) -> None:
    ruta = _pdf_con_lineas(
        tmp_path,
        ["El adjudicatario deberá entregar la Orden de provisión firmada, en el plazo de cinco", "(5) días hábiles de recibida."],
    )

    regions = compute_highlight_regions(
        ruta, 1, "El adjudicatario deberá entregar la Orden de provisión firmada, en el plazo de cinco (5) días hábiles",
        correlation_id="t",
    )

    assert regions
    assert len(regions) == 2


def test_las_comillas_tipograficas_del_pdf_no_impiden_el_match(tmp_path) -> None:
    """La cita trae comillas rectas porque viene del texto de Document
    Intelligence; el PDF tiene las tipográficas."""
    ruta = _pdf_con_lineas(tmp_path, ["para la “Adquisición de Servidores de aplicaciones”"])

    regions = compute_highlight_regions(
        ruta, 1, 'para la "Adquisición de Servidores de aplicaciones"', correlation_id="t"
    )

    assert regions


def test_una_palabra_partida_en_spans_no_impide_el_match(tmp_path) -> None:
    """Títulos maquetados con espaciado entre letras: "LICITACIÓN P" + "RIVADA"."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((57, 100), "La Municipalidad llama a LICITACIÓN P", fontsize=10)
    page.insert_text((250, 100), "RIVADA para la adquisición", fontsize=10)
    ruta = tmp_path / "spans.pdf"
    doc.save(str(ruta))
    doc.close()

    regions = compute_highlight_regions(
        str(ruta), 1, "La Municipalidad llama a LICITACIÓN PRIVADA para la adquisición", correlation_id="t"
    )

    assert regions


# ---------------------------------------------------------------------------
# 2. Lo que NO tiene que cambiar
# ---------------------------------------------------------------------------


def test_una_cita_en_un_solo_renglon_sigue_dando_una_region(tmp_path) -> None:
    ruta = _pdf_con_lineas(tmp_path, ["Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN"])

    regions = compute_highlight_regions(
        ruta, 1, "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN", correlation_id="t"
    )

    assert len(regions) == 1


def test_el_resaltado_no_se_pasa_del_texto_de_la_cita(tmp_path) -> None:
    """La prueba de que no es "por párrafo": el rectángulo tiene que cubrir el
    renglón de la cita, no el alto del párrafo que la contiene."""
    ruta = _pdf_con_lineas(
        tmp_path,
        [
            "Renglón previo que no forma parte de la cita.",
            "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN",
            "Renglón siguiente que tampoco forma parte de la cita.",
            "Y otro más.",
        ],
    )

    regions = compute_highlight_regions(
        ruta, 1, "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN", correlation_id="t"
    )

    assert len(regions) == 1
    # Un renglón de 10pt: el alto tiene que ser del orden de la fuente, no de
    # los 4 renglones del bloque (~56pt).
    assert _alto_total(regions) < 20


def test_una_cita_que_no_esta_en_la_pagina_no_devuelve_nada(tmp_path) -> None:
    """Nunca inventar una región: no encontrar es un resultado válido, y es lo
    que le deja al frontend la señal de que no hay coordenadas."""
    ruta = _pdf_con_lineas(tmp_path, ["Un texto cualquiera del pliego."])

    regions = compute_highlight_regions(
        ruta, 1, "Una cita que no aparece en ninguna parte de este documento", correlation_id="t"
    )

    assert regions == []


def test_una_cita_repetida_resalta_una_sola_aparicion(tmp_path) -> None:
    """Política de HL-04: pintar todas las apariciones confunde más que pintar
    una. La búsqueda por palabras tiene que respetarla igual que la exacta."""
    texto = "El plazo de entrega será de noventa días corridos"
    ruta = _pdf_con_lineas(tmp_path, [texto, "Otro renglón en el medio.", texto])

    regions = compute_highlight_regions(ruta, 1, texto, correlation_id="t")

    assert len(regions) == 1
