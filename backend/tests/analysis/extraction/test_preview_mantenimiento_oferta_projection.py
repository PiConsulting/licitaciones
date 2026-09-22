# Regresión (2026-09-16): `_project_plazos_clave` tomaba `matches[0]` en vez del match más completo, mostrando el plazo sin el número real (caso santa_fe).
from __future__ import annotations

from analysis.extraction.extractors.preview_criterios import (
    _MANTENIMIENTO_OFERTA_PATTERNS,
    _best_descriptive_match,
    _project_plazos_clave,
)


def _plazo(referencia: str, texto_original: str, *, confidence_llm: float, expresion_relativa: str | None = None) -> dict:
    return {
        "referencia": referencia,
        "texto_original": texto_original,
        "expresion_relativa": expresion_relativa,
        "confidence": 0.7,
        "confidence_llm": confidence_llm,
        "source_references": [{"citation": texto_original[:80]}],
        "extraction_status": "success",
    }


_MARCO_SIN_NUMERO = _plazo(
    "Mantenimiento de oferta",
    "Plazo de mantenimiento de las ofertas.",
    confidence_llm=0.55,
)
_PARTICULAR_CON_NUMERO = _plazo(
    "Mantenimiento de oferta",
    "Plazo de Mantenimiento de la Oferta: 30 días corridos, a partir del día "
    "hábil administrativo siguiente a la fecha y hora de la Apertura de las Ofertas.",
    confidence_llm=0.9,
    expresion_relativa="30 días corridos a partir del día hábil administrativo "
    "siguiente a la fecha y hora de la Apertura de las Ofertas",
)
_PERFECCIONAMIENTO_CONTRATO = _plazo(
    "Perfeccionamiento del contrato",
    "El contrato se perfecciona con la notificación fehaciente del acto "
    "administrativo de adjudicación, la que deberá realizarse dentro del "
    "plazo de mantenimiento de la oferta.",
    confidence_llm=0.9,
    expresion_relativa="dentro del plazo de mantenimiento de la oferta",
)


def test_caso_real_santa_fe_elige_el_que_tiene_el_numero() -> None:
    """El marco (sin número) aparece PRIMERO en la lista -- si el bug
    estuviera presente, `valor` terminaría siendo el genérico sin número."""
    plazos = [_MARCO_SIN_NUMERO, _PERFECCIONAMIENTO_CONTRATO, _PARTICULAR_CON_NUMERO]
    projected = _project_plazos_clave(plazos)
    mantenimiento = next(p for p in projected if p["tipo"] == "mantenimiento_oferta")
    assert "30 días corridos" in mantenimiento["valor"]
    assert mantenimiento["valor"] != _MARCO_SIN_NUMERO["texto_original"]


def test_best_descriptive_match_prefiere_duracion_concreta_sobre_confidence() -> None:
    """Aunque el genérico tuviera MAYOR confidence, si no tiene número pierde
    contra uno que sí lo tiene -- la duración concreta es lo que importa."""
    generico_alta_confianza = dict(_MARCO_SIN_NUMERO, confidence_llm=0.99)
    especifico_baja_confianza = dict(_PARTICULAR_CON_NUMERO, confidence_llm=0.51)
    best = _best_descriptive_match(
        [generico_alta_confianza, especifico_baja_confianza], _MANTENIMIENTO_OFERTA_PATTERNS
    )
    assert best is especifico_baja_confianza


def test_sin_ningun_match_con_duracion_cae_al_de_mayor_confidence() -> None:
    """Si NINGÚN match tiene número (caso legítimo: el pliego no lo especifica
    todavía), no hay que inventar nada -- se usa el de mayor confidence entre
    los disponibles, igual que antes."""
    a = dict(_MARCO_SIN_NUMERO, confidence_llm=0.4)
    b = dict(_MARCO_SIN_NUMERO, texto_original="Otra mención sin número.", confidence_llm=0.8)
    best = _best_descriptive_match([a, b], _MANTENIMIENTO_OFERTA_PATTERNS)
    assert best is b


def test_expresion_relativa_sin_numero_no_cuenta_como_duracion_concreta() -> None:
    """`expresion_relativa` puede estar seteada con solo una referencia al
    concepto ("dentro del plazo de mantenimiento de la oferta"), sin decir
    cuánto es -- eso NO alcanza para preferirlo sobre otro match. Caso real:
    "Perfeccionamiento del contrato" en santa_fe, que menciona el plazo de
    mantenimiento pero no dice cuántos días es."""
    referencia_sin_numero = _plazo(
        "Perfeccionamiento del contrato",
        "El contrato se perfecciona dentro del plazo de mantenimiento de la oferta.",
        confidence_llm=0.9,
        expresion_relativa="dentro del plazo de mantenimiento de la oferta",
    )
    con_numero = dict(_PARTICULAR_CON_NUMERO, confidence_llm=0.5)
    best = _best_descriptive_match([referencia_sin_numero, con_numero], _MANTENIMIENTO_OFERTA_PATTERNS)
    assert best is con_numero


def test_numero_de_un_tema_distinto_no_le_gana_al_tema_correcto_sin_numero() -> None:
    """Caso real (santa_fe): 'Devolución garantía de oferta' MENCIONA
    'mantenimiento de la oferta' de paso (para explicar cuándo se libera la
    garantía) y hasta tiene un número (30 días) -- pero ese número es sobre
    LA DEVOLUCIÓN, no sobre cuánto dura el mantenimiento. Su `referencia` no
    es sobre el tema; la del ítem correcto sí lo es (aunque en este caso
    ambos tengan número, gana el que es realmente sobre el tema)."""
    devolucion_garantia = _plazo(
        "Devolución garantía de oferta",
        "La garantía de mantenimiento de la oferta de los oferentes que no "
        "resulten adjudicatarios será devuelta de oficio dentro de los "
        "treinta (30) días de la comunicación o notificación de la adjudicación.",
        confidence_llm=0.9,
        expresion_relativa="dentro de los treinta (30) días de la comunicación "
        "o notificación de la adjudicación",
    )
    mantenimiento_real = dict(_PARTICULAR_CON_NUMERO, confidence_llm=0.5)
    best = _best_descriptive_match(
        [devolucion_garantia, mantenimiento_real], _MANTENIMIENTO_OFERTA_PATTERNS
    )
    assert best is mantenimiento_real
