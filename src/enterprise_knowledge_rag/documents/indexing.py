from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.models import ChunkRecord, DocumentRecord, IndexingSummary

from .chunker import chunk_document
from .parser import DocumentParseError, parse_document


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class IndexRepository(Protocol):
    def get_content_hash(self, document_id: str, version: str) -> str | None: ...

    def has_embeddings(
        self,
        document_id: str,
        version: str,
        embedding_model: str,
    ) -> bool: ...

    def find_document_by_hash(self, content_hash: str) -> tuple[str, str] | None: ...

    def upsert_document(
        self,
        document: DocumentRecord,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...


class IndexingService:
    def __init__(
        self,
        repository: IndexRepository,
        embeddings: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._settings = settings

    def index_paths(self, paths: Sequence[Path]) -> IndexingSummary:
        indexed = 0
        skipped = 0
        failed = 0
        chunk_count = 0
        errors: list[str] = []

        for path in paths:
            try:
                parsed = parse_document(path)
                current_hash = self._repository.get_content_hash(
                    parsed.record.document_id,
                    parsed.record.version,
                )
                if (
                    current_hash == parsed.record.content_hash
                    and self._repository.has_embeddings(
                        parsed.record.document_id,
                        parsed.record.version,
                        self._settings.embedding_model,
                    )
                ):
                    skipped += 1
                    continue

                duplicate = self._repository.find_document_by_hash(
                    parsed.record.content_hash
                )
                identity = (parsed.record.document_id, parsed.record.version)
                if duplicate is not None and duplicate != identity:
                    raise ValueError(
                        "duplicate content already indexed as "
                        f"{duplicate[0]}@{duplicate[1]}"
                    )

                chunks = chunk_document(
                    parsed,
                    embedding_model=self._settings.embedding_model,
                )
                vectors = self._embeddings.embed_documents(
                    [chunk.content for chunk in chunks]
                )
                self._repository.upsert_document(parsed.record, chunks, vectors)
                indexed += 1
                chunk_count += len(chunks)
            except (DocumentParseError, OSError, ValueError, RuntimeError) as exc:
                failed += 1
                errors.append(f"{path.name}: {exc}")

        return IndexingSummary(
            discovered=len(paths),
            indexed=indexed,
            skipped=skipped,
            failed=failed,
            chunk_count=chunk_count,
            errors=errors,
        )
