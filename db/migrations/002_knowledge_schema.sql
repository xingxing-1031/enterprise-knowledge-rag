CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL,
    department TEXT NOT NULL,
    visibility TEXT NOT NULL,
    allowed_roles TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    supersedes_id TEXT,
    content_hash CHAR(64) NOT NULL,
    source_path TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (document_id, version),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    document_version TEXT NOT NULL,
    section_path TEXT[] NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    content_hash CHAR(64) NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    FOREIGN KEY (document_id, document_version)
        REFERENCES knowledge_documents (document_id, version)
        ON DELETE CASCADE,
    UNIQUE (document_id, document_version, chunk_index)
);

CREATE TABLE IF NOT EXISTS knowledge_indexing_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    discovered INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb
);

