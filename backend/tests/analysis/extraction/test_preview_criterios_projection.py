from __future__ import annotations

from analysis.extraction.extractors.preview_criterios import (
    _apply_content_guards,
    _project_plazos_clave,
    _project_requisitos_tecnicos,
)


def _requisito(tipo: str, valor: str, *, obligatorio: str = "no_especificado") -> dict:
    return {
        "tipo": tipo,
        "valor": valor,
        "metadata": {"obligatorio": obligatorio},
        "confidence": 0.9,
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": valor}
        ],
        "extraction_status": "success",
    }


def test_project_requisitos_tecnicos_usa_el_tag_del_extractor() -> None:
    """Camino primario: filtra por `tipo` = certificacion / requisito_tecnico_
    excluyente, sin depender de que el vocabulario matchee una keyword."""
    requisitos = [
        _requisito("documento", "Constancia de inscripción en el registro de proveedores"),
        _requisito(
            "requisito_tecnico_excluyente",
            "Deberá garantizar compatibilidad para ejecutar alguna distribución GNU/Linux",
        ),
        _requisito("certificacion", "Certificación ISO/IEC 27001 vigente exigida para admisibilidad"),
    ]

    projected = _project_requisitos_tecnicos(requisitos)

    assert len(projected) == 1
    item = projected[0]
    assert item["tipo"] == "requisitos_tecnicos_excluyentes"
    assert item["extraction_status"] == "success"
    # "GNU/Linux" no matchea ninguna keyword del fallback -- entra por el tag.
    assert "GNU/Linux" in str(item["valor"])


def test_project_requisitos_tecnicos_cae_al_fallback_por_keyword_si_no_hay_tag() -> None:
    """Pliego analizado antes del cambio (ningún ítem taggeado): sigue andando
    la heurística vieja (obligatorio + keyword)."""
    requisitos = [
        _requisito("documento", "Balance de los últimos 3 ejercicios"),
        _requisito(
            "capacidad_minima",
            "Certificación ISO 9001 del fabricante",
            obligatorio="si",
        ),
    ]

    projected = _project_requisitos_tecnicos(requisitos)

    assert projected[0]["tipo"] == "requisitos_tecnicos_excluyentes"
    assert projected[0]["extraction_status"] == "success"


def test_project_requisitos_tecnicos_sin_nada_emite_not_found() -> None:
    projected = _project_requisitos_tecnicos(
        [_requisito("documento", "Declaración jurada de no encontrarse inhabilitado")]
    )

    assert projected[0]["tipo"] == "requisitos_tecnicos_excluyentes"
    assert projected[0]["extraction_status"] == "not_found"


def test_project_plazos_clave_detecta_validez_plural_como_mantenimiento_oferta() -> None:
    plazos = [
        {
            "referencia": "Validez de las ofertas",
            "texto_original": "El mantenimiento de las ofertas será de sesenta (60) días corridos.",
            "confidence": 0.85,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 12,
                    "citation": "El mantenimiento de las ofertas será de sesenta (60) días corridos.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "success"
    assert "sesenta (60) días" in str(mantenimiento["valor"])


def test_project_plazos_clave_sin_match_emite_not_found_para_ambos_tipos() -> None:
    plazos = [
        {
            "referencia": "Acto de apertura",
            "texto_original": "La apertura de sobres se realizará el 15 de octubre.",
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 7,
                    "citation": "La apertura de sobres se realizará el 15 de octubre.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["tiempo_entrega"]["extraction_status"] == "not_found"
    assert by_tipo["mantenimiento_oferta"]["extraction_status"] == "not_found"


def test_project_plazos_clave_detecta_mantenimiento_sin_articulo() -> None:
    """Caso real reportado: pliego de Tucumán, referencia sin artículo entre
    'de' y 'oferta', y texto_original que usa el verbo 'mantener' + la
    palabra 'propuestas' en vez del sustantivo 'mantenimiento' + 'ofertas'.
    Antes del fix (`las?` exigía literalmente la palabra "la"/"las"), esto
    quedaba como not_found pese a estar bien extraído en plazos_clave."""
    plazos = [
        {
            "referencia": "Mantenimiento de oferta",
            "texto_original": (
                "Los oferentes deberán mantener sus propuestas por el plazo de 40 "
                "(cuarenta) días hábiles administrativos, contados a partir de la "
                "fecha fijada para la apertura de cotizaciones."
            ),
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 26,
                    "citation": (
                        "Los oferentes deberán mantener sus propuestas por el "
                        "plazo de 40 (cuarenta) días hábiles administrativos,"
                    ),
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "success"
    assert "40 (cuarenta)" in str(mantenimiento["valor"])


def test_project_plazos_clave_no_falso_positivo_con_mantener_no_relacionado() -> None:
    """Guardrail: 'mantener' cerca de otra palabra que no sea oferta/propuesta
    (ej. una garantía que se debe 'mantener vigente') no debe clasificarse
    como mantenimiento de oferta."""
    plazos = [
        {
            "referencia": "Vigencia de garantía de cumplimiento",
            "texto_original": (
                "El adjudicatario deberá mantener vigente la garantía de "
                "cumplimiento del contrato durante 12 meses."
            ),
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 9,
                    "citation": (
                        "El adjudicatario deberá mantener vigente la garantía de "
                        "cumplimiento del contrato durante 12 meses."
                    ),
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "not_found"


def _preview_item(tipo: str, valor: str | None, citation: str) -> dict:
    return {
        "tipo": tipo,
        "valor": valor,
        "metadata": {},
        "confidence": 0.8,
        "source_references": [{"document_id": "doc-1", "page_number": 6, "citation": citation}],
        "extraction_status": "success" if valor else "not_found",
    }


def test_apply_content_guards_reemplaza_modalidad_por_snippet_de_costos() -> None:
    """Bug real (Bancor): la extracción directa de preview_criterios.txt
    devolvía "llave en mano" como responsabilidad_costos_logisticos -- la
    modalidad de contratación, no quién paga los costos puntuales -- aunque
    la cita adjunta SÍ tenía la frase real."""
    items = [
        _preview_item(
            "responsabilidad_costos_logisticos",
            "llave en mano",
            "El proveedor asumirá todos los gastos en concepto de transportes, inspecciones y pruebas.",
        )
    ]

    guarded = _apply_content_guards(items)

    assert guarded[0]["extraction_status"] == "success"
    assert "llave en mano" not in str(guarded[0]["valor"]).lower()
    assert "asumirá" in str(guarded[0]["valor"]).lower()


def test_apply_content_guards_a_not_found_si_no_hay_snippet_de_costos() -> None:
    items = [
        _preview_item(
            "responsabilidad_costos_logisticos",
            "provisión e instalación integral",
            "El proyecto se ejecuta bajo modalidad de provisión e instalación integral.",
        )
    ]

    guarded = _apply_content_guards(items)

    assert guarded[0]["extraction_status"] == "not_found"
    assert guarded[0]["valor"] is None


def test_apply_content_guards_no_toca_responsabilidad_costos_ya_correcta() -> None:
    items = [
        _preview_item(
            "responsabilidad_costos_logisticos",
            "El adjudicatario debe correr con los gastos de flete, seguro y acarreo.",
            "El adjudicatario debe correr con los gastos de flete, seguro y acarreo.",
        )
    ]

    guarded = _apply_content_guards(items)

    assert guarded[0]["valor"] == "El adjudicatario debe correr con los gastos de flete, seguro y acarreo."


def test_apply_content_guards_moneda_sin_nombre_de_moneda_busca_snippet() -> None:
    """Bug real (Santa Fe): "moneda" terminaba con el mismo texto que
    "tipo_cambio" (ajuste de garantías por variación cambiaria) porque
    ningún otro ítem compitió por esa etiqueta esa corrida."""
    items = [
        _preview_item(
            "moneda",
            "Si se aceptan cotizaciones en moneda extranjera, las garantías se ajustan si sube más de 10%.",
            "Todos los precios deberán cotizarse en dólares estadounidenses (USD) sin IVA.",
        )
    ]

    guarded = _apply_content_guards(items)

    assert "d" in str(guarded[0]["valor"]).lower()  # "dólares"/"USD" del snippet
    assert "ajustan" not in str(guarded[0]["valor"]).lower()


def test_apply_content_guards_moneda_con_nombre_de_moneda_no_se_toca() -> None:
    items = [_preview_item("moneda", "dólares estadounidenses (USD)", "cotizar en dólares estadounidenses (USD)")]

    guarded = _apply_content_guards(items)

    assert guarded[0]["valor"] == "dólares estadounidenses (USD)"


def test_apply_content_guards_funciona_con_tipo_como_enum_vivo() -> None:
    """Bug real (2026-09-18): los items que arma `run_extractor` a partir del
    JSON del LLM traen `tipo` como instancia VIVA de `TipoCriterioPreview`
    (el enum), no como string -- recién se aplana a string plano al
    persistir en la base. `TipoCriterioPreview(str, Enum)` no sobreescribe
    `__str__`, así que la comparación `str(item.get("tipo")) == "..."` que
    usaba antes esta función NUNCA disparaba sobre un item recién extraído
    en la MISMA corrida -- el bug de "llave en mano" en Santa Fe/Bancor
    aparentaba corregido en estos tests (que siempre usan strings planos)
    pero seguía roto contra datos reales de un solo reanálisis."""
    from analysis.extraction.schemas import TipoCriterioPreview

    items = [
        {
            "tipo": TipoCriterioPreview.RESPONSABILIDAD_COSTOS_LOGISTICOS,
            "valor": "llave en mano",
            "metadata": {},
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 6,
                    "citation": "El proveedor asumirá todos los gastos en concepto de transportes, inspecciones y pruebas.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    guarded = _apply_content_guards(items)

    assert "llave en mano" not in str(guarded[0]["valor"]).lower()
    assert "asumirá" in str(guarded[0]["valor"]).lower()


def test_apply_content_guards_not_found_pasa_intacto() -> None:
    items = [_preview_item("forma_pago", None, "")]
    items[0]["extraction_status"] = "not_found"

    guarded = _apply_content_guards(items)

    assert guarded[0]["extraction_status"] == "not_found"
    assert guarded[0]["valor"] is None
