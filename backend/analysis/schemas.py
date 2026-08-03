from pydantic import BaseModel

from documents.schemas import DocumentResponse, DocumentWarning


class AnalysisCreateResponse(BaseModel):
    id: str
    status: str
    documents: list[DocumentResponse]
    warnings: list[DocumentWarning]
