from pydantic import BaseModel, Field
from datetime import datetime
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


class StartAnalysisResponse(BaseModel):
    id: str
    status: str
    message: str
    requires_resolution: bool = False
    duplicates: list[DuplicateWarning] = Field(default_factory=list)
    redirect_analysis_id: str | None = None


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


class AnalysisListItem(BaseModel):
    id: str
    status: str
    current_stage: str
    stage_progress: str | None = None
    progress_percentage: int
    created_at: datetime
    primary_document_name: str | None = None
    organismo: str | None = None
    created_by_name: str | None = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisListItem]
    page: int
    per_page: int
    total: int
    total_pages: int


class AnalysisVersionResponse(BaseModel):
    id: str
    version_number: int
    extracted_data: dict
    conflicts: list[dict] | None = None
    created_at: datetime
    created_by: str | None = None


class AnalysisDetailResponse(BaseModel):
    id: str
    created_at: datetime
    status: str
    current_stage: str
    current_version: AnalysisVersionResponse
    documents: list[DocumentResponse]
    created_by: str | None = None
