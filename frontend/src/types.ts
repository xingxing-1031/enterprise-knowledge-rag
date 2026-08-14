export interface SessionInfo {
  user_id: string;
  role: "knowledge_admin";
  departments: string[];
  public_demo_mode: boolean;
}

export interface AdminOverview {
  document_count: number;
  active_count: number;
  inactive_count: number;
  needs_review_count: number;
  chunk_count: number;
  indexed_count: number;
  last_indexed_at: string | null;
  recent_audit_count: number;
}

export interface ManagedDocument {
  document_id: string;
  version: string;
  title: string;
  document_type: "policy" | "process" | "handbook" | "faq";
  department: string;
  visibility: "public" | "department" | "restricted";
  status: "draft" | "active" | "inactive" | "expired" | "revoked";
  effective_from: string;
  effective_to: string | null;
  topic_tags: string[];
  source_filename: string;
  chunk_count: number;
  indexed: boolean;
  indexed_at: string | null;
}

export type IngestionStatus =
  | "uploaded"
  | "parsed"
  | "needs_review"
  | "approved"
  | "indexed"
  | "quarantined"
  | "failed";

export interface ImportMetadata {
  document_id: string;
  title: string;
  document_type: ManagedDocument["document_type"];
  department: string;
  visibility: ManagedDocument["visibility"];
  allowed_roles: string[];
  version: string;
  effective_from: string;
  effective_to?: string | null;
  supersedes_id?: string | null;
  topic_tags: string[];
}

export interface CleaningIssue {
  code: string;
  severity: "info" | "warning" | "blocking";
  message: string;
  block_orders: number[];
}

export interface CleaningReport {
  characters_before: number;
  characters_after: number;
  blocks_before: number;
  blocks_after: number;
  table_count: number;
  content_hash: string;
  issues: CleaningIssue[];
  has_blocking_issues: boolean;
}

export interface KnowledgeImport {
  import_id: string;
  original_filename: string;
  source_hash: string;
  media_type: string;
  size_bytes: number;
  page_count: number | null;
  status: IngestionStatus;
  metadata: ImportMetadata | null;
  cleaning_report: CleaningReport | null;
  normalized_preview: string;
  failure_type: string | null;
  created_at: string;
  updated_at: string;
  can_approve: boolean;
}

export interface EvaluationOverview {
  status?: string;
  strategy?: string;
  corpus_snapshot?: string;
  metrics?: Record<string, number | null>;
  [key: string]: unknown;
}

export interface AdminAuditEvent {
  event_id: string;
  action: string;
  actor_id: string;
  document_ref_hash: string | null;
  version: string | null;
  result: string;
  reason_code: string | null;
  created_at: string;
}

export interface SafeDebugCandidate {
  document_id: string;
  version: string;
  title: string;
  department: string;
  chunk_id: string;
  channels: string[];
  channel_ranks: Record<string, number>;
  retrieval_score: number;
  reranker_score: number | null;
}

export interface RetrievalDebugStage {
  name: "authorization" | "bm25" | "vector" | "rrf" | "rerank" | "evidence";
  candidate_count: number;
  excluded_count: number;
  duration_ms: number;
  candidates: SafeDebugCandidate[];
  note?: string | null;
}

export interface RetrievalDebugResponse {
  query: string;
  strategy: string;
  simulated_role: string;
  simulated_departments: string[];
  status: string;
  stages: RetrievalDebugStage[];
  total_duration_ms: number;
}

export interface DeleteResult {
  deleted: boolean;
  document_id: string;
  version: string;
  chunk_count: number;
  source_removed: boolean;
  tombstone_recorded: boolean;
}

export type AppView = "overview" | "documents" | "imports" | "retrieval" | "evaluation";
