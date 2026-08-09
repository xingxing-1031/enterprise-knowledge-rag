CREATE INDEX IF NOT EXISTS idx_documents_current
    ON knowledge_documents (status, effective_from, effective_to);

CREATE INDEX IF NOT EXISTS idx_documents_visibility
    ON knowledge_documents (visibility, department);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash
    ON knowledge_documents (content_hash);

CREATE INDEX IF NOT EXISTS idx_chunks_document
    ON knowledge_chunks (document_id, document_version, chunk_index);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

