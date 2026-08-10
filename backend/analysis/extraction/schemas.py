"""
Schemas Pydantic específicos por categoría para extracción estructurada.

Este módulo define los modelos de datos para cada categoría de extracción
del sistema CedIA. Los prompts v3 referencian estos schemas en lugar de
duplicar la estructura JSON.

Estructura:
- Enums: Tipos válidos por categoría
- Items: Schemas específicos con validación
- ExtractedData: Contenedor de todas las categorías
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# BASE TYPES
# =============================================================================

class SourceReference(BaseModel):
    """Referencia a la fuente en el pliego original."""
    document_id: str
    page_number: int
    citation: str = Field(min_length=40, max_length=300)


ConfidenceLevel = Literal["alta", "media", "baja"]
ExtractionStatus = Literal["success", "failed", "not_found", "partial", "not_applicable"]


class ExtractedItem(BaseModel):
    """Base para todos los items extraídos."""
    confidence: float = Field(ge=0.0, le=1.0)
    source_references: list[SourceReference] = Field(min_length=1)
    extraction_status: ExtractionStatus = "success"


# =============================================================================
# NARRATIVE BLOCKS (para respuesta en lenguaje natural)
# =============================================================================

class NarrativeSource(BaseModel):
    """Fuente deduplicada que respalda uno o mas bloques de una CategoryNarrative."""
    id: int
    document_id: str
    page_number: int
    citation: str


class NarrativeParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str
    confidence_level: ConfidenceLevel
    source_ids: list[int] = Field(default_factory=list)


class NarrativeBulletItem(BaseModel):
    text: str
    confidence_level: ConfidenceLevel
    source_ids: list[int] = Field(default_factory=list)


class NarrativeBulletListBlock(BaseModel):
    type: Literal["bullet_list"] = "bullet_list"
    items: list[NarrativeBulletItem] = Field(default_factory=list)


class NarrativeTableRow(BaseModel):
    cells: list[str] = Field(default_factory=list)
    confidence_level: ConfidenceLevel
    source_ids: list[int] = Field(default_factory=list)


class NarrativeTableBlock(BaseModel):
    type: Literal["table"] = "table"
    headers: list[str] = Field(default_factory=list)
    rows: list[NarrativeTableRow] = Field(default_factory=list)


NarrativeBlock = Annotated[
    Union[NarrativeParagraphBlock, NarrativeBulletListBlock, NarrativeTableBlock],
    Field(discriminator="type"),
]


class CategoryNarrative(BaseModel):
    """Respuesta de experto para una categoria: bloques en lenguaje natural."""
    blocks: list[NarrativeBlock] = Field(default_factory=list)
    sources: list[NarrativeSource] = Field(default_factory=list)


# =============================================================================
# CATEGORÍA: PLAZOS CLAVE
# =============================================================================

class TipoPlazo(str, Enum):
    """Tipos de plazos según el dominio de licitaciones argentinas."""
    PRESENTACION_OFERTAS = "presentacion_ofertas"
    APERTURA_OFERTAS = "apertura_ofertas"
    CONSULTAS = "consultas"
    RESPUESTA_CONSULTAS = "respuesta_consultas"
    VISITA_LUGAR = "visita_lugar"
    MANTENIMIENTO_OFERTA = "mantenimiento_oferta"
    ADJUDICACION = "adjudicacion"
    IMPUGNACION = "impugnacion"
    FIRMA_CONTRATO = "firma_contrato"
    OTRO = "otro"


class PlazoItem(ExtractedItem):
    """Item de plazo con fecha, hora y opciones de prórroga."""
    tipo: TipoPlazo
    fecha: str | None = Field(None, description="Formato ISO YYYY-MM-DD")
    hora: str | None = Field(None, description="Formato HH:MM")
    expresion_relativa: str | None = Field(
        None,
        description="Ej: '10 días corridos desde la apertura' - NO calcular fecha"
    )
    texto_original: str | None = None
    prorrogable: Literal["si", "no", "no_especificado"] | None = None
    lugar: str | None = None

    @field_validator('fecha')
    def validate_fecha_format(cls, v):
        """Valida formato ISO de fecha."""
        if v and not v.count('-') == 2:
            raise ValueError("Fecha debe estar en formato YYYY-MM-DD")
        return v


# =============================================================================
# CATEGORÍA: GARANTÍAS
# =============================================================================

class TipoGarantia(str, Enum):
    """Tipos de garantías financieras en licitaciones."""
    MANTENIMIENTO_OFERTA = "mantenimiento_oferta"
    CUMPLIMIENTO_CONTRATO = "cumplimiento_contrato"
    ANTICIPO = "anticipo"
    FONDO_REPARO = "fondo_reparo"
    POR_VICIOS_OCULTOS = "por_vicios_ocultos"
    BUEN_USO_ANTICIPO = "buen_uso_anticipo"
    OTRA = "otra"


class GarantiaItem(ExtractedItem):
    """
    Item de garantía con validación de exclusividad monto_porcentaje/monto_valor.
    
    REGLA CRÍTICA: monto_porcentaje y monto_valor son mutuamente excluyentes.
    Solo uno puede tener valor, el otro debe ser None.
    """
    tipo: TipoGarantia
    monto_porcentaje: float | None = Field(None, ge=0.0, le=100.0)
    monto_valor: float | None = Field(None, ge=0.0)
    moneda: str | None = None
    base_calculo: str | None = None
    sobre_que_se_calcula: str | None = None
    forma_constitucion: str | None = None
    plazo_constitucion: str | None = None
    vigencia: str | None = None

    @field_validator('monto_porcentaje')
    def validate_monto_exclusivity(cls, v, info):
        """Valida que monto_porcentaje y monto_valor sean mutuamente excluyentes."""
        if v is not None and info.data.get('monto_valor') is not None:
            raise ValueError(
                "monto_porcentaje y monto_valor son mutuamente excluyentes. "
                "Solo uno puede tener valor."
            )
        return v


# =============================================================================
# CATEGORÍA: OBJETO Y ALCANCE
# =============================================================================

class TipoObjetoAlcance(str, Enum):
    """Tipos de datos en objeto y alcance."""
    RESUMEN_OBJETO = "resumen_objeto"
    MODALIDAD = "modalidad"
    ITEM = "item"
    OFERTA_PARCIAL = "oferta_parcial"
    OFERTA_ALTERNATIVA = "oferta_alternativa"
    LUGAR_ENTREGA = "lugar_entrega"
    PLAZO_EJECUCION = "plazo_ejecucion"


class ObjetoAlcanceItem(ExtractedItem):
    """Item de objeto y alcance con metadata opcional."""
    tipo: TipoObjetoAlcance
    valor: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Campos opcionales: cantidad, unidad_medida, renglon"
    )


# =============================================================================
# CATEGORÍA: REQUISITOS DE ADMISIBILIDAD
# =============================================================================

class TipoRequisito(str, Enum):
    """Tipos de requisitos de admisibilidad."""
    DOCUMENTO = "documento"
    INHABILITACION = "inhabilitacion"
    INCOMPATIBILIDAD = "incompatibilidad"
    SANCION_VIGENTE = "sancion_vigente"
    CAPACIDAD_MINIMA = "capacidad_minima"
    EXPERIENCIA_MINIMA = "experiencia_minima"
    INSCRIPCION_REGISTRO = "inscripcion_registro"
    OTRA = "otra"


class MomentoPresentacion(str, Enum):
    """Momento de presentación del requisito."""
    CON_LA_OFERTA = "con_la_oferta"
    PREVIO_APERTURA = "previo_apertura"
    PRE_ADJUDICACION = "pre_adjudicacion"
    POST_ADJUDICACION = "post_adjudicacion"
    NO_ESPECIFICADO = "no_especificado"


class RequisitoAdmisibilidadItem(ExtractedItem):
    """Item de requisito de admisibilidad con metadata de obligatoriedad."""
    tipo: TipoRequisito
    valor: str
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "obligatorio": "no_especificado",
            "momento_presentacion": "no_especificado",
            "subsanable": "no_especificado"
        }
    )


# =============================================================================
# CATEGORÍA: CRITERIOS DE EVALUACIÓN
# =============================================================================

class MetodoAdjudicacion(str, Enum):
    """Métodos de adjudicación en licitaciones argentinas."""
    MENOR_PRECIO = "menor_precio"
    PUNTAJE_PONDERADO = "puntaje_ponderado"
    MEJOR_RELACION_PRECIO_CALIDAD = "mejor_relacion_precio_calidad"
    POR_RENGLON = "por_renglon"
    SOBRE_CERRADO = "sobre_cerrado"
    SUBASTA_INVERSA = "subasta_inversa"
    OTRO = "otro"
    NO_ESPECIFICADO = "no_especificado"


class TipoCriterio(str, Enum):
    """Tipos de criterios evaluados."""
    PRECIO = "precio"
    TECNICO = "tecnico"
    EXPERIENCIA = "experiencia"
    PLAZO = "plazo"
    SUSTENTABILIDAD = "sustentabilidad"
    OTRO = "otro"
    NO_ESPECIFICADO = "no_especificado"


class CriterioEvaluacionItem(ExtractedItem):
    """
    Item de criterio de evaluación.
    
    ESTRUCTURA:
    - UN item tipo="metodo" describe el método de adjudicación
    - N items tipo="criterio" describen los factores evaluados
    """
    tipo: Literal["metodo", "criterio"]
    valor: str
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "metodo": "no_especificado",
            "ponderacion_porcentaje": None,
            "formula": None,
            "puntaje_tecnico_minimo": None,
            "tipo_criterio": "no_especificado"
        }
    )


# =============================================================================
# CATEGORÍA: ANEXOS OBLIGATORIOS
# =============================================================================

class TipoAnexo(str, Enum):
    """Tipos de anexos obligatorios."""
    ANEXO = "anexo"
    FORMULARIO = "formulario"
    PLANILLA = "planilla"
    DECLARACION_JURADA = "declaracion_jurada"
    OTRO = "otro"


class AnexoObligatorioItem(ExtractedItem):
    """Item de anexo obligatorio (formularios provistos por el pliego)."""
    tipo: TipoAnexo
    valor: str = Field(description="Identificador completo: 'Anexo I — Planilla de Cotización'")
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "debe_completarse": "no_especificado",
            "debe_firmarse": "no_especificado",
            "presente_en_documentos_subidos": "no_especificado"
        }
    )


# =============================================================================
# CATEGORÍA: IDENTIFICACIÓN DEL PROCEDIMIENTO
# =============================================================================

class TipoIdentificacion(str, Enum):
    """Tipos de datos de identificación del procedimiento."""
    ORGANISMO_CONVOCANTE = "organismo_convocante"
    EXPEDIENTE = "expediente"
    NUMERO_PROCEDIMIENTO = "numero_procedimiento"
    TIPO_PROCEDIMIENTO = "tipo_procedimiento"
    PRESUPUESTO_OFICIAL = "presupuesto_oficial"
    JURISDICCION = "jurisdiccion"


class IdentificacionProcedimientoItem(ExtractedItem):
    """Item de identificación del procedimiento."""
    tipo: TipoIdentificacion
    valor: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# CATEGORÍA: CAUSALES DE RECHAZO
# =============================================================================

class TipoCausal(str, Enum):
    """Tipos de causales de rechazo."""
    FORMAL = "formal"
    TECNICA = "tecnica"
    ECONOMICA = "economica"
    LEGAL = "legal"
    ETICA = "etica"
    OTRA = "otra"


class CausalRechazoItem(ExtractedItem):
    """Item de causal de rechazo (consecuencias de incumplimiento)."""
    tipo: TipoCausal
    valor: str
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "es_descalificante": "no_especificado",
            "es_subsanable": "no_especificado"
        }
    )


# =============================================================================
# LEGACY: Schemas genéricos (mantener compatibilidad)
# =============================================================================

class GenericCategoryItem(ExtractedItem):
    """Schema genérico para categorías sin schema específico (legacy)."""
    tipo: str | None = None
    valor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresupuestoItem(ExtractedItem):
    """Item de presupuesto (legacy)."""
    monto: float | None = None
    moneda: str | None = None
    forma_pago: str | None = None
    ajustes: str | None = None


# =============================================================================
# CONTENEDOR PRINCIPAL
# =============================================================================

class ExtractedData(BaseModel):
    """
    Contenedor de todas las categorías extraídas.
    
    Cada categoría tiene:
    - items: lista de items extraídos (con schema específico)
    - extraction_status: estado global de la extracción
    - narrative: respuesta en lenguaje natural (opcional)
    """
    
    # Objeto y Alcance
    objeto_alcance: list[ObjetoAlcanceItem] = Field(default_factory=list)
    objeto_alcance_extraction_status: str = "unknown"
    objeto_alcance_narrative: CategoryNarrative | None = None

    # Requisitos de Admisibilidad
    requisitos_admisibilidad: list[RequisitoAdmisibilidadItem] = Field(default_factory=list)
    requisitos_admisibilidad_extraction_status: str = "unknown"
    requisitos_admisibilidad_narrative: CategoryNarrative | None = None

    # Plazos Clave
    plazos_clave: list[PlazoItem] = Field(default_factory=list)
    plazos_clave_extraction_status: str = "unknown"
    plazos_clave_narrative: CategoryNarrative | None = None

    # Garantías
    garantias: list[GarantiaItem] = Field(default_factory=list)
    garantias_extraction_status: str = "unknown"
    garantias_narrative: CategoryNarrative | None = None

    # Causales de Rechazo
    causales_rechazo: list[CausalRechazoItem] = Field(default_factory=list)
    causales_extraction_status: str = "unknown"
    causales_rechazo_narrative: CategoryNarrative | None = None

    # Criterios de Evaluación
    criterios_evaluacion: list[CriterioEvaluacionItem] = Field(default_factory=list)
    criterios_evaluacion_extraction_status: str = "unknown"
    criterios_evaluacion_narrative: CategoryNarrative | None = None

    # Anexos Obligatorios
    anexos_obligatorios: list[AnexoObligatorioItem] = Field(default_factory=list)
    anexos_obligatorios_extraction_status: str = "unknown"
    anexos_obligatorios_narrative: CategoryNarrative | None = None

    # Identificación del Procedimiento
    identificacion_procedimiento: list[IdentificacionProcedimientoItem] = Field(default_factory=list)
    identificacion_procedimiento_extraction_status: str = "unknown"
    identificacion_procedimiento_narrative: CategoryNarrative | None = None

    # Legacy fields (backward compatibility)
    plazos: list[PlazoItem] = Field(default_factory=list)
    plazos_extraction_status: str = "unknown"

    datos_procedimiento: list[GenericCategoryItem] = Field(default_factory=list)
    datos_procedimiento_extraction_status: str = "unknown"

    documentos_requeridos: list[GenericCategoryItem] = Field(default_factory=list)
    documentos_extraction_status: str = "unknown"


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Base types
    "SourceReference",
    "ConfidenceLevel",
    "ExtractionStatus",
    "ExtractedItem",
    
    # Narrative
    "CategoryNarrative",
    "NarrativeBlock",
    "NarrativeParagraphBlock",
    "NarrativeBulletListBlock",
    "NarrativeTableBlock",
    
    # Categorías específicas
    "PlazoItem",
    "TipoPlazo",
    "GarantiaItem",
    "TipoGarantia",
    "ObjetoAlcanceItem",
    "TipoObjetoAlcance",
    "RequisitoAdmisibilidadItem",
    "TipoRequisito",
    "MomentoPresentacion",
    "CriterioEvaluacionItem",
    "MetodoAdjudicacion",
    "TipoCriterio",
    "AnexoObligatorioItem",
    "TipoAnexo",
    "IdentificacionProcedimientoItem",
    "TipoIdentificacion",
    "CausalRechazoItem",
    "TipoCausal",
    
    # Legacy
    "GenericCategoryItem",
    "PresupuestoItem",
    
    # Container
    "ExtractedData",
]
