from __future__ import annotations

import pytest

from analysis.extraction.synthesis import run_synthesis


def test_response_base_prompt_no_fuerza_formato_por_categoria() -> None:
    """El formato (parrafo/lista/tabla) lo decide el LLM segun el contenido de
    CADA pliego, no una regla dura por categoria (ver Fase 5 del rediseno del
    pipeline: se elimino SINGLE_PARAGRAPH_CATEGORIES/CHECKLIST_CATEGORIES)."""
    from analysis.extraction.synthesis.prompt_and_serialization import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "{checklist_hint}" not in prompt
    assert "Elegís el formato según el contenido" in prompt


def test_run_synthesis_respeta_el_formato_que_devuelve_el_llm_bullet_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Presentar certificado fiscal.",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            },
                            {
                                "text": "Acreditar capacidad técnica mínima.",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            },
                        ],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "documento",
            "valor": "Certificado fiscal",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "Certificado fiscal vigente al momento de la oferta.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(
        category_key="requisitos_admisibilidad", items=items, correlation_id="corr-1"
    )
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "bullet_list"
    assert len(narrative.blocks[0].items) == 2
    # Ambos bullets referencian el mismo (unico) item, asi que comparten fuente.
    assert len(narrative.sources) == 1
    assert narrative.sources[0].citation == "Certificado fiscal vigente al momento de la oferta."
    assert narrative.sources[0].document_id == "doc-1"
    assert narrative.blocks[0].items[0].source_ids == [0]
    assert narrative.blocks[0].items[1].source_ids == [0]


def test_run_synthesis_respeta_el_formato_que_devuelve_el_llm_paragraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Serán causales de rechazo la falta de garantía y la presentación fuera de término.",
                        "confidence_level": "alta",
                        "item_refs": [0],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "causal_rechazo",
            "valor": "Causal uno",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "Serán causales de rechazo formal la falta de garantía.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="causales_rechazo", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "paragraph"
    assert narrative.sources[0].citation == "Serán causales de rechazo formal la falta de garantía."


def test_response_base_prompt_incluye_regla_de_formato_de_fecha() -> None:
    from analysis.extraction.synthesis.prompt_and_serialization import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "Fechas y horas en formato natural" in prompt
    assert "formato argentino" in prompt


def test_response_base_prompt_prioriza_checklist_breve() -> None:
    from analysis.extraction.synthesis.prompt_and_serialization import _load_response_base_prompt

    prompt = _load_response_base_prompt()

    assert "Modo checklist breve" in prompt
    assert "items de una sola idea" in prompt


def test_run_synthesis_convierte_fecha_iso_a_formato_natural(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        prompt = messages[0][1]
        assert "Fechas y horas en formato natural" in prompt
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "La oferta debe presentarse antes del 15 de septiembre de 2026 a las 14:30 hs.",
                        "confidence_level": "alta",
                        "item_refs": [0],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "presentación ofertas",
            "fecha": "2026-09-15",
            "hora": "14:30",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 4,
                    "citation": "La oferta debe presentarse antes del 15/09/2026 14:30.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="plazos_clave", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert "15 de septiembre de 2026" in narrative.blocks[0].text
    assert "2026-09-15" not in narrative.blocks[0].text


def test_run_synthesis_incluye_item_index_en_el_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """El LLM solo puede referenciar items por `item_index`: tiene que
    recibirlo explicito en el JSON de entrada, no inferirlo contando posicion."""
    captured_prompt = {}

    def fake_call_llm(*, messages, correlation_id):
        captured_prompt["value"] = messages[0][1]
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Texto.",
                        "confidence_level": "alta",
                        "item_refs": [0],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "resumen_objeto",
            "valor": "Objeto",
            "confidence": 0.9,
            "source_references": [
                {"document_id": "doc-1", "page_number": 1, "citation": "cita larga y valida"}
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="objeto_alcance", items=items, correlation_id="corr-1")
    assert result is not None
    assert '"item_index": 0' in captured_prompt["value"]


def test_run_synthesis_descarta_item_refs_fuera_de_rango(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el LLM referencia un item_index invalido, ese bloque se descarta en
    vez de mostrar una fuente inventada o vacia."""

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Afirmacion sin evidencia real.",
                        "confidence_level": "alta",
                        "item_refs": [99],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "resumen_objeto",
            "valor": "Objeto",
            "confidence": 0.9,
            "source_references": [
                {"document_id": "doc-1", "page_number": 1, "citation": "cita larga y valida"}
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="objeto_alcance", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    # El bloque invalido se descarta -> narrative vacia -> cae al mensaje canonico de Python, nunca al texto del LLM.
    assert narrative.sources == []
    assert len(narrative.blocks) == 1
    assert "Afirmacion sin evidencia real." not in narrative.blocks[0].text
    assert "No se encontró información" in narrative.blocks[0].text


def test_run_synthesis_preview_sin_evidencia_usa_mensaje_canonico() -> None:
    result = run_synthesis(category_key="preview_criterios", items=[], correlation_id="corr-preview")

    assert result is not None
    narrative, _token_usage = result
    assert len(narrative.blocks) == 1
    assert "No se encontró información sobre Preview Criterios" in narrative.blocks[0].text


def test_run_synthesis_preview_normaliza_titulos_y_orden_canonico(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {"text": "Tiempo de entrega: x", "confidence_level": "alta", "item_refs": [1]},
                            {"text": "Forma de pago: x", "confidence_level": "alta", "item_refs": [2]},
                            {"text": "Tipo de cambio: x", "confidence_level": "alta", "item_refs": [4]},
                            {"text": "Multas o penalidades: x", "confidence_level": "alta", "item_refs": [6]},
                            {"text": "Anticipo financiero: x", "confidence_level": "alta", "item_refs": [7]},
                            {"text": "Requisitos técnicos excluyentes: x", "confidence_level": "alta", "item_refs": [8]},
                            {
                                "text": "Responsabilidad por costos logísticos: a cargo del proveedor",
                                "confidence_level": "alta",
                                "item_refs": [9],
                            },
                            {"text": "Moneda de cotización: x", "confidence_level": "alta", "item_refs": [3]},
                            {"text": "Garantías: x", "confidence_level": "alta", "item_refs": [5]},
                            {"text": "Mantenimiento de la oferta: x", "confidence_level": "alta", "item_refs": [0]},
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    tipos = [
        "mantenimiento_oferta",
        "tiempo_entrega",
        "forma_pago",
        "moneda",
        "tipo_cambio",
        "garantias_cauciones",
        "multas_penalidades",
        "anticipo_financiero",
        "requisitos_tecnicos_excluyentes",
        "responsabilidad_costos_logisticos",
    ]
    items = [
        {
            "tipo": tipo,
            "valor": f"valor {index}",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": index + 1,
                    "citation": "Cita suficientemente larga para validar evidencia.",
                }
            ],
            "extraction_status": "success",
        }
        for index, tipo in enumerate(tipos)
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-preview")
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].type == "bullet_list"
    texts = [item.text for item in narrative.blocks[0].items]

    assert texts == [
        "Mantenimiento de oferta: x",
        "Tiempo de entrega: x",
        "Forma de Pago: x",
        "Licitación en pesos o dólares: x",
        "Tipo de cambio: x",
        "Garantías o cauciones: x",
        # FIX (2026-09-17/18): estos dos tipos usan el `valor` verbatim (no la paráfrasis "x" mockeada) para no colapsar una lista de items reales en una sola oración.
        "Multas o penalidades: valor 6",
        "Anticipo financiero: x",
        "Requisitos técnicos o certificaciones excluyentes: valor 8",
        "Responsabilidad por costos logísticos o de instalación: a cargo del proveedor",
    ]


def test_run_synthesis_preview_multas_penalidades_preserva_lista_multilinea(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug reportado: la card de "Multas o penalidades" mostraba una sola
    oración editorial en vez de listar cada penalidad real del pliego. El
    LLM de síntesis, aunque devuelva una paráfrasis corta (como cualquier
    otro criterio), NO debe pisar el `valor` de multas_penalidades -- ese
    valor ya viene armado línea por línea (una por fila de tabla de tasas)
    en `_project_multas_penalidades` (preview_criterios.py)."""
    multilinea = "0,5% del abono mensual por hora.\n0,25% del monto total por día hábil de demora."

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Multas o penalidades: hay penalidades varias",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            }
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "multas_penalidades",
            "valor": multilinea,
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 41,
                    "citation": "Cita suficientemente larga para validar evidencia.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-multas")
    assert result is not None
    narrative, _token_usage = result

    text = narrative.blocks[0].items[0].text
    assert text == f"Multas o penalidades: {multilinea}"
    assert "\n" in text


def test_run_synthesis_preview_forced_bullet_funciona_con_tipo_como_enum_vivo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug real (2026-09-18): los items que arma `run_extractor` a partir del
    JSON del LLM traen `tipo` como instancia VIVA de `TipoCriterioPreview`
    (el enum), no como string -- recién se aplana a string plano al persistir
    en la base. Como `TipoCriterioPreview(str, Enum)` no sobreescribe
    `__str__`, `str(tipo_enum)` da `"TipoCriterioPreview.X"`, no `"x"` -- así
    que la comparación contra el string plano fallaba SIEMPRE que la síntesis
    corría en la MISMA invocación de grafo que extrajo el item (nunca se veía
    en un test que releyera datos ya persistidos desde la base, porque ahí el
    round-trip por JSON ya lo había aplanado a string). Reproduce el bug
    real: los bullets de multas_penalidades/requisitos_tecnicos_excluyentes
    nunca mostraban el valor verbatim en un reanálisis real de un solo
    categoría, pese a que el mismo código sí funcionaba andando bien en
    pruebas contra datos ya guardados."""
    from analysis.extraction.schemas import TipoCriterioPreview

    multilinea = "Certificación ISO 9001.\nCertificación ISO/IEC 27001."

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Requisitos técnicos: se piden certificaciones ISO",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            }
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": TipoCriterioPreview.REQUISITOS_TECNICOS_EXCLUYENTES,
            "valor": multilinea,
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 12,
                    "citation": "Cita suficientemente larga para validar evidencia.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-enum-tipo")
    assert result is not None
    narrative, _token_usage = result

    text = narrative.blocks[0].items[0].text
    assert text == f"Requisitos técnicos o certificaciones excluyentes: {multilinea}"


def test_run_synthesis_preview_multas_penalidades_not_found_no_usa_valor() -> None:
    """Si el ítem es `not_found`/`failed`, seguir mostrando el mensaje
    explícito de ausencia -- no hay `valor` real que mostrar verbatim."""
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {
                            "text": "Multas o penalidades: no se encontraron penalidades",
                            "confidence_level": "baja",
                            "item_refs": [0],
                        }
                    ],
                }
            ],
            "evidence": [],
        }
    )
    items = [
        {
            "tipo": "multas_penalidades",
            "valor": None,
            "confidence": 0.0,
            "source_references": [],
            "extraction_status": "not_found",
        }
    ]

    normalized = _normalize_preview_raw_narrative(raw, items)

    text = normalized.blocks[0].items[0].text
    assert "No se encontró información" in text or "no se encontraron" in text.lower()


def _raw_bullet_list(text: str, item_refs: list[int]) -> dict:
    return {
        "blocks": [
            {
                "type": "bullet_list",
                "items": [{"text": text, "confidence_level": "alta", "item_refs": item_refs}],
            }
        ],
        "evidence": [],
    }


def _multa_item(valor: str, *, status: str = "success") -> dict:
    return {
        "tipo": "multas_penalidades",
        "valor": valor,
        "confidence": 0.9,
        "source_references": [
            {"document_id": "doc-1", "page_number": 6, "citation": "Cita suficientemente larga para verificar."}
        ],
        "extraction_status": status,
    }


def test_run_synthesis_preview_multas_resumen_junta_tasas_por_mil_y_porcentaje() -> None:
    """Bug real en producción (Bancor): el resumen ('número grande' de la card)
    solo reconocía '%' literal -- con 3 tasas reales (2 'por mil', 1 '%') mostraba
    únicamente '1%', ignorando las dos primeras (que además eran las que
    aparecían primero en el pliego)."""
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(_raw_bullet_list("Multas o penalidades: varias", [0, 1, 2, 3]))
    items = [
        _multa_item("multa equivalente al medio por mil (1/2 por mil), por cada día de atraso"),
        _multa_item("multa diaria del uno por ciento (1 %) por cada día de atraso"),
        _multa_item("multas que podrán variar del medio por mil al uno por mil (1/2 al 1 por mil)"),
        _multa_item("rechazo de su oferta"),
    ]

    normalized = _normalize_preview_raw_narrative(raw, items)

    resumen = normalized.blocks[0].items[0].resumen
    assert resumen == "1/2 por mil · 1% · 1/2 al 1 por mil"


def test_run_synthesis_preview_multas_resumen_reconoce_multiplicador() -> None:
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(_raw_bullet_list("Multas o penalidades: multiplicador", [0]))
    items = [_multa_item("indemnizar con una suma igual a CUATRO (4) veces el valor mensual correspondiente")]

    normalized = _normalize_preview_raw_narrative(raw, items)

    assert normalized.blocks[0].items[0].resumen == "4 veces"


def test_run_synthesis_preview_multas_resumen_sin_tasa_no_repite_titulo() -> None:
    """Bug real: cuando ningún item tenía una tasa reconocible, el resumen caía
    a repetir literalmente el título del h4 ("Multas o penalidades"),
    desperdiciando el número grande de la card sin mostrar ningún dato."""
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(_raw_bullet_list("Multas o penalidades: sin cifra", [0]))
    items = [_multa_item("penalidades por mora o incumplimiento")]

    normalized = _normalize_preview_raw_narrative(raw, items)

    resumen = normalized.blocks[0].items[0].resumen
    assert resumen == "Sin tasa especificada"
    assert resumen != "Multas o penalidades"


def test_run_synthesis_preview_multas_no_cuantificables_quedan_en_el_detalle() -> None:
    """Decisión de producto: una consecuencia no cuantificable (pérdida de
    garantía, rechazo de oferta) no debe implicar un "%" en el resumen, pero
    tampoco debe perderse -- sigue en el detalle de la card."""
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(_raw_bullet_list("Multas o penalidades: varias", [0, 1]))
    items = [
        _multa_item("tres por ciento (3%) del valor mensual por cada 24 horas de retraso"),
        _multa_item("rechazo de su oferta"),
    ]

    normalized = _normalize_preview_raw_narrative(raw, items)

    bullet = normalized.blocks[0].items[0]
    assert bullet.resumen == "3%"
    assert "rechazo de su oferta" in bullet.text


def test_run_synthesis_preview_conflict_count_viaja_desde_merge_node() -> None:
    """El contador de conflictos de la card ("N conflicto(s)") tiene que ser
    estructurado -- viene de `conflicts` (ya armado por merge_node), no de que
    el LLM de síntesis escriba la palabra "conflicto" en su prosa."""
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(
        _raw_bullet_list("Forma de Pago: 15 días; además, en otra cláusula, 30 días", [0, 1])
    )
    items = [
        {
            "tipo": "forma_pago",
            "valor": "15 días",
            "confidence": 0.7,
            "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "a los 15 días..."}],
            "extraction_status": "success",
        },
        {
            "tipo": "forma_pago",
            "valor": "30 días",
            "confidence": 0.7,
            "source_references": [{"document_id": "doc-1", "page_number": 12, "citation": "dentro de 30 días..."}],
            "extraction_status": "success",
        },
    ]
    conflicts = [
        {
            "category": "preview_criterios",
            "tipo": "forma_pago",
            "values": items,
            "reason": "Valores diferentes dentro del mismo documento",
        }
    ]

    normalized = _normalize_preview_raw_narrative(raw, items, conflicts)

    assert normalized.blocks[0].items[0].conflict_count == 1


def test_run_synthesis_preview_conflict_count_cero_sin_conflictos() -> None:
    from analysis.extraction.synthesis.synthesis import _normalize_preview_raw_narrative
    from analysis.extraction.schemas import RawCategoryNarrative

    raw = RawCategoryNarrative.model_validate(_raw_bullet_list("Forma de Pago: 15 días", [0]))
    items = [
        {
            "tipo": "forma_pago",
            "valor": "15 días",
            "confidence": 0.7,
            "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "a los 15 días..."}],
            "extraction_status": "success",
        }
    ]

    normalized = _normalize_preview_raw_narrative(raw, items, conflicts=[])

    assert normalized.blocks[0].items[0].conflict_count == 0


def test_run_synthesis_preview_propaga_resumen_hasta_narrative_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Mantenimiento de oferta: 60 días",
                                "resumen": "60 días",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            },
                            {
                                "text": "Forma de Pago: En pesos",
                                "resumen": "En pesos",
                                "confidence_level": "alta",
                                "item_refs": [1],
                            },
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "mantenimiento_oferta",
            "valor": "60 días",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "La oferta deberá mantenerse por 60 días.",
                }
            ],
            "extraction_status": "success",
        },
        {
            "tipo": "forma_pago",
            "valor": "En pesos",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "El pago se realizará en pesos argentinos.",
                }
            ],
            "extraction_status": "success",
        },
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-preview")
    assert result is not None
    narrative, _token_usage = result

    assert narrative.blocks[0].type == "bullet_list"
    assert narrative.blocks[0].items[0].resumen == "60 días"
    assert narrative.blocks[0].items[1].resumen == "En pesos"


def test_run_synthesis_preview_forza_resumen_no_informado_en_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Mantenimiento de oferta: No se encontró información.",
                                "resumen": "N/A",
                                "confidence_level": "media",
                                "item_refs": [0],
                            },
                            {
                                "text": "Forma de Pago: En pesos",
                                "resumen": "En pesos",
                                "confidence_level": "alta",
                                "item_refs": [1],
                            }
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "mantenimiento_oferta",
            "valor": "",
            "confidence": 0.7,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "No se identifica información sobre mantenimiento de oferta.",
                }
            ],
            "extraction_status": "not_found",
        },
        {
            "tipo": "forma_pago",
            "valor": "En pesos",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "El pago se realizará en pesos argentinos.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-preview")
    assert result is not None
    narrative, _token_usage = result

    assert narrative.blocks[0].type == "bullet_list"
    assert narrative.blocks[0].items[0].resumen == "No informado"
    assert narrative.blocks[0].items[1].resumen == "En pesos"


def test_run_synthesis_preview_propaga_resumen_via_resolucion_por_evidencia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regresion: cuando el LLM devuelve `evidence` (el camino real de
    produccion, ver `_response_base.txt`), `_resolve_from_evidence` es el que
    arma la narrative final -- y antes descartaba `resumen` al construir cada
    bullet, dejando las cards de preview siempre en "-"."""

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Mantenimiento de oferta: 60 días",
                                "resumen": "60 días",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            },
                            {
                                "text": "Forma de Pago: En pesos",
                                "resumen": "En pesos",
                                "confidence_level": "alta",
                                "item_refs": [1],
                            },
                        ],
                    }
                ],
                "evidence": [
                    {
                        "document_id": "doc-1",
                        "page_number": 1,
                        "text": "La oferta deberá mantenerse por 60 días.",
                        "claim": "Mantenimiento de oferta: 60 días",
                        "item_refs": [0],
                    },
                    {
                        "document_id": "doc-1",
                        "page_number": 2,
                        "text": "El pago se realizará en pesos argentinos.",
                        "claim": "Forma de Pago: En pesos",
                        "item_refs": [1],
                    },
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "mantenimiento_oferta",
            "valor": "60 días",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "La oferta deberá mantenerse por 60 días.",
                }
            ],
            "extraction_status": "success",
        },
        {
            "tipo": "forma_pago",
            "valor": "En pesos",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "El pago se realizará en pesos argentinos.",
                }
            ],
            "extraction_status": "success",
        },
    ]

    result = run_synthesis(category_key="preview_criterios", items=items, correlation_id="corr-preview-evidence")
    assert result is not None
    narrative, _token_usage = result

    assert narrative.blocks[0].type == "bullet_list"
    assert narrative.blocks[0].items[0].resumen == "60 días"
    assert narrative.blocks[0].items[1].resumen == "En pesos"


def test_run_synthesis_categoria_no_preview_no_requiere_resumen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Garantía de oferta del 1%.",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            }
                        ],
                    }
                ]
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", fake_call_llm)

    items = [
        {
            "tipo": "garantia_oferta",
            "valor": "1%",
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 3,
                    "citation": "La garantía de oferta será del 1%.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    result = run_synthesis(category_key="garantias", items=items, correlation_id="corr-garantias")
    assert result is not None
    narrative, _token_usage = result

    assert narrative.blocks[0].type == "bullet_list"
    assert narrative.blocks[0].items[0].resumen is None


def _requisito_items() -> list[dict]:
    return [
        {
            "tipo": "documento",
            "valor": "Constancia de inscripción vigente.",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 3,
                    "citation": "Deberá acompañar constancia de inscripción vigente.",
                }
            ],
            "extraction_status": "success",
        }
    ]


def _fake_bullet_response() -> tuple[dict, dict]:
    return (
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {
                            "text": "Presentar constancia de inscripción vigente.",
                            "titulo": "Inscripción vigente",
                            "confidence_level": "alta",
                            "item_refs": [0],
                        }
                    ],
                }
            ],
        },
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    )


def test_run_synthesis_reintenta_una_vez_ante_fallo_transitorio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso real (análisis 9e8b8155, `requisitos_admisibilidad` con 43 items):
    la síntesis de la categoría con el prompt más grande falló una vez y no
    volvió a intentarlo -- el frontend se quedó sin `titulo` por bullet y cayó
    al nombre crudo del `tipo` ("Documento" para casi todos los ítems, porque
    es el bucket genérico del schema). Reproducido en aislado, el mismo
    prompt/items sí generó narrativa completa -- consistente con una falla
    transitoria de capacidad/latencia bajo la concurrencia de las 8 categorías
    sintetizando en paralelo, no con un problema determinístico de contenido."""
    calls = {"count": 0}

    def flaky_call_llm(*, messages, correlation_id):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("Azure OpenAI request timed out")
        return _fake_bullet_response()

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", flaky_call_llm)
    monkeypatch.setattr("analysis.extraction.synthesis.synthesis.time.sleep", lambda _seconds: None)

    result = run_synthesis(
        category_key="requisitos_admisibilidad",
        items=_requisito_items(),
        correlation_id="corr-retry",
    )

    assert calls["count"] == 2
    assert result is not None
    narrative, _token_usage = result
    assert narrative.blocks[0].items[0].titulo == "Inscripción vigente"


def test_run_synthesis_devuelve_none_si_fallan_todos_los_intentos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def always_fails(*, messages, correlation_id):
        calls["count"] += 1
        raise TimeoutError("Azure OpenAI request timed out")

    monkeypatch.setattr("analysis.extraction.engine.base._call_llm", always_fails)
    monkeypatch.setattr("analysis.extraction.synthesis.synthesis.time.sleep", lambda _seconds: None)

    result = run_synthesis(
        category_key="requisitos_admisibilidad",
        items=_requisito_items(),
        correlation_id="corr-retry-exhausted",
    )

    assert calls["count"] == 2
    assert result is None
