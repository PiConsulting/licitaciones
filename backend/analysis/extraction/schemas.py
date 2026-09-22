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
import re
from typing import Annotated, Any, Literal, Union
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CITATION_MIN_CHARS = 12

CITATION_MAX_CHARS = 120


CITATION_PREFERRED_MIN_CHARS = 40


CONFIDENCE_NO_EVIDENCE = "baja"


class SourceReference(BaseModel):
    """Referencia a la fuente en el pliego original."""

    document_id: str
    page_number: int
    citation: str = Field(min_length=CITATION_MIN_CHARS, max_length=CITATION_MAX_CHARS)
    block_id: str | None = Field(
        default=None,
        description="ID del bloque/párrafo fuente. Usado para agrupar múltiples citations del mismo párrafo.",
    )

    chunk_id: str | None = Field(
        default=None,
        description="ID del chunk recuperado del que se verificó esta cita.",
    )

    citation_llm: str | None = Field(
        default=None,
        description="La cita tal como la emitio el LLM, antes de cualquier reescritura.",
    )
    citation_origin: Literal["llm", "ensanchada", "rescatada"] | None = Field(
        default=None,
        description=(
            "'llm': la cita mostrada es la que emitio el modelo. "
            "'ensanchada': se amplio con texto del mismo chunk para que se lea sola. "
            "'rescatada': la cita del modelo NO verifico y se reemplazo por otro "
            "texto literal del item -- el item baja a `partial`."
        ),
    )

    filename: str | None = Field(
        default=None,
        description="Nombre del archivo del que sale la cita. None si no se pudo resolver.",
    )
    is_primary: bool | None = Field(
        default=None,
        description="True si la cita sale del pliego principal, False si sale de un anexo.",
    )


NOT_ANALYZED_STATUS = "not_analyzed"

ConfidenceLevel = Literal["alta", "media", "baja"]
ExtractionStatus = Literal["success", "failed", "not_found", "partial", "not_applicable"]


class ExtractedItem(BaseModel):
    """Base para todos los items extraídos."""

    confidence: float = Field(ge=0.0, le=1.0)

    confidence_llm: float | None = Field(default=None, ge=0.0, le=1.0)
    # FIX 2026-09-03: sin min_length=1 -- un item sin fuentes (placeholder "not_found", o
    # cita no verificable) moría silenciosamente en pydantic antes de que `_drop_items_without_sources` pudiera decidir qué hacer con él.
    source_references: list[SourceReference] = Field(default_factory=list)
    extraction_status: ExtractionStatus = "success"


class NarrativeSource(BaseModel):
    """Fuente deduplicada que respalda uno o mas bloques de una CategoryNarrative."""

    id: int
    document_id: str
    page_number: int
    citation: str

    unverified: bool = False

    chunk_id: str | None = None

    highlight_regions: list[dict[str, float]] = Field(default_factory=list)

    filename: str | None = None
    is_primary: bool | None = None

    highlight_unavailable_reason: str | None = None


class NarrativeParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str
    confidence_level: ConfidenceLevel
    source_ids: list[int] = Field(default_factory=list)


class NarrativeBulletItem(BaseModel):
    text: str
    resumen: str | None = None
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


class RawNarrativeParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str
    confidence_level: ConfidenceLevel
    item_refs: list[int] = Field(default_factory=list)


class RawNarrativeBulletItem(BaseModel):
    text: str
    resumen: str | None = None
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
    """Evidencia textual del LLM de sintesis - para highlighting preciso."""

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


class PlazoItem(ExtractedItem):
    """Item de plazo con fecha, hora y opciones de prórroga.

    FIX (2026-08-22): Se elimina `tipo` (antes un enum cerrado de 17 valores,
    `TipoPlazo`). Motivo: el vocabulario de "qué plazo es" varía de pliego a
    pliego, así que forzar una taxonomía fija llevaba al LLM a fallar la
    clasificación y, en la práctica, la enorme mayoría de los ítems terminaba
    cayendo en el catch-all `"otro"` vía `_canonical_plazo_tipo` (ver
    `graph.py`) -- un título que no dice nada y que además hacía que ítems sin
    relación entre sí quedaran agrupados bajo el mismo balde, generando falsos
    "conflictos" (fechas distintas para un `tipo="otro"` compartido por
    plazos que no tenían nada que ver uno con otro).

    Se reemplaza por `referencia`: un título corto en lenguaje libre (NO una
    lista cerrada) de A QUÉ plazo se refiere. La idea es la misma que ya regía
    `texto_original` (descripción autocontenida, sin depender de una
    taxonomía) pero pensada como título corto para mostrar en la UI en vez de
    un párrafo completo.
    """

    referencia: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description=(
            "Título corto (3-10 palabras) de A QUÉ plazo se refiere, en lenguaje "
            "libre -- NO elegido de una lista fija. Ej: 'Presentación de ofertas', "
            "'Plazo de entrega de bienes', 'Pago al proveedor', 'Plazo para retirar "
            "muestras de laboratorio'. Debe poder leerse solo, sin el resto del ítem."
        ),
    )
    fecha: str | None = Field(None, description="Formato ISO YYYY-MM-DD")
    hora: str | None = Field(None, description="Formato HH:MM")
    expresion_relativa: str | None = Field(
        None, description="Ej: '10 días corridos desde la apertura' - NO calcular fecha"
    )
    texto_original: str = Field(
        ...,
        min_length=CITATION_MIN_CHARS,
        description=(
            "OBLIGATORIO. Descripción completa del plazo con contexto suficiente "
            "para entender QUÉ plazo es, CUÁNDO se cuenta, y QUIÉN lo ejecuta. "
            "Debe ser auto-contenida y comprensible sin necesidad del campo tipo."
        ),
    )
    prorrogable: Literal["si", "no", "no_especificado"] | None = None
    lugar: str | None = None

    @field_validator("fecha")
    def validate_fecha_format(cls, v):
        """Valida formato ISO de fecha."""
        if v and not v.count("-") == 2:
            raise ValueError("Fecha debe estar en formato YYYY-MM-DD")
        return v


class TipoGarantia(str, Enum):
    """Tipos de garantías financieras en licitaciones."""

    MANTENIMIENTO_OFERTA = "mantenimiento_oferta"
    CUMPLIMIENTO_CONTRATO = "cumplimiento_contrato"
    ANTICIPO = "anticipo"
    CONTRAGARANTIA = "contragarantia"
    IMPUGNACION = "impugnacion"
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
    valor: str | None = None
    # le=100.0 original descartaba contragarantías reales (150%+ del anticipo, caso real Santa Fe); el techo es solo para errores de unidad, no para limitar el negocio.
    monto_porcentaje: float | None = Field(None, ge=0.0, le=1000.0)
    monto_valor: float | None = Field(None, ge=0.0)
    moneda: str | None = None
    base_calculo: str | None = None
    sobre_que_se_calcula: str | None = None
    forma_constitucion: str | None = None
    plazo_constitucion: str | None = None
    vigencia: str | None = None

    @model_validator(mode="after")
    def validate_monto_exclusivity(self) -> "GarantiaItem":
        """Valida que monto_porcentaje y monto_valor sean mutuamente excluyentes."""
        if self.monto_porcentaje is not None and self.monto_valor is not None:
            raise ValueError(
                "monto_porcentaje y monto_valor son mutuamente excluyentes. "
                "Solo uno puede tener valor."
            )
        return self


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
        default_factory=dict, description="Campos opcionales: cantidad, unidad_medida, renglon"
    )


class TipoRequisito(str, Enum):
    """Tipos de requisitos de admisibilidad."""

    DOCUMENTO = "documento"
    INHABILITACION = "inhabilitacion"
    INCOMPATIBILIDAD = "incompatibilidad"
    SANCION_VIGENTE = "sancion_vigente"
    CAPACIDAD_MINIMA = "capacidad_minima"
    EXPERIENCIA_MINIMA = "experiencia_minima"
    INSCRIPCION_REGISTRO = "inscripcion_registro"
    # Certificación exigida para admisibilidad (ISO, partner, organismo técnico); NO la ficha técnica descriptiva (eso es objeto/alcance).
    CERTIFICACION = "certificacion"
    # Condición técnica mínima obligatoria y EXCLUYENTE (inadmisible si no se cumple); se distingue por el lenguaje de obligación+exclusión, no por el tema.
    REQUISITO_TECNICO_EXCLUYENTE = "requisito_tecnico_excluyente"
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
            "subsanable": "no_especificado",
        }
    )


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
            "tipo_criterio": "no_especificado",
        }
    )


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
            "presente_en_documentos_subidos": "no_especificado",
        }
    )


class TipoIdentificacion(str, Enum):
    """Tipos de datos de identificación del procedimiento."""

    ORGANISMO_CONVOCANTE = "organismo_convocante"
    EXPEDIENTE = "expediente"
    NUMERO_PROCEDIMIENTO = "numero_procedimiento"
    TIPO_PROCEDIMIENTO = "tipo_procedimiento"
    PRESUPUESTO_OFICIAL = "presupuesto_oficial"
    JURISDICCION = "jurisdiccion"
    DENOMINACION = "denominacion"
    # Agregados: el golden de varios pliegos pedía datos de contacto/consulta sin ítem que los recibiera.
    CANAL_CONSULTAS = "canal_consultas"  # domicilio electrónico de notificaciones, correo de consultas
    LUGAR_CONSULTA_PLIEGO = "lugar_consulta_pliego"  # dónde retirar/consultar el pliego


class IdentificacionProcedimientoItem(ExtractedItem):
    """Item de identificación del procedimiento."""

    tipo: TipoIdentificacion
    valor: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TipoCriterioPreview(str, Enum):
    """Criterios de preview acordados para la fase 1."""

    MANTENIMIENTO_OFERTA = "mantenimiento_oferta"
    TIEMPO_ENTREGA = "tiempo_entrega"
    FORMA_PAGO = "forma_pago"
    MONEDA = "moneda"
    TIPO_CAMBIO = "tipo_cambio"
    GARANTIAS_CAUCIONES = "garantias_cauciones"
    MULTAS_PENALIDADES = "multas_penalidades"
    ANTICIPO_FINANCIERO = "anticipo_financiero"
    REQUISITOS_TECNICOS_EXCLUYENTES = "requisitos_tecnicos_excluyentes"
    RESPONSABILIDAD_COSTOS_LOGISTICOS = "responsabilidad_costos_logisticos"


class PreviewCriterioItem(ExtractedItem):
    """Item de criterio de preview para la fase 1."""

    tipo: TipoCriterioPreview
    valor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tipo", mode="before")
    @classmethod
    def normalize_tipo(cls, value: Any) -> Any:
        if isinstance(value, TipoCriterioPreview):
            return value
        if not isinstance(value, str):
            return value

        normalized = unicodedata.normalize("NFKD", value)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")

        aliases = {
            "mantenimiento_de_oferta": "mantenimiento_oferta",
            "mto_oferta": "mantenimiento_oferta",
            "tiempo_de_entrega": "tiempo_entrega",
            "garantias": "garantias_cauciones",
            "cauciones": "garantias_cauciones",
            "multas": "multas_penalidades",
            "penalidades": "multas_penalidades",
            "anticipo": "anticipo_financiero",
            "req_tecnicos_excluyentes": "requisitos_tecnicos_excluyentes",
            "costos_logisticos": "responsabilidad_costos_logisticos",
        }
        candidate = aliases.get(normalized, normalized)

        try:
            return TipoCriterioPreview(candidate)
        except ValueError:
            return value


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
            "es_subsanable": "no_especificado",
        }
    )


class TipoRiesgo(str, Enum):
    """Tipos de riesgos en licitaciones."""

    DESCALIFICACION = "descalificacion"
    PENALIZACION = "penalizacion"
    LEGAL = "legal"
    OPERATIVO = "operativo"
    FINANCIERO = "financiero"
    OTRO = "otro"


class SubtipoRiesgo(str, Enum):
    """Subtipos de riesgo para clasificación granular."""

    EJECUCION = "ejecucion"
    INCUMPLIMIENTO = "incumplimiento"
    OPERATIVO = "operativo"
    PLAZOS = "plazos"
    ECONOMICO = "economico"
    TECNICO = "tecnico"
    LEGAL_CONTRACTUAL = "legal_contractual"
    COMERCIAL = "comercial"
    OTRO_EXPLICITO = "otro_explicito"


class RiesgoItem(ExtractedItem):
    """Item de riesgo identificado en el pliego."""

    tipo: TipoRiesgo
    subtipo: SubtipoRiesgo = SubtipoRiesgo.OTRO_EXPLICITO
    valor: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class HitoTemporalExtracted(BaseModel):
    """
    Hito temporal extraído del documento de pliego (fusión de lo que antes
    eran dos extractores separados: "eventos temporales" y "plazos
    relativos" -- ver `analysis/extraction/prompts/eventos_temporales.txt`).

    Representa un hito o momento clave del proceso de licitación. Puede
    tener fecha propia (explícita o pendiente) y, si el pliego lo cuenta a
    partir de otro hito ("15 días corridos desde la adjudicación"), lleva
    además los campos de plazo relativo en el MISMO ítem -- no hace falta
    (ni se permite) crear un segundo ítem solo para la duración.

    Al fusionar ambos conceptos en una sola pasada del LLM, `evento_disparador`
    queda garantizado (por instrucción del prompt) como el `nombre` exacto
    de OTRO ítem de esta misma lista -- ya no hay que reconciliar nombres
    entre dos extracciones independientes que nunca se vieron entre sí.
    """

    nombre: str = Field(
        description="Nombre normalizado del hito (ej: 'Adjudicación', 'Apertura de Ofertas')",
        min_length=3,
        max_length=120,
    )
    fecha_explicita: str | None = Field(
        default=None,
        description="Fecha ISO (YYYY-MM-DD) si se menciona explícitamente en el texto",
    )
    origen_fecha: Literal["detectada", "pendiente"] = Field(
        description="'detectada' si hay fecha explícita, 'pendiente' si no"
    )

    # Presentes solo si este hito se cuenta a partir de otro (plazo relativo).
    evento_disparador: str | None = Field(
        default=None,
        description=(
            "Nombre del hito desde/hasta el cual se cuenta este plazo -- debe "
            "ser EXACTAMENTE el 'nombre' de otro ítem de esta misma lista, "
            "no una redacción nueva"
        ),
        max_length=150,
    )
    cantidad: int | None = Field(
        default=None,
        description="Cantidad de unidades de tiempo (ej: 10, 15, 30)",
        ge=0,
    )
    unidad: Literal["días", "meses", "años", "horas"] | None = Field(
        default=None, description="Unidad de tiempo"
    )
    tipo_dias: Literal["corridos", "hábiles", "no_especificado"] | None = Field(
        default=None,
        description="Si la unidad es 'días', especificar si son corridos o hábiles",
    )
    direccion: Literal["desde", "hasta", "antes_de", "después_de"] | None = Field(
        default=None, description="Dirección temporal del plazo respecto al evento disparador"
    )
    es_plazo_maximo: bool = Field(
        default=False,
        description="True si es un plazo máximo (límite), False si es duración estimada",
    )

    mencion_propia: bool = Field(
        default=True,
        description=(
            "True si el pliego declara este hito por sí mismo (tiene su propia "
            "oración/fecha, más allá de ser el disparador de otro plazo). False "
            "SOLO cuando este ítem se creó nada más porque otro ítem lo nombra "
            "en `evento_disparador` y el pliego nunca lo menciona por su cuenta "
            "-- ver regla 2. Sirve para que el usuario final pueda distinguir "
            "'esto está en el pliego' de 'esto lo inferimos para poder calcular "
            "otra fecha'."
        ),
    )

    # Estos 3 campos reemplazan ~10 funciones de post-filtrado por regex que no generalizaban (releer memoria `eventos-temporales-auditoria-completa-2026-09-21`): el LLM las autodeclara por ítem en vez de inferirlas después por texto libre.
    accion_concreta: str = Field(
        description=(
            "La acción concreta que ocurre en este hito, con sujeto y verbo "
            "propio (ej. 'el oferente presenta la oferta', 'el organismo "
            "notifica la adjudicación', 'el proveedor entrega los bienes'). "
            "Si no podés escribir una acción puntual con un sujeto que hace "
            "algo -- porque el texto solo describe una característica, una "
            "condición general, o remite a otro documento -- este ítem no "
            "debería existir."
        ),
        min_length=8,
        max_length=200,
    )
    es_ocurrencia_unica: bool = Field(
        description=(
            "True si este hito representa un momento PUNTUAL del proceso: "
            "ocurre una vez, en un punto identificable (aunque la fecha "
            "exacta todavía no se conozca). False si en realidad describe "
            "una característica o condición continua (ej. una duración de "
            "garantía del producto, la vigencia general del contrato), una "
            "obligación que se repite mientras dure la ejecución (informes "
            "periódicos, mesas de soporte 24x7), o una métrica medida cada "
            "vez que ocurre otra acción que se puede repetir cualquier "
            "cantidad de veces (ej. un tiempo de respuesta contado desde un "
            "llamado o reclamo, que puede pasar una vez, varias veces o "
            "nunca)."
        ),
    )
    depende_de_decision_discrecional: bool = Field(
        description=(
            "True si este hito depende de que una de las partes DECIDA "
            "ejercer un derecho o facultad, sin que el pliego lo ate a una "
            "etapa puntual del cronograma (ej. 'el organismo podrá auditar "
            "en cualquier momento durante la ejecución'). False si el hito "
            "ocurre en un punto conocido o calculable del proceso -- aunque "
            "alguien deba decidir accionarlo dentro de una ventana concreta "
            "(ej. 'podrá prorrogar la fecha de apertura hasta 2 días antes "
            "de la fecha original' es False: la decisión está acotada a una "
            "etapa puntual, no es 'en cualquier momento')."
        ),
    )

    fuente_documento_id: str = Field(description="ID del documento donde se encontró")
    fuente_pagina: int = Field(description="Número de página donde aparece", ge=1)
    fuente_fragmento: str = Field(
        description="Fragmento de texto original que menciona el hito",
        min_length=CITATION_MIN_CHARS,
        max_length=500,
    )
    extraction_status: Literal["success"] = Field(
        default="success",
        description=(
            "Siempre 'success' para cada hito emitido -- este campo NO se "
            "valida contra este schema en runtime (la llamada al LLM usa "
            "JSON mode libre, sin structured outputs atados a este modelo), "
            "pero `_normalize_item` (engine/normalization.py) sí lo lee del "
            "dict crudo: sin él, cada ítem cae a 'not_found' porque estos "
            "hitos no usan `source_references` (usan `fuente_*`) y por eso "
            "no hay otra señal desde la que inferir el status."
        ),
    )

    @field_validator("fecha_explicita")
    def validate_fecha_format(cls, v):
        """Valida formato ISO de fecha."""
        if v and not v.count("-") == 2:
            raise ValueError("Fecha debe estar en formato YYYY-MM-DD")
        return v

    @field_validator("tipo_dias")
    def validate_tipo_dias_only_for_dias(cls, v, info):
        """Valida que tipo_dias solo se use cuando unidad es 'días'."""
        if v and info.data.get("unidad") not in (None, "días"):
            raise ValueError("tipo_dias solo aplica cuando unidad es 'días'")
        return v


class HitosTemporalesResponse(BaseModel):
    """
    Respuesta completa de extracción de hitos temporales (eventos + plazos
    relativos fusionados).

    El nombre del campo (`eventos_temporales`, no `hitos`) tiene que
    coincidir con `result_key`/`root_key` del extractor -- `_base_system.txt`
    instruye al LLM a devolver `{"{root_key}": [...]}` como raíz del JSON, y
    `run_extractor` (engine/base.py) lee `llm_result.get(result_key)`.
    """

    eventos_temporales: list[HitoTemporalExtracted] = Field(
        default_factory=list,
        description="Lista de hitos temporales encontrados en el documento",
    )


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


class ExtractedData(BaseModel):
    """
    Contenedor de todas las categorías extraídas.

    Cada categoría tiene:
    - items: lista de items extraídos (con schema específico)
    - extraction_status: estado global de la extracción
    - narrative: respuesta en lenguaje natural (opcional)
    """

    calidad_por_categoria: dict[str, dict[str, int]] = Field(default_factory=dict)
    objeto_alcance: list[ObjetoAlcanceItem] = Field(default_factory=list)
    objeto_alcance_extraction_status: str = "unknown"
    objeto_alcance_narrative: CategoryNarrative | None = None
    requisitos_admisibilidad: list[RequisitoAdmisibilidadItem] = Field(default_factory=list)
    requisitos_admisibilidad_extraction_status: str = "unknown"
    requisitos_admisibilidad_narrative: CategoryNarrative | None = None
    plazos_clave: list[PlazoItem] = Field(default_factory=list)
    plazos_clave_extraction_status: str = "unknown"
    plazos_clave_narrative: CategoryNarrative | None = None
    garantias: list[GarantiaItem] = Field(default_factory=list)
    garantias_extraction_status: str = "unknown"
    garantias_narrative: CategoryNarrative | None = None
    causales_rechazo: list[CausalRechazoItem] = Field(default_factory=list)
    causales_rechazo_extraction_status: str = "unknown"
    causales_rechazo_narrative: CategoryNarrative | None = None
    causales_extraction_status: str = "unknown"
    criterios_evaluacion: list[CriterioEvaluacionItem] = Field(default_factory=list)
    criterios_evaluacion_extraction_status: str = "unknown"
    criterios_evaluacion_narrative: CategoryNarrative | None = None
    anexos_obligatorios: list[AnexoObligatorioItem] = Field(default_factory=list)
    anexos_obligatorios_extraction_status: str = "unknown"
    anexos_obligatorios_narrative: CategoryNarrative | None = None
    identificacion_procedimiento: list[IdentificacionProcedimientoItem] = Field(
        default_factory=list
    )
    identificacion_procedimiento_extraction_status: str = "unknown"
    identificacion_procedimiento_narrative: CategoryNarrative | None = None
    # Preview NO tiene contrato backend dedicado: el frontend unifica visualmente `preview_criterios` + `objeto_alcance`.
    preview_criterios: list[PreviewCriterioItem] = Field(default_factory=list)
    preview_criterios_extraction_status: str = "unknown"
    preview_criterios_narrative: CategoryNarrative | None = None
    riesgos: list[RiesgoItem] = Field(default_factory=list)
    riesgos_extraction_status: str = "unknown"
    riesgos_narrative: CategoryNarrative | None = None

    eventos_temporales: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Eventos temporales extraídos del documento (Story 15.1)"
    )
    eventos_temporales_extraction_status: str = "unknown"

    plazos_relativos: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Plazos relativos extraídos del documento (Story 15.2)"
    )
    plazos_relativos_extraction_status: str = "unknown"

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
        description="DEPRECATED: Usar 'requisitos_admisibilidad' en su lugar. Será eliminado en Q2 2027.",
    )
    documentos_extraction_status: str = NOT_ANALYZED_STATUS
    restricciones_participacion: list[GenericCategoryItem] = Field(default_factory=list)
    restricciones_extraction_status: str = NOT_ANALYZED_STATUS
    cronograma_proceso: list[GenericCategoryItem] = Field(default_factory=list)
    cronograma_extraction_status: str = NOT_ANALYZED_STATUS
    estimacion_presupuesto: PresupuestoItem | None = None
    presupuesto_extraction_status: str = NOT_ANALYZED_STATUS


__all__ = [
    "SourceReference",
    "ConfidenceLevel",
    "ExtractionStatus",
    "ExtractedItem",
    "CategoryNarrative",
    "NarrativeBlock",
    "NarrativeParagraphBlock",
    "NarrativeBulletListBlock",
    "NarrativeTableBlock",
    "NarrativeSource",
    "NarrativeBulletItem",
    "NarrativeTableRow",
    "RawCategoryNarrative",
    "RawNarrativeBlock",
    "RawNarrativeParagraphBlock",
    "RawNarrativeBulletItem",
    "RawNarrativeBulletListBlock",
    "RawNarrativeTableRow",
    "RawNarrativeTableBlock",
    "PlazoItem",
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
    "PreviewCriterioItem",
    "TipoCriterioPreview",
    "CausalRechazoItem",
    "TipoCausal",
    "RiesgoItem",
    "TipoRiesgo",
    "SubtipoRiesgo",
    "HitoTemporalExtracted",
    "HitosTemporalesResponse",
    "GenericCategoryItem",
    "PresupuestoItem",
    "ExtractedData",
]
