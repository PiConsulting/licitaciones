"""CTX-05: con varios documentos, el modelo veía un UUID y nada más.

Desde que un análisis acepta pliego + anexos, el encabezado que arma
`_format_chunks` tiene que resolver algo que antes no existía: el modelo debe
saber si está leyendo el pliego o un anexo. Lo único que había era el UUID:

    [Fragmento: F3, Documento: 149d9358-af60-4a65-a101-53c01f19126c, Página: 8, …]

Y la única instrucción sobre varios documentos era "Consolidalo si es
coherente", que presupone que todos pesan igual. En una licitación no pesan
igual: el pliego rige y los anexos son subordinados. Peor: hay anexos que **no
son normativos**. En el PET de Bancor, el `Anexo II Equipamiento Actual
Bancor.xlsx` es el inventario de lo que el Banco YA tiene, y el pliego lo dice
expresamente -- es la BASE del dimensionamiento, no el requerimiento. Un chunk
de ahí, sin rol, se lee como si fuera una exigencia de la licitación.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.extractors.base import _describe_document, _format_chunks

PRINCIPAL = "149d9358-af60-4a65-a101-53c01f19126c"
ANEXO = "e987dc44-0647-430e-b103-e09db1929a79"

ETIQUETAS: dict[str, dict[str, Any]] = {
    PRINCIPAL: {"nombre": "Pliego - Bancor.pdf", "es_principal": True},
    ANEXO: {"nombre": "Anexo II Equipamiento Actual Bancor.xlsx", "es_principal": False},
}


def _chunk(document_id: str, contenido: str = "Texto del fragmento.") -> dict[str, Any]:
    return {
        "document_id": document_id,
        "page_number": 8,
        "section_path": "PLIEGO DE ESPECIFICACIONES TÉCNICAS > 3. Especificaciones técnicas",
        "content": contenido,
        "block_type": "paragraph",
    }


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_el_encabezado_dice_si_es_el_pliego_o_un_anexo() -> None:
    bloque = _format_chunks([_chunk(PRINCIPAL), _chunk(ANEXO)], ETIQUETAS)

    assert "Pliego - Bancor.pdf [PLIEGO PRINCIPAL]" in bloque
    assert "Anexo II Equipamiento Actual Bancor.xlsx [ANEXO]" in bloque


def test_el_uuid_sigue_estando_porque_de_ahi_sale_el_resaltado() -> None:
    """El prompt exige copiarlo en `source_references[].document_id`."""
    bloque = _format_chunks([_chunk(PRINCIPAL)], ETIQUETAS)

    assert PRINCIPAL in bloque


def test_cada_encabezado_dice_su_propio_rol() -> None:
    """Con sólo el UUID los dos encabezados ya eran distintos —36 caracteres de
    hexadecimal—, pero de esa diferencia no se deduce cuál manda. Lo que hace
    falta es que cada uno diga qué es."""
    bloque = _format_chunks([_chunk(PRINCIPAL), _chunk(ANEXO)], ETIQUETAS)
    encabezados = [linea for linea in bloque.splitlines() if linea.startswith("[Fragmento:")]

    assert len(encabezados) == 2
    assert "[PLIEGO PRINCIPAL]" in encabezados[0]
    assert "[ANEXO]" in encabezados[1]


# ---------------------------------------------------------------------------
# Degradación: nada de esto puede romper el análisis de un solo documento
# ---------------------------------------------------------------------------


def test_sin_etiquetas_el_encabezado_queda_como_antes() -> None:
    bloque = _format_chunks([_chunk(PRINCIPAL)])

    assert f"Documento: {PRINCIPAL}," in bloque


def test_un_documento_que_no_esta_en_las_etiquetas_muestra_su_uuid() -> None:
    """Un chunk viejo, o un documento borrado entre la indexación y la
    extracción: se degrada al comportamiento anterior, no se rompe."""
    bloque = _format_chunks([_chunk("uuid-que-no-esta")], ETIQUETAS)

    assert "Documento: uuid-que-no-esta," in bloque


def test_un_documento_sin_nombre_conserva_el_rol() -> None:
    etiquetas = {PRINCIPAL: {"nombre": "", "es_principal": True}}

    assert _describe_document(PRINCIPAL, etiquetas) == f"PLIEGO PRINCIPAL ({PRINCIPAL})"


def test_un_chunk_sin_document_id_no_rompe() -> None:
    assert _describe_document("", ETIQUETAS) == "desconocido"
    assert _describe_document("", None) == "desconocido"


def test_etiquetas_malformadas_se_ignoran() -> None:
    """Si la etiqueta no es un dict no se adivina: se cae al UUID."""
    assert _describe_document(PRINCIPAL, {PRINCIPAL: "Pliego"}) == PRINCIPAL


# ---------------------------------------------------------------------------
# Guardas: el resto del encabezado no cambió
# ---------------------------------------------------------------------------


def test_los_otros_campos_del_encabezado_siguen_igual() -> None:
    bloque = _format_chunks([_chunk(PRINCIPAL)], ETIQUETAS)

    assert "Fragmento: F1" in bloque
    assert "Página: 8" in bloque
    assert "Sección: PLIEGO DE ESPECIFICACIONES TÉCNICAS > 3. Especificaciones técnicas" in bloque
    assert "Tipo: PÁRRAFO" in bloque


def test_una_tabla_se_sigue_marcando_como_tabla() -> None:
    chunk = _chunk(PRINCIPAL)
    chunk["block_type"] = "table"

    assert "Tipo: TABLA" in _format_chunks([chunk], ETIQUETAS)


def test_sin_chunks_devuelve_vacio() -> None:
    assert _format_chunks([], ETIQUETAS) == ""


# ---------------------------------------------------------------------------
# El armado de las etiquetas (rama PostgreSQL, con una sesión falsa)
# ---------------------------------------------------------------------------


class _DocFalso:
    def __init__(self, doc_id: str, filename: str, is_primary: bool) -> None:
        self.id = doc_id
        self.filename = filename
        self.is_primary = is_primary
        self.blob_name = filename


class _QueryFalsa:
    def __init__(self, docs: list[_DocFalso]) -> None:
        self._docs = docs

    def filter(self, *args: Any, **kwargs: Any) -> "_QueryFalsa":
        return self

    def all(self) -> list[_DocFalso]:
        return self._docs


class _SesionFalsa:
    def __init__(self, docs: list[_DocFalso]) -> None:
        self._docs = docs

    def query(self, *args: Any, **kwargs: Any) -> _QueryFalsa:
        return _QueryFalsa(self._docs)


def test_las_etiquetas_salen_de_los_documentos_del_analisis() -> None:
    from analysis.extraction.graph import _build_document_labels

    sesion = _SesionFalsa(
        [
            _DocFalso("a-1", "Pliego - Bancor.pdf", True),
            _DocFalso("b-2", "Anexo II Equipamiento Actual Bancor.xlsx", False),
        ]
    )

    assert _build_document_labels("analisis-1", sesion) == {
        "a-1": {"nombre": "Pliego - Bancor.pdf", "es_principal": True},
        "b-2": {"nombre": "Anexo II Equipamiento Actual Bancor.xlsx", "es_principal": False},
    }


def test_sin_sesion_no_hay_etiquetas_y_el_prompt_degrada() -> None:
    """Las etiquetas son degradables y el mapeo a blob path no.

    `_fetch_analysis_documents` levanta `RuntimeError` en producción sin sesión,
    porque para el highlighting eso sí es fatal. Para el prompt no puede serlo:
    perder los nombres de los documentos no justifica tumbar el análisis, y el
    propio prompt dice qué hacer si el encabezado no trae nombre ni rol.

    Lo atrapó `test_document_mapping_fluye_de_setup_a_synthesize_para_highlights`:
    ese test mockea `_build_document_mapping` y llama a `setup_node` con
    `db_session=None`, así que la primera versión de este fix -- que dejaba
    propagar la excepción -- rompía el arranque del grafo.
    """
    from analysis.extraction.graph import _build_document_labels

    assert _build_document_labels("analisis-3", None) == {}


def test_ningun_documento_designado_principal_queda_registrado(caplog: Any) -> None:
    """No es fatal, pero es una inconsistencia de datos que hay que poder ver:
    alguien subió documentos sin decir cuál es el pliego."""
    import logging

    from analysis.extraction.graph import _build_document_labels

    with caplog.at_level(logging.WARNING):
        _build_document_labels("analisis-2", _SesionFalsa([_DocFalso("c-3", "x.pdf", False)]))

    assert "document_labels_sin_principal" in caplog.text
