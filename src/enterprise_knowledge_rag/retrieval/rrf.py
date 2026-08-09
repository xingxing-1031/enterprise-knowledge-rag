from collections.abc import Mapping, Sequence

from enterprise_knowledge_rag.models import RetrievalCandidate


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[RetrievalCandidate]],
    *,
    k: int = 60,
    limit: int | None = None,
) -> list[RetrievalCandidate]:
    """Fuse independent rankings without comparing their raw score scales."""

    if k < 1:
        raise ValueError("k must be positive")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    candidates: dict[str, RetrievalCandidate] = {}
    scores: dict[str, float] = {}
    channels: dict[str, set[str]] = {}
    channel_ranks: dict[str, dict[str, int]] = {}

    for channel, ranking in rankings.items():
        seen_in_channel: set[str] = set()
        for rank, candidate in enumerate(ranking, start=1):
            chunk_id = candidate.chunk.chunk_id
            if chunk_id in seen_in_channel:
                continue
            seen_in_channel.add(chunk_id)
            candidates.setdefault(chunk_id, candidate)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            channels.setdefault(chunk_id, set()).add(channel)
            channel_ranks.setdefault(chunk_id, {})[channel] = rank

    ordered_ids = sorted(
        candidates,
        key=lambda chunk_id: (
            -scores[chunk_id],
            min(channel_ranks[chunk_id].values()),
            chunk_id,
        ),
    )
    if limit is not None:
        ordered_ids = ordered_ids[:limit]

    return [
        candidates[chunk_id].model_copy(
            update={
                "channels": channels[chunk_id],
                "channel_ranks": channel_ranks[chunk_id],
                "retrieval_score": scores[chunk_id],
            }
        )
        for chunk_id in ordered_ids
    ]
