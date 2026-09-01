"""Versioned intermediate representation for parsed PDF documents."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    StringConstraints,
    model_validator,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
WarningCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    ),
]
Confidence = Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
PositiveDimension = Annotated[FiniteFloat, Field(gt=0.0)]
Coordinate = Annotated[FiniteFloat, Field(ge=0.0)]


class PDFDocumentType(StrEnum):
    """Document-level routing result."""

    TEXT_BASED = "text_based"
    SCANNED = "scanned"
    MIXED = "mixed"


class PDFPageType(StrEnum):
    """Page-level routing result."""

    TEXT = "text"
    SCANNED = "scanned"
    MIXED = "mixed"
    EMPTY = "empty"


class PDFBlockType(StrEnum):
    """Semantic block types preserved by the PDF pipeline."""

    TITLE = "title"
    TEXT = "text"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"
    CAPTION = "caption"
    FOOTNOTE = "footnote"


class PDFBlockSource(StrEnum):
    """Origin of a parsed block."""

    NATIVE = "native"
    OCR = "ocr"
    DERIVED = "derived"


class PDFParseStatus(StrEnum):
    """Terminal status represented by a persisted DocumentIR."""

    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"


class PDFWarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PDFIRModel(BaseModel):
    """Shared validation settings for all PDF IR models."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class BoundingBox(PDFIRModel):
    """Axis-aligned PDF coordinates measured from the page's top-left corner."""

    x0: Coordinate
    y0: Coordinate
    x1: Coordinate
    y1: Coordinate

    @model_validator(mode="after")
    def validate_axis_order(self) -> Self:
        if self.x1 < self.x0:
            raise ValueError("x1 must be greater than or equal to x0")
        if self.y1 < self.y0:
            raise ValueError("y1 must be greater than or equal to y0")
        return self


class ParseWarning(PDFIRModel):
    """Non-fatal issue retained for diagnostics and partial-success reporting."""

    code: WarningCode
    message: Annotated[NonBlankText, StringConstraints(max_length=2_000)]
    severity: PDFWarningSeverity = PDFWarningSeverity.WARNING
    page_number: int | None = Field(default=None, ge=1)
    block_id: Identifier | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class BlockIR(PDFIRModel):
    """One positioned semantic unit on a PDF page."""

    block_id: Identifier
    type: PDFBlockType
    bbox: BoundingBox
    source: PDFBlockSource
    reading_order: int = Field(ge=0)
    text: NonBlankText | None = None
    raw_text: str | None = None
    confidence: Confidence | None = None
    asset_uri: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
        | None
    ) = None
    table_markdown: NonBlankText | None = None
    latex: NonBlankText | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_for_type(self) -> Self:
        text_required = {
            PDFBlockType.TITLE,
            PDFBlockType.TEXT,
            PDFBlockType.LIST,
            PDFBlockType.HEADER,
            PDFBlockType.FOOTER,
            PDFBlockType.CAPTION,
            PDFBlockType.FOOTNOTE,
        }
        if self.type in text_required and self.text is None:
            raise ValueError(f"{self.type.value} blocks require text")
        if self.table_markdown is not None and self.type is not PDFBlockType.TABLE:
            raise ValueError("table_markdown is only valid for table blocks")
        if self.latex is not None and self.type is not PDFBlockType.FORMULA:
            raise ValueError("latex is only valid for formula blocks")
        return self


class PageIR(PDFIRModel):
    """Structured representation of a single PDF page."""

    page_number: int = Field(ge=1)
    width: PositiveDimension
    height: PositiveDimension
    page_type: PDFPageType
    confidence: Confidence | None = None
    blocks: tuple[BlockIR, ...] = ()
    warnings: tuple[ParseWarning, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_content(self) -> Self:
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block_id values must be unique within a page")

        reading_orders = [block.reading_order for block in self.blocks]
        if len(reading_orders) != len(set(reading_orders)):
            raise ValueError("reading_order values must be unique within a page")

        for block in self.blocks:
            if block.bbox.x1 > self.width or block.bbox.y1 > self.height:
                raise ValueError(f"block {block.block_id} bbox exceeds page bounds")
        for warning in self.warnings:
            if warning.page_number is not None and warning.page_number != self.page_number:
                raise ValueError("page warning must refer to its containing page")
            if warning.block_id is not None and warning.block_id not in block_ids:
                raise ValueError("page warning refers to an unknown block")
        return self


class DocumentIR(PDFIRModel):
    """Complete, loss-aware representation persisted for one PDF document."""

    schema_version: Literal["1.0"] = "1.0"
    parser_version: Annotated[NonBlankText, StringConstraints(max_length=64)]
    document_id: UUID
    source_filename: Annotated[NonBlankText, StringConstraints(max_length=255)]
    checksum_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    document_type: PDFDocumentType
    status: PDFParseStatus = PDFParseStatus.SUCCEEDED
    page_count: int = Field(ge=1)
    pages: Annotated[tuple[PageIR, ...], Field(min_length=1)]
    warnings: tuple[ParseWarning, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_document_content(self) -> Self:
        if len(self.pages) != self.page_count:
            raise ValueError("page_count must equal the number of pages")

        expected_numbers = list(range(1, self.page_count + 1))
        actual_numbers = [page.page_number for page in self.pages]
        if actual_numbers != expected_numbers:
            raise ValueError("pages must be ordered and numbered contiguously from 1")

        block_locations = {
            block.block_id: page.page_number for page in self.pages for block in page.blocks
        }
        total_blocks = sum(len(page.blocks) for page in self.pages)
        if len(block_locations) != total_blocks:
            raise ValueError("block_id values must be unique within a document")

        for warning in self.warnings:
            if warning.page_number is not None and warning.page_number > self.page_count:
                raise ValueError("document warning refers to a page outside the document")
            if warning.block_id is not None and warning.block_id not in block_locations:
                raise ValueError("document warning refers to an unknown block")
            if (
                warning.block_id is not None
                and warning.page_number is not None
                and block_locations[warning.block_id] != warning.page_number
            ):
                raise ValueError("document warning block does not belong to the referenced page")
        return self
