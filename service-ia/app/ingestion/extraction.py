"""Text extraction for administrator-uploaded documents."""

from __future__ import annotations

import re
import logging
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document

try:
    from pypdf import PdfReader
except ImportError:  # PDF preflight remains optional when Docling supplies no pypdf.
    PdfReader = None
from docx.document import Document as DocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
except ImportError:  # Raised with a clear ingestion error when image is stale.
    DocumentConverter = None
    PdfFormatOption = None
    InputFormat = None
    PdfPipelineOptions = None

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class DocumentExtractionError(ValueError):
    """Raised when a supported document contains no usable text."""


class UnsupportedDocumentError(ValueError):
    """Raised when a document format is not supported."""


@dataclass(frozen=True)
class ExtractedSection:
    content: str
    page: int | None = None
    page_count: int | None = None


def extract_document(filename: str, data: bytes) -> list[ExtractedSection]:
    """Extract normalized text while preserving real PDF page numbers."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(
            "Format non pris en charge. Utilisez un fichier PDF, DOCX ou TXT."
        )
    if not data:
        raise DocumentExtractionError("Le document est vide.")

    try:
        if extension == ".pdf":
            sections = _extract_pdf(data)
        elif extension == ".docx":
            sections = _extract_docx(data)
        else:
            sections = _extract_txt(data)
    except (DocumentExtractionError, UnsupportedDocumentError):
        raise
    except Exception as exc:
        logger.exception("Document extraction failed filename=%r extension=%s", filename, extension)
        raise DocumentExtractionError(
            "Le document est illisible ou endommagé."
        ) from exc

    if not sections:
        message = (
            "Ce PDF ne contient pas de texte exploitable. Les PDF scannés ne sont pas pris en charge."
            if extension == ".pdf"
            else "Le document ne contient pas de texte exploitable."
        )
        raise DocumentExtractionError(message)
    return sections


def _pdf_converter() -> DocumentConverter:
    """Create the layout extractor without OCR for selectable-text PDFs.

    Production project PDFs already contain selectable text. Disabling OCR avoids
    an optional model download at reindex time and lets Docling preserve the
    table grid as Markdown rather than flattening its cells into prose.
    """
    if (
        DocumentConverter is None
        or PdfFormatOption is None
        or InputFormat is None
        or PdfPipelineOptions is None
    ):
        raise DocumentExtractionError(
            "Le composant d'extraction PDF Docling est indisponible. Reconstruisez le service IA."
        )
    options = PdfPipelineOptions()
    options.do_ocr = False
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _table_row_to_evidence_line(line: str) -> str | None:
    """Render one Markdown row as labeled, row-preserving retrieval evidence."""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not cells or all(not cell for cell in cells):
        return None
    if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
        return None
    return " | ".join(cells)


def _markdown_to_evidence_text(markdown: str) -> str:
    """Keep headings and table rows atomic before page-scoped chunking.

    Docling Markdown carries explicit column separators and row boundaries. This
    representation retains names, roles, allocations, periods, days, rates and
    amounts together in each source row, unlike ``export_to_text`` which loses
    the grid and lets the generic sentence chunker cut through a row.
    """
    blocks: list[str] = []
    table_headers: list[str] | None = None
    table_rows: list[str] = []

    def flush_table() -> None:
        nonlocal table_headers, table_rows
        if table_headers and table_rows:
            for row in table_rows:
                values = row.split(" | ")
                if len(values) != len(table_headers):
                    # Retain imperfectly detected rows verbatim rather than
                    # silently dropping a source fact.
                    blocks.append(" | ".join(table_headers) + " :: " + row)
                    continue
                blocks.append("; ".join(
                    f"{header}: {value}" for header, value in zip(table_headers, values, strict=True)
                ))
        table_headers = None
        table_rows = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_table()
            continue
        if line.startswith("|") and line.endswith("|"):
            row = _table_row_to_evidence_line(line)
            if row is None:
                continue
            if table_headers is None:
                table_headers = row.split(" | ")
            else:
                table_rows.append(row)
            continue
        flush_table()
        blocks.append(line)
    flush_table()
    return _normalize_text("\n\n".join(blocks))


def _extract_pdf(data: bytes) -> list[ExtractedSection]:
    """Extract physical PDF pages with row-preserving Docling Markdown tables."""
    _check_pdf_encryption(data)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
            temporary_file.write(data)
            temporary_path = temporary_file.name
        document = _pdf_converter().convert(temporary_path).document
        page_numbers = sorted(int(page_number) for page_number in document.pages)
        page_count = len(page_numbers)
        logger.info("Extracting PDF with Docling Markdown across %d physical pages", page_count)
        sections: list[ExtractedSection] = []
        for page_number in page_numbers:
            try:
                content = _markdown_to_evidence_text(
                    document.export_to_markdown(page_no=page_number, compact_tables=False)
                )
            except Exception as exc:
                raise DocumentExtractionError(
                    f"L'extraction de la page PDF {page_number} a échoué; le document n'a pas été indexé."
                ) from exc
            if content:
                sections.append(
                    ExtractedSection(content=content, page=page_number, page_count=page_count)
                )
        return sections
    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.exception(
            "Docling PDF conversion failed (%s); attempting selectable-text fallback",
            type(exc).__name__,
        )
        sections = _extract_pdf_with_pypdf(data)
        if sections:
            logger.warning("Indexed PDF using pypdf fallback after Docling failure")
            return sections
        raise DocumentExtractionError("Le PDF ne peut pas être extrait. Consultez les journaux du service IA.") from exc
    finally:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)


def _extract_pdf_with_pypdf(data: bytes) -> list[ExtractedSection]:
    """Extract selectable text when Docling's optional layout stack is unavailable."""
    if PdfReader is None:
        return []

    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            return []
        page_count = len(reader.pages)
        sections: list[ExtractedSection] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                content = _normalize_text(page.extract_text() or "")
            except Exception:
                logger.exception("Skipping PDF page=%s because pypdf text extraction failed", page_number)
                continue
            if content:
                sections.append(ExtractedSection(content=content, page=page_number, page_count=page_count))
        return sections
    except Exception:
        logger.exception("pypdf fallback failed")
        return []


def _check_pdf_encryption(data: bytes) -> None:
    """Reject only PDFs that remain encrypted after the standard empty-password attempt.

    Some valid PDFs advertise encryption metadata despite being readable without a
    password. In that case ``decrypt(\"\")`` succeeds and Docling remains the
    authoritative layout-aware extractor. Parse failures are logged and delegated
    to Docling instead of being misclassified as password protection.
    """
    if PdfReader is None:
        logger.debug("pypdf is unavailable; skipping PDF encryption preflight")
        return

    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentExtractionError("Ce PDF est protégé par mot de passe et ne peut pas être indexé.")
    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.warning(
            "PDF encryption preflight could not parse %s; delegating to Docling: %s",
            type(exc).__name__,
            exc,
        )


def _extract_docx(data: bytes) -> list[ExtractedSection]:
    document = Document(BytesIO(data))
    blocks: list[str] = []
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = _normalize_text(block.text)
        else:
            rows = [
                " | ".join(_normalize_text(cell.text) for cell in row.cells)
                for row in block.rows
            ]
            text = _normalize_text("\n".join(row for row in rows if row.strip(" |")))
        if text:
            blocks.append(text)
    content = "\n\n".join(blocks)
    return [ExtractedSection(content=content)] if content else []


def _iter_docx_blocks(document: DocumentType):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _extract_txt(data: bytes) -> list[ExtractedSection]:
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = data.decode("cp1252")
    content = _normalize_text(decoded)
    return [ExtractedSection(content=content)] if content else []


def _normalize_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()