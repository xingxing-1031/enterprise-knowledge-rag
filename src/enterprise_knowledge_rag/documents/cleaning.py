from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict

from .source_models import (
    CleanedDocument,
    CleaningIssue,
    CleaningReport,
    ExtractedBlock,
    ExtractedBlockKind,
    ExtractedDocument,
    IssueSeverity,
)

_PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:第\s*)?\d{1,4}(?:\s*页)?(?:\s*/\s*\d{1,4})?$",
    re.IGNORECASE,
)
_INJECTION_PATTERNS = (
    "忽略系统指令",
    "忽略之前的指令",
    "泄露其他文档",
    "ignore system instruction",
    "ignore previous instruction",
)


class DocumentCleaningService:
    def clean(self, document: ExtractedDocument) -> CleanedDocument:
        original_blocks = list(document.blocks)
        normalized = [_normalize_block(block) for block in original_blocks]
        issues = list(document.issues)

        page_furniture_orders = _repeated_page_furniture_orders(
            normalized,
            document.page_count,
        )
        if page_furniture_orders:
            issues.append(
                CleaningIssue(
                    code="repeated_page_furniture",
                    severity=IssueSeverity.INFO,
                    message="已移除多页重复出现的短页眉或页脚。",
                    block_orders=sorted(page_furniture_orders),
                )
            )

        cleaned_blocks: list[ExtractedBlock] = []
        removed_page_numbers = 0
        removed_duplicates = 0
        seen_nonconsecutive: set[str] = set()
        previous_text: str | None = None
        for block in normalized:
            if block.order in page_furniture_orders:
                continue
            if _PAGE_NUMBER_PATTERN.fullmatch(block.text):
                removed_page_numbers += 1
                continue
            if block.text == previous_text:
                removed_duplicates += 1
                continue
            if block.text in seen_nonconsecutive:
                issues.append(
                    CleaningIssue(
                        code="repeated_content_review",
                        severity=IssueSeverity.WARNING,
                        message="发现跨位置重复正文，已保留并等待人工核对。",
                        block_orders=[block.order],
                    )
                )
            cleaned_blocks.append(block)
            seen_nonconsecutive.add(block.text)
            previous_text = block.text

        if removed_page_numbers:
            issues.append(
                CleaningIssue(
                    code="page_numbers_removed",
                    severity=IssueSeverity.INFO,
                    message=f"已移除 {removed_page_numbers} 个纯页码段落。",
                )
            )
        if removed_duplicates:
            issues.append(
                CleaningIssue(
                    code="consecutive_duplicates_removed",
                    severity=IssueSeverity.INFO,
                    message=f"已移除 {removed_duplicates} 个连续重复段落。",
                )
            )

        combined_text = "\n".join(block.text for block in cleaned_blocks).lower()
        if any(pattern in combined_text for pattern in _INJECTION_PATTERNS):
            issues.append(
                CleaningIssue(
                    code="document_prompt_injection",
                    severity=IssueSeverity.WARNING,
                    message="文档包含疑似提示词指令，只按普通知识文本处理。",
                )
            )

        normalized_markdown = _render_markdown(cleaned_blocks)
        if not normalized_markdown and not any(
            issue.severity is IssueSeverity.BLOCKING for issue in issues
        ):
            issues.append(
                CleaningIssue(
                    code="empty_document",
                    severity=IssueSeverity.BLOCKING,
                    message="文档清洗后没有可索引正文。",
                )
            )

        report = CleaningReport(
            characters_before=sum(len(block.text) for block in original_blocks),
            characters_after=len(normalized_markdown),
            blocks_before=len(original_blocks),
            blocks_after=len(cleaned_blocks),
            table_count=sum(
                block.kind is ExtractedBlockKind.TABLE for block in cleaned_blocks
            ),
            content_hash=hashlib.sha256(normalized_markdown.encode("utf-8")).hexdigest(),
            issues=issues,
        )
        return CleanedDocument(
            original_filename=document.original_filename,
            source_hash=document.source_hash,
            normalized_markdown=normalized_markdown,
            blocks=cleaned_blocks,
            report=report,
        )


def _normalize_block(block: ExtractedBlock) -> ExtractedBlock:
    text = unicodedata.normalize("NFKC", block.text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        char
        for char in text
        if char in {"\n", "\t"} or unicodedata.category(char) != "Cc"
    )
    if block.kind is ExtractedBlockKind.TABLE:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
    else:
        text = re.sub(r"\s+", " ", text).strip()
    return block.model_copy(update={"text": text})


def _repeated_page_furniture_orders(
    blocks: list[ExtractedBlock],
    page_count: int | None,
) -> set[int]:
    if page_count is None or page_count < 2:
        return set()
    by_page: dict[int, list[ExtractedBlock]] = defaultdict(list)
    for block in blocks:
        if block.page_number is not None:
            by_page[block.page_number].append(block)

    edge_blocks: list[ExtractedBlock] = []
    for page_blocks in by_page.values():
        if page_blocks:
            edge_blocks.append(page_blocks[0])
            if len(page_blocks) > 1:
                edge_blocks.append(page_blocks[-1])
    counts = Counter(
        block.text
        for block in edge_blocks
        if 0 < len(block.text) <= 120 and not _PAGE_NUMBER_PATTERN.fullmatch(block.text)
    )
    threshold = max(2, math.ceil(page_count * 0.6))
    repeated = {text for text, count in counts.items() if count >= threshold}
    return {block.order for block in edge_blocks if block.text in repeated}


def _render_markdown(blocks: list[ExtractedBlock]) -> str:
    rendered: list[str] = []
    for block in blocks:
        if block.kind is ExtractedBlockKind.HEADING:
            rendered.append(f"{'#' * (block.heading_level or 1)} {block.text}")
        elif block.kind is ExtractedBlockKind.LIST_ITEM:
            rendered.append(f"- {block.text}")
        else:
            rendered.append(block.text)
    return "\n\n".join(rendered).strip()
