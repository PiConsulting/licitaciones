from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from typing import Literal

from documents.schemas import DocumentResponse, DocumentWarning


class DuplicateWarning(BaseModel):
    document_id: str
    filename: str
    existing_analysis_id: str
    created_at: str
    created_by: str
    status: str


class AnalysisCreateResponse(BaseModel):
    id: str
    status: str
    documents: list[DocumentResponse]
    warnings: list[DocumentWarning]
    requires_resolution: bool = False
    duplicates: list[DuplicateWarning] = Field(default_factory=list)


class DuplicateDecision(BaseModel):
    document_id: str
    action: Literal["view_existing", "analyze_again", "cancel"]


class StartAnalysisRequest(BaseModel):
    decisions: list[DuplicateDecision] = Field(default_factory=list)
    analysis_name: str | None = Field(default=None, max_length=160)


class StartAnalysisResponse(BaseModel):
    id: str
    status: str
    message: str
    requires_resolution: bool = False
    duplicates: list[DuplicateWarning] = Field(default_factory=list)
    redirect_analysis_id: str | None = None


ReanalyzeType = Literal["all", "phase1", "phase2", "categories"]


class ReanalyzeRequest(BaseModel):
    reanalysis_type: ReanalyzeType
    categories: list[str] = Field(default_factory=list)


class ReanalyzeResponse(BaseModel):
    id: str
    status: str
    message: str
    reanalysis_type: ReanalyzeType
    categories: list[str] = Field(default_factory=list)
    source_version_id: str | None = None
    target_version_id: str | None = None
    target_version_number: int | None = None


class AnalysisPatchRequest(BaseModel):
    monto_estimado: float = Field(..., ge=0)
    moneda: str = Field(..., min_length=1, max_length=10)


class AnalysisPatchResponse(BaseModel):
    id: str
    monto_estimado: float
    moneda: str
    monto_estimado_source: Literal["manual"]
    message: str


class AnalysisStatusResponse(BaseModel):
    id: str
    status: str
    current_stage: str
    stage_progress: str | None = None
    progress_percentage: int
    started_at: datetime | None = None
    timeout_at: datetime | None = None
    timeout_warning_at: datetime | None = None
    error_message: str | None = None
    extracted_data: dict | None = None
    conflicts: list[dict] | None = None
    reanalysis_type: ReanalyzeType | None = None
    reanalysis_categories: list[str] = Field(default_factory=list)
    reanalysis_started_at: datetime | None = None


class AnalysisListItem(BaseModel):
    id: str
    analysis_name: str | None = None
    business_unit: str | None = None
    status: str
    business_status: str | None = None
    current_stage: str
    stage_progress: str | None = None
    progress_percentage: int
    confidence_avg: float | None = None
    created_at: datetime
    primary_document_name: str | None = None
    organismo: str | None = None
    created_by_name: str | None = None
    monto_estimado: float | None = None
    moneda: str | None = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisListItem]
    page: int
    per_page: int
    total: int
    total_pages: int


class AnalysisBusinessUnitItem(BaseModel):
    business_unit: str
    count: int


class AnalysisVersionResponse(BaseModel):
    id: str
    version_number: int
    extracted_data: dict
    conflicts: list[dict] | None = None
    created_at: datetime
    created_by: str | None = None


class AnalysisDetailResponse(BaseModel):
    id: str
    analysis_name: str | None = None
    business_unit: str | None = None
    created_at: datetime
    status: str
    current_stage: str
    current_version: AnalysisVersionResponse
    versions: list[AnalysisVersionResponse] = Field(default_factory=list)
    documents: list[DocumentResponse]
    created_by: str | None = None
    created_by_name: str | None = None
    categories_decision: Literal["approved", "rejected"] | None = None
    categories_decision_by_name: str | None = None
    categories_decision_at: datetime | None = None
    business_status: str | None = None
    tracking: dict | None = None


class CategoriesDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]


class CategoriesDecisionResponse(BaseModel):
    id: str
    status: str
    message: str
    decision: Literal["approved", "rejected"]
    decision_by_name: str | None = None
    decision_at: datetime | None = None


BusinessStatusValue = Literal[
    "en_analisis",
    "pendiente_decision",
    "no_aprobada",
    "en_revision",
    "presentada",
    "ganada",
    "perdida",
]


class BusinessStatusUpdateRequest(BaseModel):
    business_status: BusinessStatusValue
    note: str | None = Field(default=None, max_length=1000)


class BusinessStatusUpdateResponse(BaseModel):
    id: str
    business_status: BusinessStatusValue
    previous_status: BusinessStatusValue | None = None
    changed_by_name: str | None = None
    changed_at: datetime
    message: str


class BusinessStatusSummaryResponse(BaseModel):
    total: int
    by_status: dict[str, int]


PresentationChannel = Literal["compr_ar", "bac_caba", "portal_organismo", "mesa_entradas", "otro"]
LossReason = Literal["precio", "puntaje_tecnico", "descalificada", "desierta_cancelada", "otro"]
CurrencyCode = Literal["ARS", "USD"]


class PresentationRequest(BaseModel):
    presented_at: date
    amount: float | None = Field(default=None, ge=0)
    currency: CurrencyCode = "ARS"
    channel: PresentationChannel
    offer_number: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class PresentationResponse(BaseModel):
    presented_at: date
    amount: float | None = None
    currency: str
    channel: str
    offer_number: str | None = None
    notes: str | None = None
    receipt_filename: str | None = None
    updated_at: datetime


class ReceiptUrlResponse(BaseModel):
    url: str
    filename: str


class UpcomingEventItem(BaseModel):
    analysis_id: str
    analysis_name: str | None = None
    organismo: str | None = None
    business_status: str | None = None
    business_unit: str | None = None
    event_id: str
    event_name: str
    event_date: date
    days_until: int
    additional_events: int = 0


class ResultRequest(BaseModel):
    outcome: Literal["ganada", "perdida"]
    resulted_at: date
    awarded_amount: float | None = Field(default=None, ge=0)
    loss_reason: LossReason | None = None
    winner_name: str | None = Field(default=None, max_length=200)
    winner_amount: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_outcome_fields(self) -> "ResultRequest":
        if self.outcome == "perdida" and self.loss_reason is None:
            raise ValueError("loss_reason es obligatorio cuando el resultado es perdida")
        if self.outcome == "ganada" and (
            self.loss_reason is not None
            or self.winner_name is not None
            or self.winner_amount is not None
        ):
            raise ValueError("loss_reason, winner_name y winner_amount aplican solo a perdida")
        if self.outcome == "perdida" and self.awarded_amount is not None:
            raise ValueError("awarded_amount aplica solo a ganada")
        return self


class ResultResponse(BaseModel):
    outcome: str
    resulted_at: date
    awarded_amount: float | None = None
    loss_reason: str | None = None
    winner_name: str | None = None
    winner_amount: float | None = None
    notes: str | None = None
    updated_at: datetime


class BusinessStatusHistoryItem(BaseModel):
    previous_status: str | None = None
    new_status: str
    changed_by_name: str | None = None
    changed_at: datetime
    note: str | None = None


class BusinessStatusStateResponse(BaseModel):
    id: str
    business_status: BusinessStatusValue
    presentation: PresentationResponse | None = None
    result: ResultResponse | None = None
    history: list[BusinessStatusHistoryItem] = Field(default_factory=list)
