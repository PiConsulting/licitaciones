from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    document_id: str
    page_number: int
    citation: str


class ExtractedItem(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    source_references: list[SourceReference] = Field(default_factory=list)
    extraction_status: Literal["success", "failed", "not_found", "partial"]


class PlazoItem(ExtractedItem):
    tipo: str
    fecha: str | None = None
    hora: str | None = None


class GarantiaItem(ExtractedItem):
    tipo: str
    monto_porcentaje: float | None = None
    monto_valor: float | None = None
    forma_constitucion: str | None = None
    vigencia: str | None = None


class GenericCategoryItem(ExtractedItem):
    tipo: str | None = None
    valor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresupuestoItem(ExtractedItem):
    monto: float | None = None
    moneda: str | None = None
    forma_pago: str | None = None
    ajustes: str | None = None


class ExtractedData(BaseModel):
    plazos: list[PlazoItem] = Field(default_factory=list)
    plazos_extraction_status: str = "unknown"

    garantias: list[GarantiaItem] = Field(default_factory=list)
    garantias_extraction_status: str = "unknown"

    causales_rechazo: list[GenericCategoryItem] = Field(default_factory=list)
    causales_extraction_status: str = "unknown"

    documentos_requeridos: list[GenericCategoryItem] = Field(default_factory=list)
    documentos_extraction_status: str = "unknown"

    criterios_evaluacion: list[GenericCategoryItem] = Field(default_factory=list)
    criterios_extraction_status: str = "unknown"

    restricciones_participacion: list[GenericCategoryItem] = Field(default_factory=list)
    restricciones_extraction_status: str = "unknown"

    cronograma_proceso: list[GenericCategoryItem] = Field(default_factory=list)
    cronograma_extraction_status: str = "unknown"

    estimacion_presupuesto: PresupuestoItem | None = None
    presupuesto_extraction_status: str = "unknown"
