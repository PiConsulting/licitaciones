from pydantic import BaseModel, Field
from typing import Literal

from documents.schemas import DocumentResponse, DocumentWarning


class AnalysisCreateResponse(BaseModel):
    id: str
    status: str
    documents: list[DocumentResponse]
    warnings: list[DocumentWarning]


class DuplicateWarning(BaseModel):
    document_id: str
    filename: str
    existing_analysis_id: str
    created_at: str
    created_by: str
    status: str


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
    current_stage: str | None
    extracted_data: dict | None = None
    conflicts: list[dict] | None = None
