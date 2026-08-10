from collections.abc import Sequence

from enterprise_knowledge_rag.models import RetrievalCandidate, RetrievalEvidence


def build_minimal_evidence(
    candidates: Sequence[RetrievalCandidate],
    *,
    max_items: int = 4,
    max_tokens: int = 900,
    min_reranker_score: float = 0.0,
) -> list[RetrievalEvidence]:
    if max_items < 1 or max_tokens < 1:
        raise ValueError("evidence limits must be positive")

    evidence: list[RetrievalEvidence] = []
    seen_content_hashes: set[str] = set()
    selected_versions: dict[str, str] = {}
    used_tokens = 0

    for candidate in candidates:
        score = candidate.reranker_score
        if score is None and min_reranker_score > 0:
            continue
        if score is not None and score < min_reranker_score:
            continue
        chunk = candidate.chunk
        document = candidate.document
        selected_version = selected_versions.setdefault(
            document.document_id,
            document.version,
        )
        if selected_version != document.version:
            continue
        if chunk.content_hash in seen_content_hashes:
            continue
        if used_tokens + chunk.token_count > max_tokens:
            continue

        evidence.append(
            RetrievalEvidence(
                evidence_id=f"ev:{chunk.chunk_id}",
                chunk_id=chunk.chunk_id,
                document_id=document.document_id,
                title=document.title,
                section_path=chunk.section_path,
                version=document.version,
                effective_from=document.effective_from,
                quote=chunk.content,
                retrieval_channels=candidate.channels,
                retrieval_rank=len(evidence) + 1,
                reranker_score=score,
                supports_need_ids=candidate.supports_need_ids,
                retrieval_hop=candidate.retrieval_hop,
            )
        )
        seen_content_hashes.add(chunk.content_hash)
        used_tokens += chunk.token_count
        if len(evidence) >= max_items:
            break

    return evidence
