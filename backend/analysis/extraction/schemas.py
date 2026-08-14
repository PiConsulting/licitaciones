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

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# BASE TYPES
# =============================================================================

# Contrato único de longitud de cita. Antes cada capa tenía su propio umbral
# (25 en el verificador de grounding, 40 en la penalización de graph.py, 40-300
# en este schema, "25-300" en el prompt), así que una misma cita literal y
# verificable podía sobrevivir en un pliego y desaparecer -- o hacer explotar
# merge_node con un ValidationError -- en otro, según cuán larga fuera la
# oración citada. La longitud no decide si una cita es válida: eso lo decide
# `_verify_reference_grounded` comprobando que el texto exista literalmente en
# un chunk recuperado. El mínimo solo descarta citas demasiado cortas para ser
# discriminantes ("oferta", "garantía"); el máximo es un límite de
# almacenamiento y se aplica recortando la cita, nunca descartando el ítem.
CITATION_MIN_CHARS = 12
# La cita es lo que la persona lee para verificar de un vistazo que la síntesis
# dice la verdad -- y es TAMBIÉN lo que define el largo del resaltado en el PDF:
# `highlight.py::compute_highlights_for_sources` busca este texto exacto en la
# página, así que una cita de párrafo produce un subrayado de párrafo. No son
# dos cosas independientes.
#
# 300 caracteres daban citas de 2 a 4 renglones (mediana medida sobre un
# análisis real: 129, p90 157, máximo 264) y subrayados del tamaño de un
# párrafo. El objetivo es el fragmento mínimo que prueba el dato: de
# `CITATION_PREFERRED_MIN_CHARS` a `CITATION_MAX_CHARS`.
CITATION_MAX_CHARS = 120

# Umbral de *utilidad*, no de validez: por debajo de esto la cita es verificable
# pero pobre como evidencia para el usuario, así que se intenta reemplazarla por
# un fragmento literal más rico del mismo chunk. Si no se consigue, la cita
# corta se conserva igual -- nunca se descarta el ítem por este umbral.
CITATION_PREFERRED_MIN_CHARS = 40

# Nivel de confianza para categorías sin evidencia. Usado por `_empty_category_narrative()`
# en synthesis.py cuando no se encuentran items útiles para una categoría.
CONFIDENCE_NO_EVIDENCE = "baja"


class SourceReference(BaseModel):
    """Referencia a la fuente en el pliego original."""
    document_id: str
    page_number: int
    citation: str = Field(min_length=CITATION_MIN_CHARS, max_length=CITATION_MAX_CHARS)
    block_id: str | None = Field(
        default=None,
        description="ID del bloque/párrafo fuente. Usado para agrupar múltiples citations del mismo párrafo."
    )
    # ATR-01 (auditoría 2026-08-13): id del chunk que respaldó esta cita,
    # capturado en `_verify_citation_grounding` en el momento en que se
    # verifica el grounding. Es lo que evita que síntesis y highlighting
    # tengan que re-adivinar el origen buscando el texto de la cita de nuevo
    # -- y lo que impide que una frase repetida en dos chunks de la misma
    # página se resuelva al chunk equivocado.
    chunk_id: str | None = Field(
        default=None,
        description="ID del chunk recuperado del que se verificó esta cita.",
    )


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
    # Marca de cita que no se pudo respaldar contra los chunks recuperados.
    # Antes viajaba como la clave suelta `_unverified` en un dict: pydantic la
    # descartaba al reconstruir la narrativa y la fuente llegaba al usuario sin
    # ninguna señal de que no estaba verificada. Como campo declarado, sobrevive
    # la serialización y la persistencia.
    unverified: bool = False
    # ATR-05 (auditoría 2026-08-13): `_resolve_from_evidence` ya escribía este
    # campo "para matching posterior con highlight", pero al no estar declarado
    # pydantic lo descartaba en el `model_validate` -- exactamente el mismo bug
    # que ya se había corregido para `unverified` (ver el comentario de arriba).
    chunk_id: str | None = None
    # Coordenadas de highlight pre-computadas en el PDF usando PyMuPDF.
    # Cada región es un rectángulo: {"x": float, "y": float, "width": float, "height": float}
    # Lista vacía si no se pudo calcular o si PyMuPDF no está disponible.
    # FIX CRÍTICO (2026-08): Resuelve el problema de highlight frágil identificado
    # en la auditoría RAG (falsos positivos/negativos por heurísticas de matching).
    highlight_regions: list[dict[str, float]] = Field(default_factory=list)


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
# NARRATIVE BLOCKS (forma cruda que devuelve el LLM de sintesis)
# =============================================================================
#
# El LLM de sintesis NUNCA autoria `sources` ni `source_ids`: solo indica, por
# `item_refs`, que indices del array de items de entrada (`item_index`)
# respaldan cada bloque/bullet/fila. `synthesis._resolve_narrative_sources`
# traduce esto a un `CategoryNarrative` tomando los `source_references`
# propios de ESOS items -- nunca texto inventado ni citas de otro item -- y
# arma `sources`/`source_ids` en codigo. Esta forma cruda nunca se persiste ni
# llega al frontend.

class RawNarrativeParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str
    confidence_level: ConfidenceLevel
    item_refs: list[int] = Field(default_factory=list)


class RawNarrativeBulletItem(BaseModel):
    text: str
    confidence_level: ConfidenceLevel
    item_refs: list[int] = Field(default_factory=list)


class RawNarrativeBulletListBlock(BaseModel):
    type: Literal["bullet_list"] = "bullet_list"
    items: list[RawNarrativeBulletItem] = Field(default_factory=list)


class RawNarrativeTableRow(BaseModel):
    cells: list[str] = Field(default_factory=list)
    confidence_level: ConfidenceLevel
    item_refs: list[int] = Field(default_factory=list)


class RawNarrativeTableBlock(BaseModel):
    type: Literal["table"] = "table"
    headers: list[str] = Field(default_factory=list)
    rows: list[RawNarrativeTableRow] = Field(default_factory=list)


RawNarrativeBlock = Annotated[
    Union[RawNarrativeParagraphBlock, RawNarrativeBulletListBlock, RawNarrativeTableBlock],
    Field(discriminator="type"),
]


class RawEvidence(BaseModel):
    """Evidencia textual del LLM de sintesis - para highlighting preciso.

    FIX (auditoria 2026-08-13, hallazgos SYN-01 y SYN-04): `text` NO es el
    contenido que se le muestra al usuario. Es un selector: `_stub_for_evidence`
    lo usa para recortar un sub-fragmento DENTRO de la cita ya verificada del
    item que esta evidencia referencia en `item_refs`. Si no cae dentro de
    ninguna de esas citas, se usa la cita verificada completa.

    Por la misma razon, `document_id` y `page_number` son informativos: los
    valores que llegan a la source salen del item verificado, no de estos
    campos. El LLM copiaba mal el UUID del documento y eso alcanzaba para
    perder la evidencia.
    """
    document_id: str
    page_number: int
    text: str = Field(min_length=CITATION_MIN_CHARS)
    claim: str
    item_refs: list[int] = Field(default_factory=list)


class RawCategoryNarrative(BaseModel):
    """Salida cruda del LLM de sintesis: bloques con `item_refs`, sin `sources`.
    
    NUEVO (2026-08-12): Campo `evidence` opcional para highlighting preciso.
    Si está presente, se usa para construir sources en vez de item_refs.
    """
    blocks: list[RawNarrativeBlock] = Field(default_factory=list)
    evidence: list[RawEvidence] = Field(default_factory=list)


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
    PLAZO_EJECUCION = "plazo_ejecucion"  # Plazo de entrega o ejecución del contrato
    ADJUDICACION = "adjudicacion"
    IMPUGNACION = "impugnacion"
    FIRMA_CONTRATO = "firma_contrato"
    # Nuevos tipos específicos para evitar clasificación genérica
    PRESENTACION_ORDEN_PROVISION = "presentacion_orden_provision"  # Plazo para presentarse a firmar orden
    ENTREGA_ORDEN_FIRMADA = "entrega_orden_firmada"  # Plazo para devolver orden firmada
    PLAZO_PAGO = "plazo_pago"  # Plazo para efectuar el pago
    PLAZO_SUBSANACION = "plazo_subsanacion"  # Plazo para subsanar documentación faltante
    PREAVISO_RESCISION = "preaviso_rescision"  # Plazo de preaviso para rescindir contrato
    ACREDITACION_IMPORTACION = "acreditacion_importacion"  # Plazo para acreditar solicitud de importación
    PRESENTACION_FACTURA = "presentacion_factura"  # Plazo para presentar factura
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
    # Texto descriptivo de la garantía. Es el unico lugar donde puede vivir la
    # explicacion de un item `not_applicable` ("Exento: no se exige garantia
    # cuando el monto no supera 100 modulos"), que por definicion no tiene monto.
    # Sin este campo pydantic descartaba en silencio el `valor` que el prompt ya
    # le venia pidiendo al LLM, y la exencion se persistia sin ninguna
    # explicacion para el usuario.
    valor: str | None = None
    monto_porcentaje: float | None = Field(None, ge=0.0, le=100.0)
    monto_valor: float | None = Field(None, ge=0.0)
    moneda: str | None = None
    base_calculo: str | None = None
    sobre_que_se_calcula: str | None = None
    forma_constitucion: str | None = None
    plazo_constitucion: str | None = None
    vigencia: str | None = None

    @model_validator(mode='after')
    def validate_monto_exclusivity(self) -> "GarantiaItem":
        """Valida que monto_porcentaje y monto_valor sean mutuamente excluyentes.

        FIX (auditoría 2026-08-12, flujo RAG/prompts): esto era un
        `@field_validator('monto_porcentaje')` que leía
        `info.data.get('monto_valor')`. En Pydantic v2 los validators de
        campo corren en el orden de declaración y `info.data` solo trae los
        campos YA validados -- como `monto_porcentaje` se declara antes que
        `monto_valor` en esta clase, `monto_valor` nunca estaba todavía en
        `info.data` cuando este validator corría, así que la condición
        `is not None` daba siempre falso y la regla de exclusividad mutua
        nunca se disparaba (verificado: un `GarantiaItem` con AMBOS campos
        seteados se construía sin error). Un `model_validator(mode='after')`
        corre una sola vez con el objeto ya completo, sin depender del orden
        de declaración de los campos.
        """
        if self.monto_porcentaje is not None and self.monto_valor is not None:
            raise ValueError(
                "monto_porcentaje y monto_valor son mutuamente excluyentes. "
                "Solo uno puede tener valor."
            )
        return self


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
    # FIX (2026-08-13): la carátula/portada de muchos pliegos trae un nombre
    # corto entre comillas (ej. "Adquisición de Servidores de aplicaciones y
    # base de datos") que identifica de qué se trata el llamado a simple
    # vista -- distinto del número de procedimiento (que puede no existir
    # todavía, ver la regla de `numero_procedimiento` en el prompt) y
    # distinto del resumen_objeto de `objeto_alcance` (que es una síntesis
    # de 2-4 oraciones, pensada para lectura detallada, no para un título).
    # Sin este campo, un pliego sin número asignado quedaba con un título
    # vacío de contenido ("Licitación Privada" a secas).
    DENOMINACION = "denominacion"


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

    # =============================================================================
    # LEGACY FIELDS - BACKWARD COMPATIBILITY
    # =============================================================================
    # FIX MEDIUM (#4): Campos legacy mantenidos por compatibilidad con frontend.
    #
    # AUDITORÍA US-5.3 (2026-08-12): se confirmó contra `frontend/src` cuáles
    # campos legacy siguen consumiéndose de verdad -- el estado real es
    # DISTINTO por campo, no "todos son fallback seguro de eliminar en Q2 2027"
    # como decía este comentario antes:
    #
    #   - "plazos" y "documentos_requeridos"/"restricciones_participacion":
    #     confirmado SAFE. `frontend/src/services/api/analysisApi.ts`
    #     (`legacyToUiMap`) los lee solo como fallback para análisis viejos
    #     que no tengan todavía el campo canónico -- el camino primario ya usa
    #     "plazos_clave"/"requisitos_admisibilidad". Como `merge_node` escribe
    #     siempre ambos nombres, todo análisis nuevo ya trae el canónico. Plan
    #     Q2 2027 (dejar de escribirlos desde el backend) sigue vigente.
    #
    #   - "datos_procedimiento": NO es un duplicado legacy seguro de eliminar.
    #     El frontend lo usa como categoría PRIMARIA -- `CategoryId` en
    #     `frontend/src/features/analysis-detail/types.ts` lo declara como
    #     valor de primera clase, y es la ÚNICA fuente que puebla
    #     organismo/expediente en el header del análisis
    #     (`NORMALIZE_CATEGORY_IDS` en `analysisApi.ts`). El frontend NUNCA
    #     lee "identificacion_procedimiento" (cero referencias en todo
    #     `frontend/src`). Además "identificacion_procedimiento" no es
    #     equivalente: es un subconjunto filtrado por el enum
    #     `TipoIdentificacion` (ver `graph.py::merge_node`,
    #     `identificacion_canonica`), mientras que "datos_procedimiento"
    #     conserva la lista completa sin filtrar. Eliminar este campo con
    #     el plan viejo (fecha fija, sin depender de que el frontend migre)
    #     rompería el header de cualquier análisis nuevo. Ver plan de
    #     migración de frontend en
    #     `_bmad-output/us-5.3-legacy-fields-migration-plan.md` -- la
    #     eliminación de este campo queda BLOQUEADA hasta que ese trabajo de
    #     frontend se haga, no programada por fecha de calendario.
    #
    # ACCIÓN REQUERIDA:
    #   - "plazos" / "documentos_requeridos" / "restricciones_participacion":
    #     ninguna -- proceder con el retiro planeado en Q2 2027.
    #   - "datos_procedimiento": NO retirar hasta migrar el frontend a
    #     "identificacion_procedimiento" (o a un campo canónico sin filtrar
    #     que preserve el 100% de lo que hoy expone "datos_procedimiento").
    # =============================================================================

    plazos: list[PlazoItem] = Field(
        default_factory=list,
        description="DEPRECATED: Usar 'plazos_clave' en su lugar. Será eliminado en Q2 2027.",
    )
    plazos_extraction_status: str = "unknown"

    datos_procedimiento: list[GenericCategoryItem] = Field(
        default_factory=list,
        description=(
            "NO DEPRECAR TODAVÍA: pese al nombre 'legacy', es la fuente primaria que usa "
            "el frontend para organismo/expediente (nunca lee 'identificacion_procedimiento', "
            "que además es un subconjunto filtrado, no equivalente). Ver "
            "_bmad-output/us-5.3-legacy-fields-migration-plan.md antes de tocar este campo."
        ),
    )
    datos_procedimiento_extraction_status: str = "unknown"

    documentos_requeridos: list[GenericCategoryItem] = Field(
        default_factory=list,
        description="DEPRECATED: Usar 'anexos_obligatorios' en su lugar. Será eliminado en Q2 2027.",
    )
    documentos_extraction_status: str = "unknown"

    # FIX (auditoría US-5.3, 2026-08-12): `merge_node` ya escribía estos tres
    # campos en el dict de `extracted_data`, pero no estaban declarados acá --
    # `ExtractedData(**extracted_data)` los descartaba en silencio (comportamiento
    # default de pydantic con campos no declarados), exactamente el mismo patrón
    # del incidente histórico de `primary_category`/`secondary_categories`. Hoy
    # no cambia nada observable (`merge_node` los escribe siempre vacíos, todavía
    # no hay extractor real para estas categorías), pero sin esto, el día que se
    # implemente un extractor para alguna de las tres, sus datos se perderían en
    # silencio antes de llegar a la API -- igual que pasó antes.
    restricciones_participacion: list[GenericCategoryItem] = Field(default_factory=list)
    restricciones_extraction_status: str = "not_found"
    cronograma_proceso: list[GenericCategoryItem] = Field(default_factory=list)
    cronograma_extraction_status: str = "not_found"
    estimacion_presupuesto: PresupuestoItem | None = None
    presupuesto_extraction_status: str = "not_found"


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
    "NarrativeSource",
    "NarrativeBulletItem",
    "NarrativeTableRow",

    # Narrative (raw LLM output)
    "RawCategoryNarrative",
    "RawNarrativeBlock",
    "RawNarrativeParagraphBlock",
    "RawNarrativeBulletItem",
    "RawNarrativeBulletListBlock",
    "RawNarrativeTableRow",
    "RawNarrativeTableBlock",

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
