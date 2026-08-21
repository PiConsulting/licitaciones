"""PRM-01: los prompts por categoría enseñaban citas que el esquema recorta.

`_base_system.txt` le pide al modelo citas de entre 40 y 120 caracteres y le
muestra como ❌ una cita de párrafo. Pero los ejemplos de salida de cinco
categorías mostraban como ✅ exactamente eso: 127, 130, 158, 163 y 198
caracteres. El de `garantias.txt` era casi palabra por palabra el
contraejemplo del prompt base.

Un ejemplo pesa más que una regla: el modelo copia la forma de la salida que ve.
Y una cita de 198 caracteres no se descarta -- entra a
`shorten_citation_to_evidence`, que elige una ventana de 120 alrededor del dato.
O sea, el prompt fabricaba trabajo para la maquinaria de recorte, que es
justamente donde apareció ATR-07.

Este test no revisa redacción: fija el contrato entre los prompts y el esquema.
Cualquier ejemplo nuevo que se salga del rango rompe acá y no en producción.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from analysis.extraction.schemas import (
    CITATION_MAX_CHARS,
    CITATION_MIN_CHARS,
    CITATION_PREFERRED_MIN_CHARS,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "analysis" / "extraction" / "prompts"

CATEGORIAS = [
    "anexos_obligatorios",
    "causales_rechazo",
    "criterios_evaluacion",
    "garantias",
    "identificacion_procedimiento",
    "objeto_alcance",
    "plazos_clave",
    "requisitos_admisibilidad",
]

_CITATION_RE = re.compile(r'"citation"\s*:\s*"((?:[^"\\]|\\.)*)"')
# Las citas de tabla tienen su propio formato y su propia verificación
# (`_citation_verified_in_table_chunk`): no son texto corrido del pliego.
_FORMATO_TABLA = "Encabezado:"


def _citations_de(nombre: str) -> list[str]:
    texto = (PROMPTS_DIR / f"{nombre}.txt").read_text(encoding="utf-8")
    return [
        crudo.replace('\\"', '"')
        for crudo in _CITATION_RE.findall(texto)
        if _FORMATO_TABLA not in crudo
    ]


@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_ningun_ejemplo_supera_el_limite_del_esquema(categoria: str) -> None:
    """El caso del hallazgo. `SourceReference.citation` valida contra
    `CITATION_MAX_CHARS`; un ejemplo más largo enseña a producir algo que el
    pipeline va a tener que recortar."""
    largas = [(len(c), c) for c in _citations_de(categoria) if len(c) > CITATION_MAX_CHARS]

    assert not largas, "\n".join(f"  {n} caracteres: {c[:90]}" for n, c in largas)


def _normalizar(texto: str) -> str:
    return " ".join(str(texto or "").split()).lower()


def _refs_con_su_valor(categoria: str) -> list[tuple[str, str]]:
    """Pares (valor del ítem, cita) sacados de los ejemplos JSON del prompt."""
    texto = (PROMPTS_DIR / f"{categoria}.txt").read_text(encoding="utf-8")
    pares: list[tuple[str, str]] = []

    for bloque in re.findall(r"```json\n(.*?)```", texto, re.S):
        if "//" in bloque:  # contraejemplo deliberado
            continue
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        if not isinstance(datos, dict):
            continue
        for items in datos.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                valor = str(item.get("valor") or item.get("texto_original") or "")
                for ref in item.get("source_references") or []:
                    cita = str((ref or {}).get("citation") or "")
                    if cita and _FORMATO_TABLA not in cita:
                        pares.append((valor, cita))
    return pares


@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_una_cita_corta_solo_se_permite_si_el_dato_ES_la_cita(categoria: str) -> None:
    """Por debajo de `CITATION_PREFERRED_MIN_CHARS` el pipeline ensancha la cita
    con el contexto del chunk, así que un ejemplo corto enseña a producir algo
    que no queda como se muestra.

    Pero hay un caso legítimo y hay que distinguirlo: en una carátula el dato
    *es* una línea corta -- `organismo_convocante` = "Municipalidad de Rosario",
    24 caracteres, y no hay nada más que agregar que siga probando ESE dato.
    Exigirle 40 caracteres ahí obligaría al modelo a rellenar con las líneas
    vecinas de la carátula, que es exactamente la falla de ATR-07: una cita que
    cubre tres datos ajenos y deja de ser evidencia de éste.

    Entonces la regla no es "toda cita ≥ 40", sino: si es más corta, tiene que
    ser porque el dato mismo es corto -- el `valor` ocupa casi toda la cita.
    """
    problemas = []
    for valor, cita in _refs_con_su_valor(categoria):
        if len(cita) >= CITATION_PREFERRED_MIN_CHARS:
            continue
        if _normalizar(valor) not in _normalizar(cita):
            problemas.append(f"  {len(cita)} caracteres: {cita!r} (valor: {valor!r})")

    assert not problemas, "citas cortas que no contienen el dato:\n" + "\n".join(problemas)


@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_los_ejemplos_respetan_el_minimo_duro(categoria: str) -> None:
    """Guarda: `SourceReference` rechaza por debajo de `CITATION_MIN_CHARS`."""
    for cita in _citations_de(categoria):
        assert len(cita) >= CITATION_MIN_CHARS, cita


def test_cada_categoria_tiene_al_menos_un_ejemplo_de_cita() -> None:
    """Si un prompt se queda sin ejemplos, los tests de arriba pasan vacíos."""
    for categoria in CATEGORIAS:
        assert _citations_de(categoria), f"{categoria} no tiene ninguna cita de ejemplo"


def test_el_prompt_base_declara_el_rango_que_valida_el_esquema() -> None:
    """La regla en prosa y la constante del código tienen que decir lo mismo:
    si divergen, los ejemplos vuelven a irse de rango sin que nadie lo note."""
    base = (PROMPTS_DIR / "_base_system.txt").read_text(encoding="utf-8")

    assert f"{CITATION_PREFERRED_MIN_CHARS} y {CITATION_MAX_CHARS} caracteres" in base
    assert str(CITATION_MIN_CHARS) in base


def test_los_ejemplos_json_de_cada_categoria_siguen_siendo_json_valido() -> None:
    """Los ejemplos de salida se editaron a mano para acortar las citas: un
    corchete de menos convierte el ejemplo en ruido para el modelo.

    Se saltean los bloques marcados como contraejemplo, que llevan comentarios
    `//` a propósito.
    """
    for categoria in CATEGORIAS:
        texto = (PROMPTS_DIR / f"{categoria}.txt").read_text(encoding="utf-8")
        for bloque in re.findall(r"```json\n(.*?)```", texto, re.S):
            if "//" in bloque:
                continue
            try:
                json.loads(bloque)
            except json.JSONDecodeError as error:  # pragma: no cover - mensaje
                pytest.fail(f"{categoria}: bloque JSON inválido ({error})\n{bloque[:400]}")
