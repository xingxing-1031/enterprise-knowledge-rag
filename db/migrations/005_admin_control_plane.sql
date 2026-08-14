CREATE TABLE IF NOT EXISTS knowledge_admin_audit (
    event_id UUID PRIMARY KEY,
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    document_ref_hash CHAR(64),
    version TEXT,
    result TEXT NOT NULL,
    reason_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_admin_audit_created
    ON knowledge_admin_audit (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status
    ON knowledge_documents (status);
