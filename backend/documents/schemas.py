from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    filename: str
    page_count: int
    file_size_bytes: int
    is_primary: bool


class DocumentWarning(BaseModel):
    filename: str
    message: str
