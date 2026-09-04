"""Tests para la derivación de `eventos_temporales`/`plazos_relativos` (legacy)
a partir del extractor fusionado de hitos temporales (ver
`analysis/extraction/prompts/eventos_temporales.txt` y el bloque de
`merge_node` que las deriva en `analysis/extraction/graph/nodes.py`).

Antes había DOS extractores LLM independientes (`eventos_temporales` y
`plazos_relativos`) que nunca se veían entre sí, y `timeline/materializer.py`
tenía que reconciliar sus nombres con una heurística de texto. Ahora hay un
solo extractor (`eventos_temporales`, con `HitosTemporalesResponse`) que ya
decide él mismo, leyendo el pliego completo, qué hitos hay y cómo se
relacionan. Estos tests verifican que `merge_node` sigue produciendo las DOS
vistas legacy con la forma EXACTA que esperaba `timeline/materializer.py`
antes del cambio -- ningún código río abajo debería notar la diferencia.
"""
from __future__ import annotations

from analysis.extraction.graph.nodes import merge_node
from analysis.extraction.state import GraphState


def _base_state(hitos_temporales: list[dict]) -> GraphState:
    return {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "eventos_temporales": hitos_temporales,
        "eventos_temporales_status": "success",
    }


def test_hito_con_fecha_propia_sin_plazo_relativo_solo_aparece_en_eventos_temporales():
    hitos = [
        {
            "nombre": "Apertura de Ofertas",
            "fecha_explicita": "2026-09-15",
            "origen_fecha": "detectada",
            "evento_disparador": None,
            "cantidad": None,
            "unidad": None,
            "tipo_dias": None,
            "direccion": None,
            "es_plazo_maximo": False,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 3,
            "fuente_fragmento": "La apertura de ofertas se realizará el 15/09/2026.",
            "extraction_status": "success",
            "_source_document_id": "doc-1",
        }
    ]

    state = merge_node(_base_state(hitos))
    extracted = state["extracted_data"]

    assert len(extracted["eventos_temporales"]) == 1
    assert extracted["eventos_temporales"][0]["nombre"] == "Apertura de Ofertas"
    assert extracted["eventos_temporales"][0]["fecha_explicita"] == "2026-09-15"
    assert extracted["eventos_temporales"][0]["_source_document_id"] == "doc-1"

    # Sin evento_disparador -> no genera un ítem de plazo relativo.
    assert extracted["plazos_relativos"] == []


def test_hito_con_plazo_relativo_aparece_en_ambas_vistas_con_forma_legacy():
    hitos = [
        {
            "nombre": "Adjudicación",
            "fecha_explicita": "2026-09-30",
            "origen_fecha": "detectada",
            "evento_disparador": None,
            "cantidad": None,
            "unidad": None,
            "tipo_dias": None,
            "direccion": None,
            "es_plazo_maximo": False,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 8,
            "fuente_fragmento": "La adjudicación se realizará el 30 de septiembre de 2026.",
            "extraction_status": "success",
            "_source_document_id": "doc-1",
        },
        {
            "nombre": "Firma del Contrato",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Adjudicación",
            "cantidad": 10,
            "unidad": "días",
            "tipo_dias": "no_especificado",
            "direccion": "desde",
            "es_plazo_maximo": True,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 8,
            "fuente_fragmento": (
                "Dentro de los 10 días de la adjudicación, el adjudicatario "
                "deberá presentarse para firmar el contrato."
            ),
            "extraction_status": "success",
            "_source_document_id": "doc-1",
        },
    ]

    state = merge_node(_base_state(hitos))
    extracted = state["extracted_data"]

    # Vista "eventos_temporales": los DOS hitos, con la forma legacy
    # (nombre/fecha_explicita/origen_fecha/fuente_*), sin los campos de plazo
    # relativo.
    eventos = {item["nombre"]: item for item in extracted["eventos_temporales"]}
    assert set(eventos) == {"Adjudicación", "Firma del Contrato"}
    assert eventos["Adjudicación"]["fecha_explicita"] == "2026-09-30"
    assert "cantidad" not in eventos["Firma del Contrato"]
    assert "evento_disparador" not in eventos["Firma del Contrato"]

    # Vista "plazos_relativos": SOLO el hito que tiene evento_disparador,
    # con la forma legacy (descripcion/cantidad/unidad/.../evento_disparador).
    assert len(extracted["plazos_relativos"]) == 1
    plazo = extracted["plazos_relativos"][0]
    assert plazo["descripcion"] == "Firma del Contrato"
    assert plazo["cantidad"] == 10
    assert plazo["unidad"] == "días"
    assert plazo["tipo_dias"] == "no_especificado"
    assert plazo["evento_disparador"] == "Adjudicación"
    assert plazo["direccion"] == "desde"
    assert plazo["es_plazo_maximo"] is True
    assert plazo["_source_document_id"] == "doc-1"


def test_evento_disparador_referencia_el_nombre_exacto_de_otro_item():
    """El corazón del cambio: como el LLM ve todo en una sola pasada, el
    `evento_disparador` de un ítem coincide EXACTAMENTE con el `nombre` de
    otro ítem de la misma lista -- ya no hay que reconciliar dos extracciones
    independientes con una heurística de texto."""
    hitos = [
        {
            "nombre": "Recepción del Pliego",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": None,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 2,
            "fuente_fragmento": "El pliego se recibe en la fecha indicada en la carátula.",
            "extraction_status": "success",
        },
        {
            "nombre": "Presentación de Consultas",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Recepción del Pliego",
            "cantidad": 15,
            "unidad": "días",
            "tipo_dias": "no_especificado",
            "direccion": "desde",
            "es_plazo_maximo": True,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 2,
            "fuente_fragmento": "Dentro de los 15 días de recibido el pliego, los oferentes deberán presentar consultas.",
            "extraction_status": "success",
        },
    ]

    state = merge_node(_base_state(hitos))
    extracted = state["extracted_data"]

    nombres_en_eventos_temporales = {item["nombre"] for item in extracted["eventos_temporales"]}
    disparador = extracted["plazos_relativos"][0]["evento_disparador"]

    # El evento_disparador tiene que matchear EXACTO un `nombre` ya presente
    # en la vista de eventos_temporales -- esto es lo que garantiza que el
    # tier de coincidencia EXACTA de materializer._find_matching_event
    # acierte, sin depender de sus tiers de substring/tokens/difflib.
    assert disparador in nombres_en_eventos_temporales


def test_mencion_propia_se_propaga_a_eventos_temporales_con_default_true():
    """`mencion_propia` distingue "el pliego declara este hito por sí mismo"
    de "se creó solo para poder ser evento_disparador de otro" -- ver el
    pedido del usuario de no poder diferenciar ambos casos en el Timeline.
    Default True si el LLM omite el campo, para no marcar como "inferido" a
    un hito real por una omisión del modelo."""
    hitos = [
        {
            "nombre": "Puesta en Marcha del Sistema",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": None,
            "mencion_propia": False,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 9,
            "fuente_fragmento": "x",
            "extraction_status": "success",
        },
        {
            "nombre": "Capacitación del Personal",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Puesta en Marcha del Sistema",
            "cantidad": 20,
            "unidad": "días",
            "tipo_dias": "corridos",
            "direccion": "después_de",
            "es_plazo_maximo": True,
            "mencion_propia": True,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 9,
            "fuente_fragmento": "y",
            "extraction_status": "success",
        },
        {
            # El LLM omitió el campo -- debe defaultear a True, no a False.
            "nombre": "Recepción del Pliego",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": None,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 1,
            "fuente_fragmento": "z",
            "extraction_status": "success",
        },
    ]

    state = merge_node(_base_state(hitos))
    eventos = {item["nombre"]: item for item in state["extracted_data"]["eventos_temporales"]}

    assert eventos["Puesta en Marcha del Sistema"]["mencion_propia"] is False
    assert eventos["Capacitación del Personal"]["mencion_propia"] is True
    assert eventos["Recepción del Pliego"]["mencion_propia"] is True


def test_sin_hitos_ambas_vistas_quedan_vacias():
    state = merge_node(_base_state([]))
    extracted = state["extracted_data"]

    assert extracted["eventos_temporales"] == []
    assert extracted["plazos_relativos"] == []


def test_status_de_plazos_relativos_se_toma_del_status_de_eventos_temporales():
    """Ya no hay un extractor separado para plazos_relativos -- su status
    legacy tiene que reflejar el status real del único extractor que corrió
    (`eventos_temporales_status`), no quedar hardcodeado en "unknown"."""
    hitos = [
        {
            "nombre": "Adjudicación",
            "fecha_explicita": "2026-09-30",
            "origen_fecha": "detectada",
            "evento_disparador": None,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 8,
            "fuente_fragmento": "La adjudicación se realizará el 30 de septiembre de 2026.",
            "extraction_status": "success",
        }
    ]
    state = _base_state(hitos)
    state["eventos_temporales_status"] = "partial"

    result_state = merge_node(state)
    extracted = result_state["extracted_data"]

    assert extracted["eventos_temporales_extraction_status"] == "partial"
    assert extracted["plazos_relativos_extraction_status"] == "partial"


def test_filtra_items_no_procedurales_de_forma_de_pago_y_vigencia_licencia():
    hitos = [
        {
            "nombre": "Forma de Pago",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Emisión de valores",
            "cantidad": 30,
            "unidad": "días",
            "tipo_dias": "no_especificado",
            "direccion": "desde",
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 5,
            "fuente_fragmento": "El pago se efectuará con cheques de pago diferido.",
            "extraction_status": "success",
        },
        {
            "nombre": "Vigencia de la Licencia",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Recepción Definitiva",
            "cantidad": 36,
            "unidad": "meses",
            "tipo_dias": "no_especificado",
            "direccion": "desde",
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 23,
            "fuente_fragmento": "Licencia con vigencia mínima de 36 meses.",
            "extraction_status": "success",
        },
        {
            "nombre": "Apertura de Cotizaciones",
            "fecha_explicita": "2026-08-19",
            "origen_fecha": "detectada",
            "evento_disparador": None,
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 1,
            "fuente_fragmento": "La apertura será el 19/08/2026 a las 10:00.",
            "extraction_status": "success",
        },
    ]

    state = merge_node(_base_state(hitos))
    extracted = state["extracted_data"]

    assert [item["nombre"] for item in extracted["eventos_temporales"]] == [
        "Apertura de Cotizaciones"
    ]
    assert extracted["plazos_relativos"] == []


def test_limpia_prefijos_columna_y_deduplica_eventos_temporales_repetidos():
    hitos = [
        {
            "nombre": "Entrega de los Bienes",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Notificación de la Adjudicación",
            "cantidad": 60,
            "unidad": "días",
            "tipo_dias": "hábiles",
            "direccion": "desde",
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 27,
            "fuente_fragmento": "col_2: El plazo de entrega será de 60 días hábiles desde la notificación.",
            "extraction_status": "success",
        },
        {
            "nombre": "Entrega de los Bienes",
            "fecha_explicita": None,
            "origen_fecha": "pendiente",
            "evento_disparador": "Notificación de la Adjudicación",
            "cantidad": 60,
            "unidad": "días",
            "tipo_dias": "hábiles",
            "direccion": "desde",
            "fuente_documento_id": "doc-1",
            "fuente_pagina": 27,
            "fuente_fragmento": "col_3: El plazo de entrega será de 60 días hábiles desde la notificación.",
            "extraction_status": "success",
        },
    ]

    state = merge_node(_base_state(hitos))
    extracted = state["extracted_data"]

    assert len(extracted["eventos_temporales"]) == 1
    assert len(extracted["plazos_relativos"]) == 1
    assert extracted["eventos_temporales"][0]["fuente_fragmento"].startswith(
        "El plazo de entrega"
    )
