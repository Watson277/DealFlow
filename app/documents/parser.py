from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument

from app.core.config import Settings
from app.core.exceptions import DocumentProcessingError, UnsupportedDocumentError
from app.documents.pdf import NativePDFDocument, NativePDFParser, OCRProvider, PDFParsingConfig


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int | None
    pdf: NativePDFDocument | None = None


class DocumentParser:
    def __init__(
        self,
        pdf_config: PDFParsingConfig | None = None,
        pdf_ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.pdf_parser = NativePDFParser(pdf_config, pdf_ocr_provider)

    @classmethod
    def from_settings(cls, settings: Settings) -> "DocumentParser":
        return cls(PDFParsingConfig.from_settings(settings))

    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        extension = Path(filename).suffix.lower()
        try:
            if extension == ".pdf":
                parsed = self._parse_pdf(content, filename)
            elif extension == ".docx":
                parsed = self._parse_docx(content)
            else:
                raise UnsupportedDocumentError("only PDF and DOCX files are supported")
        except (UnsupportedDocumentError, DocumentProcessingError):
            raise
        except Exception as exc:
            raise DocumentProcessingError(
                f"failed to parse {extension.removeprefix('.').upper()} document"
            ) from exc

        if not parsed.text.strip():
            raise DocumentProcessingError("document contains no extractable text")
        return parsed

    def _parse_pdf(self, content: bytes, filename: str) -> ParsedDocument:
        parsed = self.pdf_parser.parse(content, filename)
        return ParsedDocument(text=parsed.text, page_count=parsed.page_count, pdf=parsed)

    @staticmethod
    def _parse_docx(content: bytes) -> ParsedDocument:
        document = DocxDocument(BytesIO(content))
        blocks: list[str] = []
        blocks.extend(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    blocks.append("\t".join(cells))
        return ParsedDocument(text="\n".join(blocks), page_count=None)
