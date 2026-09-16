# Regresión (2026-09-14, Fase 1 de auditoría RAG, finding P0-1): las
# cláusulas numeradas con notación ordinal argentina ("7º.- GARANTÍAS",
# "10º.- MANTENIMIENTO DE OFERTA") no se reconocían como run-in heading
# porque `_RUN_IN_HEADING_RE` solo aceptaba dígitos pelados ("7", "10").
# Consecuencia real confirmada en un pliego real (Dell): la cláusula de
# garantías y las 4 cláusulas numeradas siguientes quedaban en el MISMO
# bloque, y `_detect_incisos` (que corta el último inciso hasta el final del
# bloque sin más límite) terminaba metiendo el contenido de esas cláusulas
# ajenas dentro del último inciso -- el LLM citó ese chunk contaminado para
# un dato de garantías que en realidad hablaba de otra cosa.
from __future__ import annotations

from indexing.chunking.headings import _promote_run_in_headings


def _block(content: str) -> dict:
    return {
        "page_number": 3,
        "block_type": "paragraph",
        "content": content,
        "source_order": 0,
        "table_ref": None,
    }


def test_clausula_con_ordinal_se_promueve_a_heading() -> None:
    blocks = [_block("8º.- I.V.A.: Los precios deberán incluir el impuesto al valor agregado.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 1
    assert "I.V.A" in headings[0]["content"]


def test_clausula_con_simbolo_grado_tambien_se_promueve() -> None:
    """Algunos pliegos tipean '°' (grado) en vez de 'º' (ordinal masculino) --
    ambos aparecen indistintamente en la práctica."""
    blocks = [_block("10°.- MANTENIMIENTO DE OFERTA: Las ofertas deberán mantenerse por 60 días.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 1


def test_dos_clausulas_ordinales_consecutivas_quedan_en_bloques_separados() -> None:
    """El caso real: una cláusula de garantías (con sus propios incisos a-d,
    en el mismo párrafo) seguida de una cláusula ajena numerada -- antes del
    fix, todo esto era UN SOLO bloque; `_detect_incisos` mezclaba el
    contenido de la segunda cláusula dentro del último inciso de la primera."""
    contenido = (
        "7º.- GARANTÍAS: a) GARANTÍA DE OFERTA: el oferente debe constituir garantía "
        "equivalente al uno por ciento del monto total cotizado como mínimo del "
        "presupuesto oficial de la presente contratación.\n\n"
        "b) GARANTÍA DE ADJUDICACIÓN: dentro de los diez días de notificada la "
        "adjudicación el adjudicatario deberá constituir garantía de cumplimiento "
        "de contrato equivalente al cinco por ciento del monto adjudicado.\n\n"
        "8º.- I.V.A.: Los precios cotizados deberán incluir el impuesto al valor "
        "agregado vigente al momento de la facturación correspondiente a la entrega."
    )
    blocks = [_block(contenido)]

    promoted = _promote_run_in_headings(blocks)

    iva_heading_index = next(
        i
        for i, b in enumerate(promoted)
        if b.get("heading_level") == 2 and "I.V.A" in b["content"]
    )
    # Todo lo que quedó ANTES del heading de IVA (incluida la cláusula de
    # garantías con sus incisos) no debe mencionar IVA -- si el fix no
    # funcionara, "8º.- I.V.A..." seguiría pegado al cuerpo de garantías.
    contenido_previo = "\n\n".join(
        str(b.get("content", "")) for b in promoted[:iva_heading_index]
    )
    assert "I.V.A" not in contenido_previo
    assert "GARANT" in contenido_previo


def test_articulo_con_texto_no_numerado_sigue_funcionando() -> None:
    """No romper el caso ya cubierto: 'Artículo N' sigue reconociéndose."""
    blocks = [_block("Artículo 10: MANTENIMIENTO DE OFERTA. Las ofertas deben mantenerse vigentes.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 1


# ---------------------------------------------------------------------------
# Auditoría de chunking (Rosario, real): el `title_bare` no-greedy se
# conforma con el mínimo de letras mayúsculas que ya satisface
# `_looks_like_section_title` -- corta el título mucho antes de que
# terminen las mayúsculas reales del pliego.
# ---------------------------------------------------------------------------


def test_titulo_sin_dos_puntos_propio_no_se_corta_antes_de_tiempo() -> None:
    """Caso real de Rosario: sin un ':' que delimite el título (va directo a
    la rama `title_bare`, no-greedy), el regex se conformaba con "PLA" -- 3
    letras ya alcanzan el 100% de mayúsculas que exige
    `_looks_like_section_title`. El título real es "PLAZO DE ENTREGA"."""
    blocks = [
        _block(
            "Artículo 12: PLAZO DE ENTREGA El plazo de entrega de los productos será "
            "como máximo de noventa (90) días corridos a partir de la recepción de la "
            "Orden de Provisión."
        )
    ]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 1
    assert headings[0]["content"] == "Artículo 12: PLAZO DE ENTREGA"

    cuerpo = "\n\n".join(
        str(b.get("content", "")) for b in promoted if b.get("heading_level") != 2
    )
    assert cuerpo.startswith("El plazo de entrega")
    assert "PLAZO" not in cuerpo


def test_palabra_partida_a_la_mitad_por_el_corte_lazy_se_reconstruye_sin_espacio() -> None:
    """La palabra "PLAZO" queda literalmente partida entre lo que el regex
    capturó ("PLA") y lo que dejó en el cuerpo ("ZO...") -- sin espacio real
    entre ambas mitades. La reconstrucción no debe insertar uno."""
    blocks = [_block("Artículo 5: PLAZO Los plazos se cuentan en días corridos.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert headings[0]["content"] == "Artículo 5: PLAZO"


def test_la_extension_se_detiene_en_la_primera_palabra_que_no_es_mayuscula() -> None:
    """Guarda: no debe devorar el cuerpo real solo porque sigue con mayúsculas
    parciales -- se detiene apenas aparece una palabra que no es 100%
    mayúscula (ignorando puntuación), como "El" (arranca la oración)."""
    blocks = [_block("Artículo 9: ADJUDICACIÓN DEFINITIVA El acto de adjudicación pondrá fin.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert headings[0]["content"] == "Artículo 9: ADJUDICACIÓN DEFINITIVA"


def test_la_extension_no_devora_un_parrafo_entero_en_mayusculas() -> None:
    """Guarda de tamaño: si lo que sigue es una cláusula real escrita entera
    en mayúsculas (no un título cortado), la extensión no debe convertir
    todo el párrafo en heading -- se acota a `_HEADING_TAIL_MAX_CHARS`."""
    clausula_larga_en_mayusculas = " ".join(["PALABRA"] * 30)
    blocks = [_block(f"Artículo 1: TÍTULO {clausula_larga_en_mayusculas} y sigue en minúsculas.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert headings[0]["content"] != f"Artículo 1: TÍTULO {clausula_larga_en_mayusculas}"
    assert len(headings[0]["content"]) < len(f"Artículo 1: TÍTULO {clausula_larga_en_mayusculas}")


def test_titulo_que_ocupa_todo_el_parrafo_sin_cuerpo_propio_se_promueve_igual() -> None:
    """Caso real de Rosario, confirmado con el markdown crudo de Document
    Intelligence: "ARTÍCULO 12: PLAZO DE ENTREGA" llega como bloque PROPIO,
    completo, sin nada más -- el cuerpo real ("El plazo de entrega...") está
    en la página siguiente, en otro bloque. Antes de este fix, la extensión
    consumía TODO el remanente ("ZO DE ENTREGA") hacia el título, dejaba
    `body=""`, y la guarda `if not body` descartaba el heading entero --
    "ARTÍCULO 12: PLAZO DE ENTREGA" quedaba como texto plano, sin promoverse
    nunca a heading."""
    blocks = [_block("Artículo 12: PLAZO DE ENTREGA")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 1
    assert headings[0]["content"] == "Artículo 12: PLAZO DE ENTREGA"
    # Sin cuerpo propio: no debe quedar ningún bloque vacío/espurio.
    cuerpos = [b for b in promoted if b.get("heading_level") != 2]
    assert not any(not str(b.get("content", "")).strip() for b in cuerpos)


def test_numero_dentro_de_una_oracion_no_se_promueve() -> None:
    """El ordinal solo cuenta al INICIO del párrafo -- un número de artículo
    mencionado en medio de una oración no debe generar un heading falso."""
    blocks = [_block("Según lo establecido en el artículo 8º de este pliego, los oferentes deberán presentar la documentación correspondiente en tiempo y forma ante la mesa de entradas del organismo licitante.")]

    promoted = _promote_run_in_headings(blocks)

    headings = [b for b in promoted if b.get("heading_level") == 2]
    assert len(headings) == 0
