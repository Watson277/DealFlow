from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    original_filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    document_version: str | None
    knowledge_category: str | None
    parsed_text_object_key: str | None
    parsed_ir_object_key: str | None
    extra_data: dict[str, object]
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
