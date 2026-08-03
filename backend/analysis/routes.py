from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from analysis.schemas import AnalysisCreateResponse
from analysis.service import IncomingUploadFile, create_analysis_with_documents, to_document_response
from shared.database import get_db
from users.service import get_current_user, http_bearer

analysis_router = APIRouter(prefix="/analyses", tags=["analyses"])


@analysis_router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    files: Annotated[list[UploadFile], File(...)],
    primary_file_index: Annotated[int, Form()] = 0,
    credentials=Depends(http_bearer),
    db: Session = Depends(get_db),
) -> AnalysisCreateResponse:
    current_user = get_current_user(credentials, db)

    incoming_files: list[IncomingUploadFile] = []
    for file in files:
        incoming_files.append(
            IncomingUploadFile(
                filename=file.filename or "documento.pdf",
                content=await file.read(),
            )
        )

    analysis, documents, warnings = create_analysis_with_documents(
        db=db,
        user_id=current_user.id,
        files=incoming_files,
        primary_file_index=primary_file_index,
    )

    return AnalysisCreateResponse(
        id=analysis.id,
        status=analysis.status,
        documents=[to_document_response(document) for document in documents],
        warnings=warnings,
    )
