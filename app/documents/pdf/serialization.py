"""Canonical serialization and storage naming for persisted PDF DocumentIR files."""

from uuid import UUID

from app.documents.pdf.models import DocumentIR

DOCUMENT_IR_CONTENT_TYPE = "application/json; charset=utf-8"
DOCUMENT_IR_FILENAME = "document-ir.v1.json"


def document_ir_object_key(document_id: UUID | str) -> str:
    """Return the domain-neutral MinIO key for one document's versioned IR."""

    canonical_id = UUID(str(document_id))
    return f"documents/{canonical_id}/parsed/{DOCUMENT_IR_FILENAME}"


def serialize_document_ir(document_ir: DocumentIR) -> str:
    """Serialize a validated DocumentIR as human-readable UTF-8 JSON."""

    payload = document_ir.model_dump_json(indent=2)
    DocumentIR.model_validate_json(payload)
    return f"{payload}\n"
