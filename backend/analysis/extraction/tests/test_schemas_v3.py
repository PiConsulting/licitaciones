"""
Tests unitarios para schemas v3.

Ejecutar con:
    pytest backend/analysis/extraction/tests/test_schemas_v3.py -v

Cobertura:
- Validadores de campos
- Enums
- Reglas de exclusividad
- Formatos de fecha
- Longitud de citations
"""

import pytest
from pydantic import ValidationError

from analysis.extraction.schemas_v3 import (
    # Base types
    SourceReference,
    ExtractedItem,
    ExtractedData,
    # Garantías
    GarantiaItem,
    TipoGarantia,
    # Plazos
    PlazoItem,
    TipoPlazo,
    # Objeto y alcance
    ObjetoAlcanceItem,
    TipoObjetoAlcance,
    # Requisitos
    RequisitoAdmisibilidadItem,
    TipoRequisito,
    MomentoPresentacion,
    # Criterios
    CriterioEvaluacionItem,
    MetodoAdjudicacion,
    TipoCriterio,
    # Anexos
    AnexoObligatorioItem,
    TipoAnexo,
    # Identificación
    IdentificacionProcedimientoItem,
    TipoIdentificacion,
    # Causales
    CausalRechazoItem,
    TipoCausal,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def valid_source_ref():
    """SourceReference válido de ejemplo."""
    return SourceReference(
        document_id="test-doc-123",
        page_number=5,
        citation="a" * 50  # Min 40 chars
    )


@pytest.fixture
def short_citation_source():
    """SourceReference con citation corta (inválida)."""
    return {
        "document_id": "test",
        "page_number": 1,
        "citation": "Muy corta"  # < 40 chars
    }


# =============================================================================
# TESTS: SourceReference
# =============================================================================

def test_source_reference_valid(valid_source_ref):
    """SourceReference con citation válida (40-300 chars)."""
    assert valid_source_ref.citation == "a" * 50
    assert valid_source_ref.page_number == 5


def test_source_reference_citation_too_short(short_citation_source):
    """Citation < 40 chars debe fallar."""
    with pytest.raises(ValidationError) as exc_info:
        SourceReference(**short_citation_source)
    
    errors = exc_info.value.errors()
    assert any("at least 40" in str(e).lower() for e in errors)


def test_source_reference_citation_too_long():
    """Citation > 300 chars debe fallar."""
    with pytest.raises(ValidationError):
        SourceReference(
            document_id="test",
            page_number=1,
            citation="x" * 301  # Max 300 chars
        )


# =============================================================================
# TESTS: GarantiaItem - Exclusividad monto_porcentaje/monto_valor
# =============================================================================

def test_garantia_monto_porcentaje_only(valid_source_ref):
    """Garantía con solo monto_porcentaje (válido)."""
    garantia = GarantiaItem(
        tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
        monto_porcentaje=5.0,
        monto_valor=None,
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert garantia.monto_porcentaje == 5.0
    assert garantia.monto_valor is None


def test_garantia_monto_valor_only(valid_source_ref):
    """Garantía con solo monto_valor (válido)."""
    garantia = GarantiaItem(
        tipo=TipoGarantia.CUMPLIMIENTO_CONTRATO,
        monto_porcentaje=None,
        monto_valor=100000.0,
        moneda="ARS",
        confidence=0.85,
        source_references=[valid_source_ref]
    )
    assert garantia.monto_valor == 100000.0
    assert garantia.monto_porcentaje is None


def test_garantia_both_montos_fails(valid_source_ref):
    """Garantía con ambos montos debe fallar (mutuamente excluyentes)."""
    with pytest.raises(ValidationError) as exc_info:
        GarantiaItem(
            tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
            monto_porcentaje=5.0,
            monto_valor=100000.0,  # ❌ No permitido
            confidence=0.9,
            source_references=[valid_source_ref]
        )
    
    errors = exc_info.value.errors()
    assert any("mutuamente excluyentes" in str(e).lower() for e in errors)


def test_garantia_monto_porcentaje_out_of_range(valid_source_ref):
    """monto_porcentaje fuera de rango [0-100] debe fallar."""
    with pytest.raises(ValidationError):
        GarantiaItem(
            tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
            monto_porcentaje=150.0,  # > 100
            monto_valor=None,
            confidence=0.9,
            source_references=[valid_source_ref]
        )


def test_garantia_tipo_enum_invalid(valid_source_ref):
    """Tipo de garantía inválido debe fallar."""
    with pytest.raises(ValidationError):
        GarantiaItem(
            tipo="garantia_invalida",  # No existe en enum
            monto_porcentaje=5.0,
            confidence=0.9,
            source_references=[valid_source_ref]
        )


# =============================================================================
# TESTS: PlazoItem - Validación de formato de fecha
# =============================================================================

def test_plazo_fecha_iso_valid(valid_source_ref):
    """Plazo con fecha en formato ISO (válido)."""
    plazo = PlazoItem(
        tipo=TipoPlazo.PRESENTACION_OFERTAS,
        fecha="2026-08-15",  # ✅ YYYY-MM-DD
        hora="10:00",
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert plazo.fecha == "2026-08-15"


def test_plazo_fecha_argentina_format_fails(valid_source_ref):
    """Plazo con fecha en formato argentino debe fallar."""
    with pytest.raises(ValidationError) as exc_info:
        PlazoItem(
            tipo=TipoPlazo.PRESENTACION_OFERTAS,
            fecha="15/08/2026",  # ❌ DD/MM/YYYY
            confidence=0.9,
            source_references=[valid_source_ref]
        )
    
    errors = exc_info.value.errors()
    assert any("yyyy-mm-dd" in str(e).lower() for e in errors)


def test_plazo_fecha_none_valid(valid_source_ref):
    """Plazo sin fecha (con expresion_relativa) es válido."""
    plazo = PlazoItem(
        tipo=TipoPlazo.CONSULTAS,
        fecha=None,
        expresion_relativa="10 días corridos desde la apertura",
        confidence=0.8,
        source_references=[valid_source_ref]
    )
    assert plazo.fecha is None
    assert plazo.expresion_relativa is not None


def test_plazo_tipo_enum_invalid(valid_source_ref):
    """Tipo de plazo inválido debe fallar."""
    with pytest.raises(ValidationError):
        PlazoItem(
            tipo="plazo_inventado",  # No existe en enum
            fecha="2026-08-15",
            confidence=0.9,
            source_references=[valid_source_ref]
        )


# =============================================================================
# TESTS: ObjetoAlcanceItem
# =============================================================================

def test_objeto_alcance_resumen_valid(valid_source_ref):
    """Objeto alcance con tipo resumen_objeto."""
    item = ObjetoAlcanceItem(
        tipo=TipoObjetoAlcance.RESUMEN_OBJETO,
        valor="Provisión de 200 resmas de papel A4",
        metadata={
            "cantidad": 200,
            "unidad_medida": "resmas"
        },
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert item.tipo == TipoObjetoAlcance.RESUMEN_OBJETO
    assert item.metadata["cantidad"] == 200


def test_objeto_alcance_oferta_parcial(valid_source_ref):
    """Objeto alcance con oferta_parcial (valor debe ser 'si' o 'no')."""
    item = ObjetoAlcanceItem(
        tipo=TipoObjetoAlcance.OFERTA_PARCIAL,
        valor="no",  # Texto, no booleano
        confidence=0.85,
        source_references=[valid_source_ref]
    )
    assert item.valor == "no"


# =============================================================================
# TESTS: RequisitoAdmisibilidadItem
# =============================================================================

def test_requisito_documento_valid(valid_source_ref):
    """Requisito tipo documento con metadata."""
    requisito = RequisitoAdmisibilidadItem(
        tipo=TipoRequisito.DOCUMENTO,
        valor="Certificado fiscal para contratar vigente",
        metadata={
            "obligatorio": "si",
            "momento_presentacion": "con_la_oferta",
            "subsanable": "no"
        },
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert requisito.tipo == TipoRequisito.DOCUMENTO
    assert requisito.metadata["obligatorio"] == "si"


def test_requisito_default_metadata(valid_source_ref):
    """Requisito sin metadata explícita debe tener defaults."""
    requisito = RequisitoAdmisibilidadItem(
        tipo=TipoRequisito.CAPACIDAD_MINIMA,
        valor="Facturación anual mínima de $5.000.000",
        confidence=0.8,
        source_references=[valid_source_ref]
    )
    # Defaults definidos en schema
    assert requisito.metadata["obligatorio"] == "no_especificado"
    assert requisito.metadata["momento_presentacion"] == "no_especificado"


# =============================================================================
# TESTS: CriterioEvaluacionItem
# =============================================================================

def test_criterio_metodo(valid_source_ref):
    """Item tipo='metodo' describe el método de adjudicación."""
    criterio = CriterioEvaluacionItem(
        tipo="metodo",
        valor="Puntaje ponderado",
        metadata={
            "metodo": "puntaje_ponderado",
            "puntaje_tecnico_minimo": "70 puntos"
        },
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert criterio.tipo == "metodo"
    assert criterio.metadata["metodo"] == "puntaje_ponderado"


def test_criterio_factor(valid_source_ref):
    """Item tipo='criterio' describe un factor evaluado."""
    criterio = CriterioEvaluacionItem(
        tipo="criterio",
        valor="Precio",
        metadata={
            "tipo_criterio": "precio",
            "ponderacion_porcentaje": 60.0
        },
        confidence=0.85,
        source_references=[valid_source_ref]
    )
    assert criterio.tipo == "criterio"
    assert criterio.metadata["ponderacion_porcentaje"] == 60.0


# =============================================================================
# TESTS: AnexoObligatorioItem
# =============================================================================

def test_anexo_obligatorio_valid(valid_source_ref):
    """Anexo obligatorio con identificador completo."""
    anexo = AnexoObligatorioItem(
        tipo=TipoAnexo.ANEXO,
        valor="Anexo I — Planilla de Cotización",
        metadata={
            "debe_completarse": "si",
            "debe_firmarse": "si"
        },
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert anexo.tipo == TipoAnexo.ANEXO
    assert "Anexo I" in anexo.valor


# =============================================================================
# TESTS: IdentificacionProcedimientoItem
# =============================================================================

def test_identificacion_organismo(valid_source_ref):
    """Identificación de organismo convocante."""
    item = IdentificacionProcedimientoItem(
        tipo=TipoIdentificacion.ORGANISMO_CONVOCANTE,
        valor="Municipalidad de Villa Nueva",
        confidence=0.95,
        source_references=[valid_source_ref]
    )
    assert item.tipo == TipoIdentificacion.ORGANISMO_CONVOCANTE


def test_identificacion_expediente(valid_source_ref):
    """Identificación de expediente administrativo."""
    item = IdentificacionProcedimientoItem(
        tipo=TipoIdentificacion.EXPEDIENTE,
        valor="4521-2026",
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert item.valor == "4521-2026"


# =============================================================================
# TESTS: CausalRechazoItem
# =============================================================================

def test_causal_rechazo_formal(valid_source_ref):
    """Causal de rechazo tipo formal."""
    causal = CausalRechazoItem(
        tipo=TipoCausal.FORMAL,
        valor="Falta de firma del representante legal",
        metadata={
            "es_descalificante": "si",
            "es_subsanable": "no"
        },
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    assert causal.tipo == TipoCausal.FORMAL
    assert causal.metadata["es_descalificante"] == "si"


# =============================================================================
# TESTS: ExtractedData - Contenedor
# =============================================================================

def test_extracted_data_empty():
    """ExtractedData vacío debe inicializar listas vacías."""
    data = ExtractedData()
    assert data.garantias == []
    assert data.plazos_clave == []
    assert data.objeto_alcance == []
    assert data.garantias_extraction_status == "unknown"


def test_extracted_data_with_items(valid_source_ref):
    """ExtractedData con items de varias categorías."""
    garantia = GarantiaItem(
        tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
        monto_porcentaje=5.0,
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    
    plazo = PlazoItem(
        tipo=TipoPlazo.PRESENTACION_OFERTAS,
        fecha="2026-08-15",
        confidence=0.9,
        source_references=[valid_source_ref]
    )
    
    data = ExtractedData(
        garantias=[garantia],
        garantias_extraction_status="success",
        plazos_clave=[plazo],
        plazos_clave_extraction_status="success"
    )
    
    assert len(data.garantias) == 1
    assert len(data.plazos_clave) == 1
    assert data.garantias_extraction_status == "success"


# =============================================================================
# TESTS: Confidence validation
# =============================================================================

def test_confidence_out_of_range_fails(valid_source_ref):
    """Confidence fuera de rango [0-1] debe fallar."""
    with pytest.raises(ValidationError):
        GarantiaItem(
            tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
            monto_porcentaje=5.0,
            confidence=1.5,  # > 1.0
            source_references=[valid_source_ref]
        )


def test_confidence_negative_fails(valid_source_ref):
    """Confidence negativo debe fallar."""
    with pytest.raises(ValidationError):
        PlazoItem(
            tipo=TipoPlazo.PRESENTACION_OFERTAS,
            fecha="2026-08-15",
            confidence=-0.1,  # < 0.0
            source_references=[valid_source_ref]
        )


# =============================================================================
# TESTS: source_references validation
# =============================================================================

def test_source_references_empty_fails(valid_source_ref):
    """source_references vacío debe fallar (min_length=1)."""
    with pytest.raises(ValidationError):
        GarantiaItem(
            tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
            monto_porcentaje=5.0,
            confidence=0.9,
            source_references=[]  # ❌ Min 1 elemento
        )


def test_source_references_multiple_valid(valid_source_ref):
    """Múltiples source_references válidos."""
    ref2 = SourceReference(
        document_id="test-doc-456",
        page_number=7,
        citation="b" * 50
    )
    
    garantia = GarantiaItem(
        tipo=TipoGarantia.MANTENIMIENTO_OFERTA,
        monto_porcentaje=5.0,
        confidence=0.9,
        source_references=[valid_source_ref, ref2]
    )
    
    assert len(garantia.source_references) == 2
