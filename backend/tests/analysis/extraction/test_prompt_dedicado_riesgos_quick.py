"""
Test del prompt dedicado de Riesgos (REDISEÑO 2026-09-18).

`riesgos.txt` dejó de ser un prompt de extracción sobre chunks crudos -- ahora
recibe un DIGEST de hechos ya extraídos por otras categorías (garantías,
plazos, requisitos, causales, criterios) y selecciona/prioriza los 3-5 más
materialmente riesgosos. Estos tests validan la estructura de ESE diseño, no
la del prompt de escaneo-de-chunks anterior (ver git history si hace falta
comparar).
"""

from analysis.extraction.engine.prompts import (
    CANONICAL_CATEGORY_PROMPT_MAP,
    CANONICAL_PROMPT_FILES,
    _load_prompt,
)


def test_prompt_existe_y_registrado():
    assert "riesgos.txt" in CANONICAL_PROMPT_FILES
    assert CANONICAL_CATEGORY_PROMPT_MAP.get("riesgos") == "riesgos.txt"

    prompt_content = _load_prompt("riesgos.txt")
    assert len(prompt_content) > 0


def test_prompt_recibe_digest_no_chunks():
    """A diferencia de las demás categorías, este prompt NO tiene el bloque
    `<contexto_pliego>{chunks}</contexto_pliego>` -- recibe `{digest}`, la
    lista de hechos ya extraídos por otras categorías."""
    prompt = _load_prompt("riesgos.txt")

    assert "{digest}" in prompt
    assert "<contexto_pliego>" not in prompt
    assert "{chunks}" not in prompt


def test_prompt_excluye_los_6_tipos_que_ahora_vienen_de_preview():
    """forma_pago/moneda/tipo_cambio/anticipo_financiero/responsabilidad_
    costos_logisticos/multas_penalidades se movieron a extracción directa de
    `preview_criterios.txt` -- riesgos ya no debe reclamarlos."""
    prompt = _load_prompt("riesgos.txt")

    for tipo in (
        "forma de pago",
        "moneda",
        "tipo de cambio",
        "anticipo financiero",
        "multas y penalidades",
    ):
        assert tipo in prompt.lower(), f"debe mencionar explícitamente que excluye '{tipo}'"


def test_prompt_define_estructura_de_salida_por_indices():
    """El LLM referencia hechos del digest por índice -- las citas se
    resuelven en código a partir de esos índices, nunca las inventa/repite el
    LLM (ver `_resolve_source_references` en riesgos.py)."""
    prompt = _load_prompt("riesgos.txt")

    for field in ("indices", "explicacion", "tipo", "subtipo"):
        assert f'"{field}"' in prompt, f"Campo '{field}' debe estar en el formato de salida"


def test_prompt_tipos_y_subtipos_definidos():
    prompt = _load_prompt("riesgos.txt")

    for tipo in ("descalificacion", "penalizacion", "legal", "operativo", "financiero", "otro"):
        assert tipo in prompt

    for subtipo in (
        "ejecucion",
        "incumplimiento",
        "operativo",
        "plazos",
        "economico",
        "tecnico",
        "legal_contractual",
        "comercial",
        "otro_explicito",
    ):
        assert subtipo in prompt


def test_prompt_permite_lista_vacia_y_no_fuerza_minimo() -> None:
    """Pedido explícito ya documentado: preferir `[]` (o menos de 3) antes
    que forzar un riesgo dudoso solo para completar un cupo."""
    prompt = _load_prompt("riesgos.txt")

    assert '"riesgos": []' in prompt
    assert "preferí" in prompt.lower() or "preferi" in prompt.lower()


def test_prompt_no_inventa_indices_fuera_del_digest() -> None:
    prompt = _load_prompt("riesgos.txt")

    assert "no inventes" in prompt.lower()
