from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument

from app.core.exceptions import DocumentProcessingError, UnsupportedDocumentError


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int | None


class DocumentParser:
    def parse(self, content: bytes, filename: str) -> ParsedDocument:
        extension = Path(filename).suffix.lower()
        try:
            if extension == ".pdf":
                parsed = self._parse_pdf(content)
            elif extension == ".docx":
                parsed = self._parse_docx(content)
            else:
                raise UnsupportedDocumentError("only PDF and DOCX files are supported")
        except UnsupportedDocumentError:
            raise
        except Exception as exc:
            raise DocumentProcessingError(
                f"failed to parse {extension.removeprefix('.').upper()} document"
            ) from exc

        if not parsed.text.strip():
            raise DocumentProcessingError("document contains no extractable text")
        return parsed

    @staticmethod
    def _parse_pdf(content: bytes) -> ParsedDocument:
        with pymupdf.open(  # type: ignore[no-untyped-call]
            stream=content, filetype="pdf"
        ) as document:
            pages = [page.get_text("text").strip() for page in document]
            text = "\n\n".join(
                f"--- Page {index} ---\n{page}" for index, page in enumerate(pages, start=1) if page
            )
            return ParsedDocument(text=text, page_count=document.page_count)

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
