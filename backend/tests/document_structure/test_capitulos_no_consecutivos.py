"""Auditoría de chunking (Santa Fe, PUBCG): `_normalize_numbered_heading_levels`
reseteaba la secuencia de capítulos ante CUALQUIER sub-heading en el medio, y
un capítulo real siempre tiene sub-secciones entre él y el siguiente -- así que
la función nunca lograba encadenar dos capítulos reales.

Caso real: Azure DI le dio a "2. DE LA CONVOCATORIA" y a "8. Penalidades y
Sanciones" un `heading_level` más profundo que a sus hermanos (1, 3, 4, 5, 6,
7, 9, 10, 11) -- una inconsistencia tipográfica real del PDF fuente. Como la
secuencia se reseteaba en la primera sub-sección ("1.1.", "1.2.", ...), nunca
llegaba a "2." para corregirlo. Consecuencia doble: (a) `heading_path` de todo
el capítulo 2 quedaba colgando de la última sub-sección del capítulo 1, y (b)
"2. DE LA CONVOCATORIA" se cerraba sin haber recibido nunca su propio cuerpo
directo -- generaba un chunk huérfano cuyo contenido era solo el título.
"""

from __future__ import annotations

from typing import Any

from indexing.chunking import create_chunks
from indexing.chunking.headings import _normalize_numbered_heading_levels


def _heading(contenido: str, nivel: int, page: int, source_order: int) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": nivel,
        "page_number": page,
        "source_order": source_order,
    }


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


# Estructura real simplificada del PUBCG: "2." queda en nivel 4 (menos prominencia tipográfica que sus hermanos), separado de "1." por dos sub-secciones reales.
_BLOQUES_PUBCG = [
    _heading("1. DISPOSICIONES GENERALES", 1, 1, 0),
    _heading("1.1. Ámbito de aplicación", 2, 1, 1),
    _parrafo("Las normas de este PUBCG son de aplicación obligatoria.", 1, 2),
    _heading("1.2. Normativa Aplicable", 2, 1, 3),
    _parrafo("Las contrataciones se rigen por la Ley Provincial 12510.", 1, 4),
    _heading("2. DE LA CONVOCATORIA", 4, 2, 5),  # nivel distinto al de sus hermanos
    _heading("2.1. Tipo de convocatoria", 2, 2, 6),
    _parrafo("Según el alcance, la licitación puede ser pública o privada.", 2, 7),
    _heading("3. OFERTAS", 1, 3, 8),
    _heading("3.1. De los Oferentes", 2, 3, 9),
    _parrafo("Los oferentes deberán tener capacidad jurídica para obligarse.", 3, 10),
]


def test_un_capitulo_separado_por_subsecciones_se_normaliza_igual_que_sus_hermanos() -> None:
    normalizados = _normalize_numbered_heading_levels(_BLOQUES_PUBCG)

    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["2. DE LA CONVOCATORIA"] == niveles["1. DISPOSICIONES GENERALES"]
    assert niveles["2. DE LA CONVOCATORIA"] == niveles["3. OFERTAS"]


def test_el_capitulo_deja_de_quedar_anidado_bajo_la_ultima_subseccion_anterior() -> None:
    chunks = create_chunks(_BLOQUES_PUBCG, document_id="doc", correlation_id="corr")

    convocatoria = next(c for c in chunks if "pública o privada" in c["content"])

    assert "1.2. Normativa Aplicable" not in convocatoria["section_path"], (
        f"el capítulo 2 sigue colgando de una sub-sección del capítulo 1: "
        f"{convocatoria['section_path']}"
    )
    assert convocatoria["section_path"] == "2. DE LA CONVOCATORIA > 2.1. Tipo de convocatoria"


def test_el_capitulo_ya_no_genera_un_chunk_solo_titulo_huerfano() -> None:
    """Antes del fix, "2. DE LA CONVOCATORIA" se cerraba (al llegar "3.
    OFERTAS") sin haber recibido nunca su propio cuerpo directo -- quedaba
    huérfano y generaba un chunk cuyo contenido era solo el título."""
    chunks = create_chunks(_BLOQUES_PUBCG, document_id="doc", correlation_id="corr")

    huerfanos = [c for c in chunks if c["content"] == "2. DE LA CONVOCATORIA"]

    assert not huerfanos


def test_una_referencia_fuera_de_orden_no_rompe_la_secuencia_en_curso() -> None:
    """Un heading que matchea "N. TÍTULO" pero rompe el orden esperado (y no
    es un reinicio legítimo con "1.") se ignora sin resetear lo que venía
    acumulado -- ruido, no una señal de que la secuencia real terminó."""
    bloques = [
        _heading("1. DISPOSICIONES GENERALES", 1, 1, 0),
        _heading("5. Referencia suelta mal etiquetada", 3, 1, 1),  # ruido, fuera de orden
        _heading("2. DE LA CONVOCATORIA", 4, 2, 2),
        _heading("3. OFERTAS", 1, 3, 3),
    ]

    normalizados = _normalize_numbered_heading_levels(bloques)
    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["2. DE LA CONVOCATORIA"] == niveles["1. DISPOSICIONES GENERALES"]
    assert niveles["3. OFERTAS"] == niveles["1. DISPOSICIONES GENERALES"]
    # el ruido no forma parte de la secuencia real: se deja como Azure DI lo trajo.
    assert niveles["5. Referencia suelta mal etiquetada"] == 3


def test_una_secuencia_corta_sin_relacion_no_se_toca() -> None:
    """Guarda: si solo hay UN capítulo numerado (nunca llega a formar una
    secuencia de >= 2), no se fuerza ningún nivel."""
    bloques = [_heading("1. ÚNICA SECCIÓN", 3, 1, 0)]

    normalizados = _normalize_numbered_heading_levels(bloques)

    assert normalizados == bloques


# Auditoría de chunking (real: Tribunal Superior de Justicia): el patrón exigía que el número fuera lo primero del heading, así que "Artículo N" nunca entraba a la secuencia y todo lo posterior a "Artículo 16. GARANTÍAS" heredaba GARANTÍAS como ancestro.


def _bloques_articulo_con_prefijo() -> list[dict[str, Any]]:
    bloques = [_heading(f"Artículo {n}. TÍTULO GENÉRICO {n}", 3, 1, n) for n in range(1, 16)]
    bloques.append(_heading("Artículo 16. GARANTÍAS", 3, 1, 16))
    bloques.append(_heading("16.1. CLASES", 4, 2, 17))
    bloques.append(_heading("16.2. FORMAS DE CONSTITUCIÓN", 4, 2, 18))
    bloques.append(_heading("16.3. DEVOLUCIÓN DE LAS GARANTÍAS", 4, 2, 19))
    bloques.extend(
        _heading(f"Artículo {n}. TÍTULO GENÉRICO {n}", 5, 3, 100 + n) for n in range(17, 32)
    )
    return bloques


def test_articulo_con_prefijo_de_palabra_tambien_se_normaliza() -> None:
    normalizados = _normalize_numbered_heading_levels(_bloques_articulo_con_prefijo())
    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["Artículo 17. TÍTULO GENÉRICO 17"] == niveles["Artículo 16. GARANTÍAS"]
    assert niveles["Artículo 31. TÍTULO GENÉRICO 31"] == niveles["Artículo 1. TÍTULO GENÉRICO 1"]
    # las sub-secciones decimales no forman parte de la secuencia de capítulos.
    assert niveles["16.1. CLASES"] == 4


def test_articulo_17_deja_de_heredar_garantias_como_ancestro() -> None:
    bloques = _bloques_articulo_con_prefijo()
    bloques.append(_parrafo("La Municipalidad pagará conforme la normativa vigente.", 3, 200))

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")

    pago = next(c for c in chunks if "pagará conforme" in c["content"])

    assert "Artículo 16. GARANTÍAS" not in pago["section_path"]
    assert pago["section_path"] == "Artículo 31. TÍTULO GENÉRICO 31"


def test_articulo_con_dos_puntos_tambien_matchea() -> None:
    """La convención real usa tanto "Artículo N. TÍTULO" como "ARTÍCULO N:
    TÍTULO" -- ambos separadores tienen que reconocerse."""
    bloques = [
        _heading("ARTÍCULO 1: OBJETO", 2, 1, 0),
        _heading("ARTÍCULO 2: ALCANCE", 4, 1, 1),
        _heading("ARTÍCULO 3: PLAZOS", 2, 1, 2),
    ]

    normalizados = _normalize_numbered_heading_levels(bloques)
    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["ARTÍCULO 2: ALCANCE"] == niveles["ARTÍCULO 1: OBJETO"]


def test_articulo_no_numerico_no_se_confunde_con_la_secuencia() -> None:
    """Guarda: "Artículo Único" no tiene número -- no debe matchear ni
    interferir con la secuencia real."""
    bloques = [
        _heading("Artículo 1. OBJETO", 3, 1, 0),
        _heading("Artículo Único: DISPOSICIÓN TRANSITORIA", 5, 1, 1),
        _heading("Artículo 2. ALCANCE", 3, 1, 2),
    ]

    normalizados = _normalize_numbered_heading_levels(bloques)
    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["Artículo 2. ALCANCE"] == niveles["Artículo 1. OBJETO"]
    assert niveles["Artículo Único: DISPOSICIÓN TRANSITORIA"] == 5
