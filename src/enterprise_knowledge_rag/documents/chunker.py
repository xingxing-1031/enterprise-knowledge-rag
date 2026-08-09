import hashlib
import re
from dataclasses import dataclass

from enterprise_knowledge_rag.models import ChunkRecord

from .parser import ParsedDocument

HEADING_PATTERN = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]")


@dataclass(frozen=True, slots=True)
class Section:
    path: tuple[str, ...]
    blocks: tuple[str, ...]


def estimate_tokens(text: str) -> int:
    """Deterministic approximation used for chunk budgets and tests."""

    return len(TOKEN_PATTERN.findall(text))


def _sections(body: str) -> list[Section]:
    heading_stack: list[str] = []
    blocks: list[str] = []
    current_lines: list[str] = []
    sections: list[Section] = []

    def flush_block() -> None:
        nonlocal current_lines
        block = "\n".join(current_lines).strip()
        if block:
            blocks.append(block)
        current_lines = []

    def flush_section() -> None:
        nonlocal blocks
        flush_block()
        if blocks:
            path = tuple(heading_stack) or ("正文",)
            sections.append(Section(path=path, blocks=tuple(blocks)))
        blocks = []

    for raw_line in body.splitlines():
        heading = HEADING_PATTERN.match(raw_line)
        if heading:
            flush_section()
            level = len(heading.group("marks"))
            title = heading.group("title").strip()
            heading_stack[level - 1 :] = [title]
            continue
        if raw_line.strip():
            current_lines.append(raw_line.rstrip())
        else:
            flush_block()
    flush_section()
    return sections


def _split_oversized_block(block: str, max_tokens: int) -> list[str]:
    if estimate_tokens(block) <= max_tokens:
        return [block]

    lines = [line for line in block.splitlines() if line.strip()]
    if len(lines) > 1:
        parts: list[str] = []
        current: list[str] = []
        for line in lines:
            candidate = "\n".join([*current, line])
            if current and estimate_tokens(candidate) > max_tokens:
                parts.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            parts.append("\n".join(current))
        if all(estimate_tokens(part) <= max_tokens for part in parts):
            return parts

    tokens = TOKEN_PATTERN.findall(block)
    return [
        "".join(tokens[index : index + max_tokens])
        for index in range(0, len(tokens), max_tokens)
    ]


def _stable_chunk_id(
    document_id: str,
    version: str,
    section_path: tuple[str, ...],
    chunk_index: int,
    content: str,
) -> str:
    identity = "|".join(
        [document_id, version, ">".join(section_path), str(chunk_index), content]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{document_id}@{version}:{chunk_index}:{digest}"


def chunk_document(
    document: ParsedDocument,
    *,
    max_tokens: int = 320,
    overlap_tokens: int = 40,
    embedding_model: str = "BAAI/bge-m3",
) -> list[ChunkRecord]:
    """Create deterministic chunks without crossing heading sections."""

    if max_tokens < 16:
        raise ValueError("max_tokens must be at least 16")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be between 0 and max_tokens")

    records: list[ChunkRecord] = []
    chunk_index = 0
    for section in _sections(document.body):
        expanded_blocks = [
            part
            for block in section.blocks
            for part in _split_oversized_block(block, max_tokens)
        ]
        current: list[str] = []
        previous_tail = ""

        def emit() -> None:
            nonlocal chunk_index, current, previous_tail
            if not current:
                return
            content = "\n\n".join(current).strip()
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            records.append(
                ChunkRecord(
                    chunk_id=_stable_chunk_id(
                        document.record.document_id,
                        document.record.version,
                        section.path,
                        chunk_index,
                        content,
                    ),
                    document_id=document.record.document_id,
                    section_path=list(section.path),
                    chunk_index=chunk_index,
                    content=content,
                    token_count=estimate_tokens(content),
                    content_hash=content_hash,
                    embedding_model=embedding_model,
                )
            )
            tokens = TOKEN_PATTERN.findall(content)
            previous_tail = "".join(tokens[-overlap_tokens:]) if overlap_tokens else ""
            chunk_index += 1
            current = []

        for block in expanded_blocks:
            candidate_parts = [*current, block]
            candidate = "\n\n".join(candidate_parts)
            if current and estimate_tokens(candidate) > max_tokens:
                emit()
                current = [previous_tail, block] if previous_tail else [block]
                if estimate_tokens("\n\n".join(current)) > max_tokens:
                    current = [block]
            else:
                current.append(block)
        emit()

    return records
