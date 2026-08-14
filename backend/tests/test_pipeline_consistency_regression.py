"""Regresiones de consistencia del pipeline entre pliegos distintos.

Cada test de este archivo fija una propiedad que se violaba en produccion y que
hacia que dos pliegos con la MISMA informacion dieran resultados distintos. El
denominador comun de todas: alguna etapa decidia por una heuristica que depende
de como esta redactado o maquetado el documento (largo de una oracion, en que
parte de la pagina cae una tabla, si Azure marco un titulo como titulo) en vez
de decidir por la evidencia.

Analisis reales de referencia:
  A = ea691f19-ea38-4706-b968-0077a576efae  (pliego_04_sin_garantias.pdf, 1 pag)
  B = 9decdba9-cc28-4c73-8fd5-8c452ba4480f  (Pliego Rosario servidores, 10 pags)
"""

from __future__ import annotations

from typing import Any

import pytest

from analysis.extraction.extractors.base import (
    _verify_citation_grounding,
    _verify_reference_grounded,
    clip_citation,
)
from analysis.extraction.graph import merge_node
from analysis.extraction.schemas import (
    CITATION_MAX_CHARS,
    CITATION_MIN_CHARS,
    ExtractedData,
)
from analysis.extraction.synthesis import run_synthesis
from extraction.chunking import classify_chunk_categories, create_chunks
from shared.ports.azure_search import SEARCH_CHUNK_SELECT_FIELDS

# Texto real del pliego_04 (analisis A). La cita que el LLM devolvio para
# objeto_alcance mide 343 caracteres y era descartada solo por eso.
OBJETO_PLIEGO_04 = (
    "La presente Licitación Pública tiene por objeto la contratación del servicio de "
    "vigilancia y seguridad privada, sin armas de fuego, para los edificios de la Agencia "
    "sitos en calle Belgrano 902 y Anexo Alberdi 340, por un plazo de 12 (doce) meses, "
    "incluyendo control de accesos, rondas perimetrales y monitoreo del sistema de cámaras "
    "existente."
)


def _chunk(content: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "document_id": "doc-1",
        "page_number": 1,
        "chunk_index": 0,
        "block_type": "paragraph",
        "table_ref": None,
        "content": content,
    }
    base.update(overrides)
    return base


def _item(citation: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "tipo": "resumen_objeto",
        "valor": "Servicio de vigilancia y seguridad privada",
        "confidence": 0.9,
        "extraction_status": "success",
        "source_references": [{"document_id": "doc-1", "page_number": 1, "citation": citation}],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. El largo de la cita no decide si la evidencia vale
# ---------------------------------------------------------------------------


def test_cita_larga_verbatim_sobrevive_al_grounding() -> None:
    """Caso A/objeto_alcance: cita de 343 chars, literal en el chunk. Antes el
    techo de 300 la rechazaba y la categoria quedaba vacia con status partial."""
    assert len(OBJETO_PLIEGO_04) > CITATION_MAX_CHARS

    chunks = [_chunk(f"1. OBJETO Y ALCANCE\n\n{OBJETO_PLIEGO_04}")]
    items = [_item(OBJETO_PLIEGO_04)]

    _verify_citation_grounding(items, chunks, category="objeto_alcance", correlation_id="corr")

    assert items[0]["extraction_status"] == "success"
    assert items[0]["source_references"], "la evidencia existe literal: no puede quedar sin fuentes"
    assert items[0].get("_warning") != "cita_no_verificada"


def test_cita_corta_verbatim_sobrevive_al_grounding() -> None:
    """Caso B/presupuesto_oficial: 'PRESUPUESTO OFICIAL: $ X' mide 24 chars y
    quedaba un caracter por debajo del piso de 25."""
    citation = "PRESUPUESTO OFICIAL: $ X"
    assert len(citation) == 24

    chunks = [_chunk("ADQUISICIÓN DE: Servidores. PRESUPUESTO OFICIAL: $ X APERTURA:")]
    items = [_item(citation, tipo="presupuesto_oficial", valor="$ X")]

    _verify_citation_grounding(
        items, chunks, category="identificacion_procedimiento", correlation_id="corr"
    )

    assert items[0]["source_references"]


def test_cita_inventada_sigue_siendo_rechazada() -> None:
    """Aflojar el largo no puede aflojar el anti-alucinacion: lo que decide es
    que el texto exista literalmente en un chunk recuperado. Ni la cita ni el
    `valor` del item aparecen en el chunk, asi que tampoco hay rescate posible."""
    chunks = [_chunk(f"1. OBJETO Y ALCANCE\n\n{OBJETO_PLIEGO_04}")]
    items = [
        _item(
            "La garantía de mantenimiento de oferta es del 5% del presupuesto oficial.",
            valor="Garantía de mantenimiento de oferta del 5% constituida por seguro de caución.",
        )
    ]

    _verify_citation_grounding(items, chunks, category="objeto_alcance", correlation_id="corr")

    assert items[0]["source_references"] == []
    assert items[0]["_warning"] == "cita_no_verificada"
    assert items[0]["extraction_status"] == "partial"


def test_cita_de_una_palabra_no_es_evidencia() -> None:
    chunks = [_chunk(f"1. OBJETO Y ALCANCE\n\n{OBJETO_PLIEGO_04}")]
    assert _verify_reference_grounded("oferta", chunks) is False


def test_clip_citation_preserva_el_caracter_literal() -> None:
    """La cita recortada tiene que seguir verificando: si no, el recorte
    convertiria evidencia valida en no verificable al re-analizar."""
    chunks = [_chunk(f"1. OBJETO Y ALCANCE\n\n{OBJETO_PLIEGO_04}")]

    clipped = clip_citation(OBJETO_PLIEGO_04)

    assert len(clipped) <= CITATION_MAX_CHARS
    assert clipped in OBJETO_PLIEGO_04, "el recorte debe ser un prefijo textual, no un resumen"
    assert _verify_reference_grounded(clipped, chunks) is True


def test_grounding_guarda_la_cita_dentro_del_limite_de_persistencia() -> None:
    """Lo que el grounding deja en el item tiene que poder persistirse: si
    excede el maximo, ExtractedData explota y se pierde el analisis entero."""
    chunks = [_chunk(f"1. OBJETO Y ALCANCE\n\n{OBJETO_PLIEGO_04}")]
    items = [_item(OBJETO_PLIEGO_04)]

    _verify_citation_grounding(items, chunks, category="objeto_alcance", correlation_id="corr")

    stored = items[0]["source_references"][0]["citation"]
    assert CITATION_MIN_CHARS <= len(stored) <= CITATION_MAX_CHARS
    ExtractedData(objeto_alcance=[items[0]])  # no debe levantar ValidationError


# ---------------------------------------------------------------------------
# 2. merge_node es un borde de contrato: degrada el dato, no tumba el analisis
# ---------------------------------------------------------------------------


def _merge_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "objeto_alcance": [],
        "objeto_alcance_status": "not_found",
        "requisitos_admisibilidad": [],
        "requisitos_admisibilidad_status": "not_found",
        "plazos": [],
        "plazos_status": "not_found",
        "garantias": [],
        "garantias_status": "not_found",
        "causales": [],
        "causales_status": "not_found",
        "anexos": [],
        "anexos_status": "not_found",
        "criterios": [],
        "criterios_status": "not_found",
        "identificacion": [],
        "identificacion_status": "not_found",
    }
    state.update(overrides)
    return state


def test_una_cita_fuera_de_contrato_no_tumba_las_demas_categorias() -> None:
    """Antes, una sola cita corta hacia que ExtractedData(**...) levantara
    ValidationError dentro de merge_node y se perdian las OCHO categorias."""
    state = _merge_state(
        objeto_alcance=[_item("corta")],  # por debajo del minimo
        objeto_alcance_status="success",
        garantias=[
            {
                "tipo": "mantenimiento_oferta",
                "monto_porcentaje": 1.0,
                "confidence": 0.9,
                "extraction_status": "success",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 3,
                        "citation": "Garantía de mantenimiento de oferta: 1% del presupuesto oficial.",
                    }
                ],
            }
        ],
        garantias_status="success",
    )

    result = merge_node(state)
    data = result["extracted_data"]

    assert data["objeto_alcance"] == [], "el item sin cita utilizable se descarta"
    assert data["objeto_alcance_extraction_status"] == "partial"
    assert len(data["garantias"]) == 1, "la categoria sana no puede verse afectada"


def test_cita_demasiado_larga_se_recorta_en_vez_de_descartarse() -> None:
    state = _merge_state(
        objeto_alcance=[_item(OBJETO_PLIEGO_04)],
        objeto_alcance_status="success",
    )

    data = merge_node(state)["extracted_data"]

    assert len(data["objeto_alcance"]) == 1
    citation = data["objeto_alcance"][0]["source_references"][0]["citation"]
    assert len(citation) <= CITATION_MAX_CHARS
    assert citation in OBJETO_PLIEGO_04


# ---------------------------------------------------------------------------
# 3. merge_node completa los campos canonicos que consume el frontend
# ---------------------------------------------------------------------------


def test_merge_completa_campos_canonicos_y_no_solo_los_legacy() -> None:
    """`identificacion_procedimiento` quedaba SIEMPRE vacio (y los status de
    anexos/criterios en "unknown") porque merge_node escribia solo los nombres
    legacy y pydantic descartaba el resto."""
    identificacion = [
        {
            "tipo": "organismo_convocante",
            "valor": "Agencia Provincial de Administración de Bienes del Estado",
            "confidence": 0.9,
            "extraction_status": "success",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "Organismo: Agencia Provincial de Administración de Bienes del Estado",
                }
            ],
        }
    ]
    anexos = [
        {
            "tipo": "anexo",
            "valor": "Anexo I - Formulario de oferta económica",
            "confidence": 0.8,
            "extraction_status": "success",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "Anexo I — Formulario de oferta económica presentado con la oferta.",
                }
            ],
        }
    ]

    data = merge_node(
        _merge_state(
            identificacion=identificacion,
            identificacion_status="success",
            anexos=anexos,
            anexos_status="success",
        )
    )["extracted_data"]

    assert len(data["identificacion_procedimiento"]) == 1
    assert data["identificacion_procedimiento_extraction_status"] == "success"
    assert data["anexos_obligatorios_extraction_status"] == "success"
    # El campo legacy sigue poblado para no romper consumidores existentes.
    assert len(data["datos_procedimiento"]) == 1


def test_tipo_de_identificacion_fuera_del_enum_no_rompe_el_merge() -> None:
    identificacion = [
        {
            "tipo": "lugar_de_apertura",  # no pertenece a TipoIdentificacion
            "valor": "Santa Fe 660, Rosario",
            "confidence": 0.7,
            "extraction_status": "success",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 1,
                    "citation": "LUGAR: Dirección General de Compras y Suministros, Santa Fe 660.",
                }
            ],
        }
    ]

    data = merge_node(
        _merge_state(identificacion=identificacion, identificacion_status="success")
    )["extracted_data"]

    assert data["identificacion_procedimiento"] == []
    assert len(data["datos_procedimiento"]) == 1, "el dato no se pierde: queda en el campo legacy"


# ---------------------------------------------------------------------------
# 4. La clasificacion de chunks tiene que llegar al indice y volver
# ---------------------------------------------------------------------------


def test_chunks_llevan_categoria_al_indice() -> None:
    """`create_chunks` clasificaba los chunks pero `upload_chunks` no subia esos
    campos: quedaban en null para el 100% de los chunks y el filtro por
    categoria del retrieval no matcheaba nunca."""
    from extraction import ai_search

    blocks = [
        {"page_number": 1, "source_order": 0, "block_type": "paragraph", "table_ref": None,
         "content": "3. GARANTÍAS", "heading_level": 1},
        {"page_number": 1, "source_order": 1, "block_type": "paragraph", "table_ref": None,
         "content": "Garantía de mantenimiento de oferta: 1% del presupuesto oficial."},
    ]
    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    assert chunks[0]["primary_category"] == "garantias"

    uploaded: list[dict[str, Any]] = []

    class _Adapter:
        deleted_analysis_ids: list[str] = []

        def upload_chunks(self, documents: list[dict]) -> None:
            uploaded.extend(documents)

        def delete_analysis_chunks(self, analysis_id: str) -> int:
            # IDX-03 (auditoría 2026-08-13): `upload_chunks` ahora limpia los
            # chunks previos del análisis antes de subir los nuevos, así que
            # este método SÍ se invoca en cada re-indexación.
            self.deleted_analysis_ids.append(analysis_id)
            return 0

    original_build = ai_search._build_adapter
    original_validate = ai_search.validate_index_contract
    ai_search._build_adapter = lambda: _Adapter()  # type: ignore[assignment]
    ai_search.validate_index_contract = lambda: None  # type: ignore[assignment]
    try:
        with_embeddings = [{**chunk, "embedding": [0.0, 0.1]} for chunk in chunks]
        ai_search.upload_chunks(with_embeddings, "analysis-1", "corr-1")
    finally:
        ai_search._build_adapter = original_build  # type: ignore[assignment]
        ai_search.validate_index_contract = original_validate  # type: ignore[assignment]

    assert uploaded, "se tienen que haber subido documentos"
    assert uploaded[0]["primary_category"] == "garantias"
    assert "secondary_categories" in uploaded[0]


def test_retrieval_selecciona_los_campos_de_categoria() -> None:
    """Sin esto, purity_rate en `retrieval_metrics` daba 0.0 siempre y la
    telemetria que detectaria este problema quedaba ciega."""
    assert "primary_category" in SEARCH_CHUNK_SELECT_FIELDS
    assert "secondary_categories" in SEARCH_CHUNK_SELECT_FIELDS


# ---------------------------------------------------------------------------
# 5. US-3.1: parent/child chunking tiene que llegar completo al indice
# ---------------------------------------------------------------------------


_ARTICULO_LARGO_CON_INCISOS = (
    "Los oferentes deberan presentar la totalidad de la documentacion enumerada a "
    "continuacion, en sobre cerrado, dentro del plazo establecido en el presente "
    "pliego de bases y condiciones, bajo apercibimiento de exclusion automatica del "
    "proceso licitatorio sin posibilidad de subsanacion posterior alguna.\n\n"
    "a) Documentacion de personeria juridica del oferente, incluyendo estatuto social "
    "vigente, actas de designacion de autoridades y poder suficiente para obligar a "
    "la sociedad en los terminos de la presente contratacion.\n\n"
    "b) Propuesta economica conforme al modelo adjunto como Anexo II, indicando "
    "precio unitario y total, discriminando impuestos, con vigencia minima de "
    "sesenta dias corridos desde la apertura.\n\n"
    "c) Propuesta tecnica incluyendo cronograma detallado de tareas, metodologia de "
    "trabajo, recursos humanos afectados y antecedentes de trabajos similares "
    "realizados en los ultimos cinco anios."
)


def test_upload_chunks_traduce_indices_de_parent_child_a_ids_completos() -> None:
    """`create_chunks` sólo conoce `chunk_index` (entero, único por documento)
    para parent_chunk_index/child_chunk_indices -- recién `upload_chunks`
    conoce el `analysis_id` necesario para armar los mismos ids compuestos
    (`{analysis_id}--{document_id}--{chunk_index}`) que se usan como `id` de
    documento en Azure Search. Si esto se rompe, la expansión children→parent
    del retrieval (`_expand_children_to_parents`) no encuentra el parent."""
    from extraction import ai_search

    blocks = [
        {"page_number": 1, "source_order": 0, "block_type": "paragraph", "table_ref": None,
         "content": _ARTICULO_LARGO_CON_INCISOS},
    ]
    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    parent = next(c for c in chunks if c["chunk_type"] == "parent")
    children = [c for c in chunks if c["chunk_type"] == "child"]
    assert children, "el articulo de prueba tiene que generar al menos un child"

    uploaded: list[dict[str, Any]] = []

    class _Adapter:
        deleted_analysis_ids: list[str] = []

        def upload_chunks(self, documents: list[dict]) -> None:
            uploaded.extend(documents)

        def delete_analysis_chunks(self, analysis_id: str) -> int:
            # IDX-03 (auditoría 2026-08-13): `upload_chunks` ahora limpia los
            # chunks previos del análisis antes de subir los nuevos, así que
            # este método SÍ se invoca en cada re-indexación.
            self.deleted_analysis_ids.append(analysis_id)
            return 0

    original_build = ai_search._build_adapter
    original_validate = ai_search.validate_index_contract
    ai_search._build_adapter = lambda: _Adapter()  # type: ignore[assignment]
    ai_search.validate_index_contract = lambda: None  # type: ignore[assignment]
    try:
        with_embeddings = [{**chunk, "embedding": [0.0, 0.1]} for chunk in chunks]
        ai_search.upload_chunks(with_embeddings, "analysis-1", "corr-1")
    finally:
        ai_search._build_adapter = original_build  # type: ignore[assignment]
        ai_search.validate_index_contract = original_validate  # type: ignore[assignment]

    by_chunk_index = {doc["chunk_index"]: doc for doc in uploaded}

    parent_doc = by_chunk_index[parent["chunk_index"]]
    assert parent_doc["chunk_type"] == "parent"
    assert parent_doc["parent_chunk_id"] is None
    expected_child_ids = [f"analysis-1--doc-1--{c['chunk_index']}" for c in children]
    assert parent_doc["child_chunk_ids"] == expected_child_ids

    for child in children:
        child_doc = by_chunk_index[child["chunk_index"]]
        assert child_doc["chunk_type"] == "child"
        assert child_doc["parent_chunk_id"] == f"analysis-1--doc-1--{parent['chunk_index']}"
        assert child_doc["child_chunk_ids"] == []


def test_upload_chunks_marca_normal_los_chunks_sin_subdividir() -> None:
    """Los chunks que no se subdividieron (la mayoría) tienen que seguir
    subiendo con chunk_type='normal' y sin parent/child ids -- comportamiento
    idéntico al de antes de US-3.1."""
    from extraction import ai_search

    blocks = [
        {"page_number": 1, "source_order": 0, "block_type": "paragraph", "table_ref": None,
         "content": "3. GARANTÍAS", "heading_level": 1},
        {"page_number": 1, "source_order": 1, "block_type": "paragraph", "table_ref": None,
         "content": "Garantía de mantenimiento de oferta: 1% del presupuesto oficial."},
    ]
    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    uploaded: list[dict[str, Any]] = []

    class _Adapter:
        deleted_analysis_ids: list[str] = []

        def upload_chunks(self, documents: list[dict]) -> None:
            uploaded.extend(documents)

        def delete_analysis_chunks(self, analysis_id: str) -> int:
            # IDX-03 (auditoría 2026-08-13): `upload_chunks` ahora limpia los
            # chunks previos del análisis antes de subir los nuevos, así que
            # este método SÍ se invoca en cada re-indexación.
            self.deleted_analysis_ids.append(analysis_id)
            return 0

    original_build = ai_search._build_adapter
    original_validate = ai_search.validate_index_contract
    ai_search._build_adapter = lambda: _Adapter()  # type: ignore[assignment]
    ai_search.validate_index_contract = lambda: None  # type: ignore[assignment]
    try:
        with_embeddings = [{**chunk, "embedding": [0.0, 0.1]} for chunk in chunks]
        ai_search.upload_chunks(with_embeddings, "analysis-1", "corr-1")
    finally:
        ai_search._build_adapter = original_build  # type: ignore[assignment]
        ai_search.validate_index_contract = original_validate  # type: ignore[assignment]

    assert uploaded
    assert uploaded[0]["chunk_type"] == "normal"
    assert uploaded[0]["parent_chunk_id"] is None
    assert uploaded[0]["child_chunk_ids"] == []


def test_retrieval_selecciona_los_campos_de_parent_child() -> None:
    """US-3.1: sin estos campos en el SELECT, `_expand_children_to_parents`
    nunca detecta un chunk 'child' en los resultados y la expansión a parent
    queda muerta en la práctica (nunca se activa)."""
    assert "chunk_type" in SEARCH_CHUNK_SELECT_FIELDS
    assert "parent_chunk_id" in SEARCH_CHUNK_SELECT_FIELDS
    assert "child_chunk_ids" in SEARCH_CHUNK_SELECT_FIELDS
    assert "id" in SEARCH_CHUNK_SELECT_FIELDS


def test_titulo_en_singular_clasifica_igual_que_en_plural() -> None:
    """Los patrones estaban en plural, asi que un pliego que titula su seccion
    "GARANTÍA DE ADJUDICACIÓN" o "ANEXO I" no matcheaba nada y caia en otra
    categoria por una palabra secundaria del titulo."""
    from extraction.chunking import _classify_by_heading

    assert _classify_by_heading(["3. GARANTÍAS"]) == "garantias"
    assert _classify_by_heading(["Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN"]) == "garantias"
    assert _classify_by_heading(["ANEXO I"]) == "anexos_obligatorios"
    assert _classify_by_heading(["6. ANEXOS OBLIGATORIOS"]) == "anexos_obligatorios"
    assert _classify_by_heading(["5. CAUSAL DE RECHAZO"]) == "causales_rechazo"
    # El desempate por posicion no puede romper el caso legitimo inverso.
    assert _classify_by_heading(["ARTÍCULO 9: ADJUDICACIÓN"]) == "criterios_evaluacion"


def test_categorias_secundarias_no_dependen_del_tamano_del_glossary() -> None:
    """El score se dividia por la cantidad total de terminos de la categoria, asi
    que una categoria con muchos sinonimos no llegaba nunca al umbral."""
    chunk = {
        "heading_path": ["Requisitos"],
        "content": (
            "Presentar certificado de habilitación y antecedentes. "
            "Constituir garantía de mantenimiento de oferta. Completar Anexo I."
        ),
    }

    result = classify_chunk_categories(chunk)

    assert result["primary_category"] == "requisitos_admisibilidad"
    assert "garantias" in result["secondary_categories"]


# ---------------------------------------------------------------------------
# 5. Secciones con el titulo corrido dentro del texto
# ---------------------------------------------------------------------------


# Forma real de la salida de Document Intelligence: `_parse_markdown_blocks` no
# corta en lineas en blanco, asi que TODO el texto entre dos encabezados llega
# como un unico bloque con "\n\n" internos.
BLOQUE_ARTICULO_9_ROSARIO = (
    "Queda debidamente establecido a los fines de comparar las ofertas que se presenten, "
    "que se deberán convertir los precios cotizados a moneda de curso legal.\n\n"
    "La adjudicación se efectuará por ítem, mediante el texto legal correspondiente, que "
    "será notificado en forma fehaciente al adjudicatario.\n\n"
    "Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN: En caso de corresponder, el importe de las "
    "garantías de la contratación y otras que se estipulen deberán ajustarse cada vez que se "
    "verifique un incremento igual o mayor al veinte por ciento (20%)."
)


def test_seccion_con_titulo_corrido_no_queda_sepultada_en_la_anterior() -> None:
    """Caso B: la UNICA clausula de garantias del pliego de Rosario quedaba
    dentro del chunk rotulado "ARTÍCULO 9: ADJUDICACIÓN", porque Azure no marca
    como encabezado un titulo que va corrido con el texto."""
    blocks = [
        {"page_number": 4, "source_order": 0, "block_type": "paragraph", "table_ref": None,
         "content": "ARTÍCULO 9: ADJUDICACIÓN", "heading_level": 2},
        {"page_number": 4, "source_order": 1, "block_type": "paragraph", "table_ref": None,
         "content": BLOQUE_ARTICULO_9_ROSARIO},
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    secciones = {chunk["section_path"] for chunk in chunks}

    assert any("GARANTÍA DE ADJUDICACIÓN" in seccion for seccion in secciones), (
        f"la seccion de garantias sigue sepultada; secciones={secciones}"
    )

    garantia_chunks = [c for c in chunks if "GARANTÍA DE ADJUDICACIÓN" in c["section_path"]]
    assert any("veinte por ciento" in c["content"] for c in garantia_chunks), (
        "el cuerpo del articulo tiene que quedar bajo su propio titulo"
    )


def test_referencia_cruzada_no_parte_el_parrafo() -> None:
    """Contrapartida: mencionar un articulo en medio de una oracion no puede
    crear una seccion nueva."""
    blocks = [
        {"page_number": 4, "source_order": 0, "block_type": "paragraph", "table_ref": None,
         "content": "ARTÍCULO 11: ORDEN DE PROVISIÓN", "heading_level": 2},
        {"page_number": 4, "source_order": 1, "block_type": "paragraph", "table_ref": None,
         "content": (
             "Dentro de los cinco días contados a partir de la notificación mencionada en el "
             "Art. 9, la empresa adjudicataria deberá presentarse ante la oficina."
         )},
    ]

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")

    assert {c["section_path"] for c in chunks} == {"ARTÍCULO 11: ORDEN DE PROVISIÓN"}


def test_membrete_repetido_se_despega_aunque_una_pagina_lo_traiga_fusionado() -> None:
    """En el pliego de Rosario el membrete se filtraba en las paginas 1-9 pero
    en la 10 venia fusionado con "ANEXO II", no coincidia exacto con el de las
    otras paginas y se colaba como ancestro de todos los chunks de esa pagina."""
    membrete = 'Municipalidad de Rosario LICITACIÓN PRIVADA PLIEGO DE CONDICIONES PARTICULARES'
    blocks = []
    for page in (1, 2, 3):
        blocks.append({"page_number": page, "source_order": 0, "block_type": "paragraph",
                       "table_ref": None, "content": membrete, "heading_level": 1})
        blocks.append({"page_number": page, "source_order": 1, "block_type": "paragraph",
                       "table_ref": None, "content": f"Cuerpo de la página {page} del pliego."})
    blocks.append({"page_number": 4, "source_order": 0, "block_type": "paragraph",
                   "table_ref": None, "content": f"{membrete} ANEXO II", "heading_level": 1})
    blocks.append({"page_number": 4, "source_order": 1, "block_type": "paragraph",
                   "table_ref": None, "content": "Tabla de cotización por ítem."})

    chunks = create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")
    pagina_4 = [c for c in chunks if c["page_number"] == 4]

    assert pagina_4
    for chunk in pagina_4:
        assert "Municipalidad de Rosario" not in chunk["section_path"]
        assert chunk["section_path"] == "ANEXO II"


# ---------------------------------------------------------------------------
# 6. Respuesta del LLM: JSON con saltos de linea crudos en las citas
# ---------------------------------------------------------------------------


def test_cita_con_salto_de_linea_crudo_no_rompe_el_parseo() -> None:
    """Las citas son texto copiado literal del pliego y el texto de un PDF trae
    los saltos de linea del maquetado. Si el modelo no los escapa, el JSON es
    invalido y se pierde la categoria entera al agotar los reintentos -- y que
    una cita caiga sobre un salto de renglon depende del maquetado de cada PDF."""
    from analysis.extraction.extractors.base import _parse_json_response

    crudo = '{"garantias": [{"citation": "el importe de las garantías de\nla contratación"}]}'

    parsed = _parse_json_response(crudo)

    assert parsed["garantias"][0]["citation"] == "el importe de las garantías de\nla contratación"


def test_garantia_no_aplicable_conserva_su_explicacion() -> None:
    """Un item `not_applicable` no tiene monto: `valor` es el unico campo que
    explica por que no hay garantia. `GarantiaItem` no lo declaraba, asi que
    pydantic lo descartaba en silencio y la exencion se persistia sin motivo."""
    from analysis.extraction.schemas import GarantiaItem

    item = GarantiaItem(
        tipo="otra",
        valor="El pliego sólo regula el ajuste de garantías en caso de corresponder",
        confidence=0.7,
        extraction_status="not_applicable",
        source_references=[
            {
                "document_id": "doc-1",
                "page_number": 4,
                "citation": "En caso de corresponder, el importe de las garantías de la contratación deberá ajustarse.",
            }
        ],
    )

    assert item.valor == "El pliego sólo regula el ajuste de garantías en caso de corresponder"


def test_categoria_no_aplicable_no_se_agrega_como_not_found() -> None:
    """`not_applicable` ("el pliego habla de garantías y no exige ninguna") es
    una respuesta distinta de `not_found` ("el pliego no habla de garantías"), y
    tiene que sobrevivir hasta el resultado final."""
    garantias = [
        {
            "tipo": "otra",
            "valor": "El pliego sólo prevé garantía técnica del equipamiento, ninguna financiera",
            "confidence": 0.7,
            "extraction_status": "not_applicable",
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 8,
                    "citation": "Los servidores deberán contar con garantía de fábrica de 3 años.",
                }
            ],
        }
    ]

    data = merge_node(_merge_state(garantias=garantias, garantias_status="not_applicable"))[
        "extracted_data"
    ]

    assert len(data["garantias"]) == 1
    assert data["garantias_extraction_status"] == "not_applicable"
    assert data["garantias"][0].get("valor")


# ---------------------------------------------------------------------------
# 7. El filtro por categoria no puede bajar la recall
# ---------------------------------------------------------------------------


def test_la_categoria_prioriza_pero_no_recorta_el_presupuesto(monkeypatch) -> None:
    """Usar la categoría como compuerta dura hacía que un documento con la
    sección mal clasificada recuperara 1 chunk y otro equivalente 25.

    La categoría prioriza (boost sobre el score de Azure) y después se completa
    el MISMO presupuesto top_k con el resto de los candidatos.

    Este test también fija el contrato de RET-02: `_retrieve_with_category_priority`
    NO le pasa ningún argumento de categoría a `search_hybrid`. Si alguien
    reintroduce un filtro duro, `fake_search` revienta con TypeError.
    """
    from analysis.extraction.extractors import base

    # El chunk clasificado en la categoría tiene un score PEOR que varios otros:
    # sin el boost no quedaría primero.
    candidatos = [_chunk(f"parrafo {i}", chunk_index=i, search_score=1.0 - i * 0.01) for i in range(10)]
    candidatos.append(
        _chunk(
            "garantía de mantenimiento de oferta",
            chunk_index=7 + 10,
            search_score=0.95,
            primary_category="garantias",
        )
    )

    llamadas: list[dict[str, Any]] = []

    def fake_search(*, query, analysis_id, top_k, keyword_query):
        llamadas.append({"query": query, "top_k": top_k, "keyword_query": keyword_query})
        return list(candidatos)

    monkeypatch.setattr(base, "search_hybrid", fake_search)

    chunks = base._retrieve_with_category_priority(
        query="garantías exigidas",
        analysis_id="analysis-1",
        top_k=5,
        keyword_query="garantia caucion",
        category="garantias",
        correlation_id="corr-1",
    )

    assert len(llamadas) == 1, "una sola búsqueda: no hay pasada filtrada + backfill"
    assert len(chunks) == 5, "se completa el presupuesto, no se recorta a lo clasificado"
    assert chunks[0]["chunk_index"] == 17, "lo clasificado en la categoría va primero"
    indexes = [chunk["chunk_index"] for chunk in chunks]
    assert len(indexes) == len(set(indexes)), "no se puede duplicar chunks"


# ---------------------------------------------------------------------------
# 8. La fuente mostrada en la sintesis respalda el elemento exacto, no la
#    categoria entera (caso reportado: bullets de "Anexos" citando evidencia
#    de otra seccion del pliego)
# ---------------------------------------------------------------------------


def _anexo_item(citation: str, valor: str) -> dict[str, Any]:
    return {
        "tipo": "anexo",
        "valor": valor,
        "confidence": 0.9,
        "extraction_status": "success",
        "source_references": [{"document_id": "doc-1", "page_number": 3, "citation": citation}],
    }


def test_bloque_con_item_ref_equivocado_no_contamina_la_sintesis_de_anexos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce el bug reportado: la categoria "Anexos Obligatorios" tiene
    varios items, cada uno con su propia cita. Si el LLM de sintesis manda un
    bullet cuyo `item_refs` no corresponde a ningun item real (el equivalente
    de "engancharse" con la evidencia de otro tema), ese bullet se descarta
    entero -- nunca se muestra bajo una cita que no lo respalda."""
    items = [
        _anexo_item(
            "Anexo I — Formulario de oferta económica presentado con la oferta.",
            "Anexo I - Formulario de oferta económica",
        ),
        _anexo_item(
            "Anexo II — Declaración jurada de aptitud para contratar con el Estado.",
            "Anexo II - Declaración jurada de aptitud para contratar",
        ),
    ]

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {
                                "text": "Presentar Anexo I: Formulario de oferta económica.",
                                "confidence_level": "alta",
                                "item_refs": [0],
                            },
                            {
                                "text": "Presentar Anexo II: Declaración jurada de aptitud para contratar.",
                                "confidence_level": "alta",
                                # Indice fuera de rango: simula el defecto observado donde el
                                # bloque queda "enganchado" con evidencia que no es la suya.
                                "item_refs": [99],
                            },
                        ],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    result = run_synthesis(category_key="anexos_obligatorios", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    bullets = narrative.blocks[0].items
    assert len(bullets) == 1, "el bullet sin item_refs valido se descarta entero"
    assert bullets[0].text == "Presentar Anexo I: Formulario de oferta económica."
    assert len(narrative.sources) == 1
    assert narrative.sources[0].citation == items[0]["source_references"][0]["citation"]
    assert "Anexo II" not in narrative.sources[0].citation


def test_ningun_source_queda_huerfano_tras_descartar_bloques_invalidos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        _anexo_item("Anexo I — Planilla de cotización por renglón, firmada por el oferente.", "Anexo I"),
        _anexo_item("Anexo II — Nómina de antecedentes y referencias comerciales.", "Anexo II"),
        _anexo_item("Anexo III — Plan de trabajo y cronograma de entregas propuesto.", "Anexo III"),
    ]

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {"text": "Presentar Anexo I.", "confidence_level": "alta", "item_refs": [0]},
                            {"text": "Sin evidencia real.", "confidence_level": "alta", "item_refs": []},
                            {"text": "Indice inventado.", "confidence_level": "alta", "item_refs": [50]},
                            {"text": "Presentar Anexo III.", "confidence_level": "alta", "item_refs": [2]},
                        ],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    result = run_synthesis(category_key="anexos_obligatorios", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    bullets = narrative.blocks[0].items
    assert [b.text for b in bullets] == ["Presentar Anexo I.", "Presentar Anexo III."]

    referenced_ids = {sid for bullet in bullets for sid in bullet.source_ids}
    source_ids = {s.id for s in narrative.sources}
    assert referenced_ids == source_ids, "toda source mostrada debe estar referenciada por algun bullet"


def test_misma_evidencia_referenciada_por_dos_elementos_se_muestra_una_sola_vez(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cuando UNA sola evidencia (mismo documento+pagina+cita) realmente
    respalda a dos elementos de la sintesis, es correcto reusar la misma
    source -- a diferencia de dos anexos distintos, que nunca deben
    compartir fuente aunque esten en el mismo bloque."""
    citation = "Anexo IV — Constancia de visita al lugar de la obra, firmada por el responsable."
    items = [
        _anexo_item(citation, "Anexo IV"),
        {**_anexo_item(citation, "Anexo IV (duplicado en otro documento)")},
    ]

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "bullet_list",
                        "items": [
                            {"text": "Presentar constancia de visita.", "confidence_level": "alta", "item_refs": [0]},
                            {"text": "Firmarla el responsable técnico.", "confidence_level": "alta", "item_refs": [1]},
                        ],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    result = run_synthesis(category_key="anexos_obligatorios", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert len(narrative.sources) == 1
    bullets = narrative.blocks[0].items
    assert bullets[0].source_ids == bullets[1].source_ids == [narrative.sources[0].id]


def test_categoria_sin_bloques_resolubles_usa_mensaje_canonico_no_el_del_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_anexo_item("Anexo I — Formulario de oferta económica presentado con la oferta.", "Anexo I")]

    def fake_call_llm(*, messages, correlation_id):
        return (
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Texto que el LLM intento colar sin evidencia real.",
                        "confidence_level": "alta",
                        "item_refs": [7],
                    }
                ],
            },
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr("analysis.extraction.extractors.base._call_llm", fake_call_llm)

    result = run_synthesis(category_key="anexos_obligatorios", items=items, correlation_id="corr-1")
    assert result is not None
    narrative, _token_usage = result

    assert narrative.sources == []
    assert len(narrative.blocks) == 1
    assert "Texto que el LLM intento colar sin evidencia real." not in narrative.blocks[0].text
    assert "No se encontró información" in narrative.blocks[0].text
