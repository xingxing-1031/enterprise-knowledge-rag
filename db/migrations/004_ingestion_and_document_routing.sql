CREATE TABLE IF NOT EXISTS knowledge_imports (
    import_id UUID PRIMARY KEY,
    source_hash CHAR(64) NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    suffix TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
    status TEXT NOT NULL CHECK (status IN (
        'uploaded', 'parsed', 'needs_review', 'approved', 'indexed',
        'quarantined', 'failed'
    )),
    metadata JSONB,
    cleaning_report JSONB,
    normalized_preview TEXT NOT NULL DEFAULT '',
    failure_type TEXT,
    uploaded_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS topic_tags TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS document_search_text TEXT,
    ADD COLUMN IF NOT EXISTS document_embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS document_embedding vector(1024);

CREATE INDEX IF NOT EXISTS idx_knowledge_imports_status_created
    ON knowledge_imports (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_parent_embedding_hnsw
    ON knowledge_documents USING hnsw (document_embedding vector_cosine_ops);
