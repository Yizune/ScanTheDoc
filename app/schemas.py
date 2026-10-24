from pydantic import BaseModel, Field


class MergeRequest(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=20)
    name: str = Field(default="Merged document", min_length=1, max_length=255)


class CompareRequest(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=2)


class DocumentSelectionRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=20)


class ExtractPagesRequest(BaseModel):
    pages: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=255)
