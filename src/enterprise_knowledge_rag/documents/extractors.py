from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Protocol

from charset_normalizer import from_bytes
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from .source_models import (
    CleaningIssue,
    ExtractedBlock,
    ExtractedBlockKind,
    ExtractedDocument,
    IssueSeverity,
    SourceFile,
    SourceFormat,
)

MAX_SOURCE_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_EXPANDED_BYTES = 100 * 1024 * 1024

_ALLOWED_MEDIA_TYPES: dict[SourceFormat, frozenset[str]] = {
    SourceFormat.PDF: frozenset({"application/pdf"}),
    SourceFormat.DOCX: frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    ),
    SourceFormat.MARKDOWN: frozenset(
        {"text/markdown", "text/x-markdown", "text/plain"}
    ),
    SourceFormat.TEXT: frozenset({"text/plain"}),
}


class SourceValidationError(ValueError):
    """Raised when a source is unsafe, unsupported or structurally invalid."""


class SourceExtractor(Protocol):
    def supports(self, source: SourceFile) -> bool: ...

    def extract(self, source: SourceFile) -> ExtractedDocument: ...


def _base_document(
    source: SourceFile,
    *,
    blocks: list[ExtractedBlock],
    page_count: int | None = None,
    title_hint: str | None = None,
    issues: list[CleaningIssue] | None = None,
) -> ExtractedDocument:
    return ExtractedDocument(
        original_filename=source.original_filename,
        source_hash=source.source_hash,
        media_type=source.media_type,
        blocks=blocks,
        page_count=page_count,
        title_hint=title_hint,
        issues=issues or [],
    )


def _decode_text(content: bytes) -> str:
    if b"\x00" in content:
        raise SourceValidationError("text signature contains binary null bytes")
    match = from_bytes(content).best()
    if match is None:
        raise SourceValidationError("text encoding could not be detected")
    return str(match).replace("\r\n", "\n").replace("\r", "\n")


def _text_blocks(text: str, *, markdown: bool) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    paragraph_lines: list[str] = []
    heading_stack: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(line.strip() for line in paragraph_lines).strip()
        paragraph_lines.clear()
        if paragraph:
            blocks.append(
                ExtractedBlock(
                    kind=ExtractedBlockKind.PARAGRAPH,
                    order=len(blocks),
                    text=paragraph,
                    section_path=heading_stack.copy(),
                )
            )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line) if markdown else None
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack[level - 1 :] = [title]
            blocks.append(
                ExtractedBlock(
                    kind=ExtractedBlockKind.HEADING,
                    order=len(blocks),
                    text=title,
                    heading_level=level,
                    section_path=heading_stack[:-1],
                )
            )
            continue
        if markdown and re.match(r"^[-*+]\s+", line):
            flush_paragraph()
            blocks.append(
                ExtractedBlock(
                    kind=ExtractedBlockKind.LIST_ITEM,
                    order=len(blocks),
                    text=re.sub(r"^[-*+]\s+", "", line),
                    section_path=heading_stack.copy(),
                )
            )
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    return blocks


class MarkdownExtractor:
    def supports(self, source: SourceFile) -> bool:
        return source.suffix is SourceFormat.MARKDOWN

    def extract(self, source: SourceFile) -> ExtractedDocument:
        blocks = _text_blocks(_decode_text(source.content), markdown=True)
        title = next(
            (
                block.text
                for block in blocks
                if block.kind is ExtractedBlockKind.HEADING
            ),
            None,
        )
        return _base_document(source, blocks=blocks, title_hint=title)


class TextExtractor:
    def supports(self, source: SourceFile) -> bool:
        return source.suffix is SourceFormat.TEXT

    def extract(self, source: SourceFile) -> ExtractedDocument:
        return _base_document(
            source,
            blocks=_text_blocks(_decode_text(source.content), markdown=False),
        )


class DocxExtractor:
    def supports(self, source: SourceFile) -> bool:
        return source.suffix is SourceFormat.DOCX

    def extract(self, source: SourceFile) -> ExtractedDocument:
        _validate_docx_archive(source.content)
        try:
            document = Document(BytesIO(source.content))
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
            raise SourceValidationError("DOCX structure is invalid") from exc

        blocks: list[ExtractedBlock] = []
        heading_stack: list[str] = []
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                style_name = item.style.name if item.style is not None else ""
                heading_match = re.match(r"Heading\s+([1-6])", style_name)
                if heading_match:
                    level = int(heading_match.group(1))
                    heading_stack[level - 1 :] = [text]
                    kind = ExtractedBlockKind.HEADING
                    section_path = heading_stack[:-1]
                else:
                    level = None
                    kind = (
                        ExtractedBlockKind.LIST_ITEM
                        if "List" in style_name
                        else ExtractedBlockKind.PARAGRAPH
                    )
                    section_path = heading_stack.copy()
                blocks.append(
                    ExtractedBlock(
                        kind=kind,
                        order=len(blocks),
                        text=text,
                        heading_level=level,
                        section_path=section_path,
                    )
                )
            elif isinstance(item, Table):
                markdown_table = _table_to_markdown(item)
                if markdown_table:
                    blocks.append(
                        ExtractedBlock(
                            kind=ExtractedBlockKind.TABLE,
                            order=len(blocks),
                            text=markdown_table,
                            section_path=heading_stack.copy(),
                        )
                    )
        title = next(
            (
                block.text
                for block in blocks
                if block.kind is ExtractedBlockKind.HEADING
            ),
            None,
        )
        return _base_document(source, blocks=blocks, title_hint=title)


class PdfExtractor:
    def supports(self, source: SourceFile) -> bool:
        return source.suffix is SourceFormat.PDF

    def extract(self, source: SourceFile) -> ExtractedDocument:
        try:
            reader = PdfReader(BytesIO(source.content), strict=True)
        except Exception as exc:
            raise SourceValidationError("PDF structure is invalid") from exc
        if reader.is_encrypted:
            raise SourceValidationError("encrypted PDF is not supported")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise SourceValidationError("PDF exceeds the 200 page limit")

        blocks: list[ExtractedBlock] = []
        extracted_text: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                raise SourceValidationError("PDF page text extraction failed") from exc
            extracted_text.append(page_text)
            for paragraph in _split_pdf_text(page_text):
                blocks.append(
                    ExtractedBlock(
                        kind=ExtractedBlockKind.PARAGRAPH,
                        order=len(blocks),
                        text=paragraph,
                        page_number=page_number,
                    )
                )

        visible_characters = sum(
            1 for char in "".join(extracted_text) if not char.isspace()
        )
        minimum_characters = max(40, page_count * 20)
        issues: list[CleaningIssue] = []
        if visible_characters < minimum_characters:
            issues.append(
                CleaningIssue(
                    code="scanned_or_low_text_pdf",
                    severity=IssueSeverity.BLOCKING,
                    message="PDF 缺少足够的可提取文本，需要人工处理。",
                )
            )
        return _base_document(
            source,
            blocks=blocks,
            page_count=page_count,
            issues=issues,
        )


class ExtractorRegistry:
    def __init__(self, extractors: tuple[SourceExtractor, ...]) -> None:
        self._extractors = extractors

    @classmethod
    def default(cls) -> ExtractorRegistry:
        return cls(
            (
                PdfExtractor(),
                DocxExtractor(),
                MarkdownExtractor(),
                TextExtractor(),
            )
        )

    def extract(self, source: SourceFile) -> ExtractedDocument:
        _validate_source(source)
        extractor = next(
            (item for item in self._extractors if item.supports(source)),
            None,
        )
        if extractor is None:
            raise SourceValidationError("unsupported enterprise document format")
        return extractor.extract(source)


def _validate_source(source: SourceFile) -> None:
    if source.size_bytes > MAX_SOURCE_BYTES:
        raise SourceValidationError("source exceeds the 15 MiB limit")
    if source.media_type not in _ALLOWED_MEDIA_TYPES[source.suffix]:
        raise SourceValidationError("file extension and MIME type do not agree")
    if source.suffix is SourceFormat.PDF and not source.content.startswith(b"%PDF-"):
        raise SourceValidationError("PDF signature does not match its extension")
    if source.suffix is SourceFormat.DOCX and not source.content.startswith(b"PK"):
        raise SourceValidationError("DOCX signature does not match its extension")


def _validate_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename.lower() for entry in entries}
            if len(entries) > MAX_DOCX_ENTRIES:
                raise SourceValidationError("DOCX contains too many archive entries")
            if sum(entry.file_size for entry in entries) > MAX_DOCX_EXPANDED_BYTES:
                raise SourceValidationError("DOCX expanded content is too large")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise SourceValidationError("encrypted DOCX is not supported")
            if "[content_types].xml" not in names or "word/document.xml" not in names:
                raise SourceValidationError("DOCX signature is incomplete")
            if any(name.endswith("vbaproject.bin") for name in names):
                raise SourceValidationError("macro-enabled documents are not supported")
    except zipfile.BadZipFile as exc:
        raise SourceValidationError("DOCX signature is invalid") from exc


def _table_to_markdown(table: Table) -> str:
    rows = [
        [cell.text.strip().replace("|", "\\|") for cell in row.cells]
        for row in table.rows
    ]
    if not rows or not any(any(cell for cell in row) for row in rows):
        return ""
    width = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(normalized_rows[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in normalized_rows[1:])
    return "\n".join(lines)


def _split_pdf_text(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]
