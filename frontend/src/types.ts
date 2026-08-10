export type ResultStatus = "success" | "degraded" | "refused" | "failed";

export interface SessionInfo {
  user_id: string;
  role: "employee" | "department_admin" | "knowledge_admin";
  departments: string[];
  public_demo_mode: boolean;
}

export interface Citation {
  evidence_id: string;
  label: string;
}

export interface RetrievalEvidence {
  evidence_id: string;
  chunk_id: string;
  document_id: string;
  title: string;
  section_path: string[];
  version: string;
  effective_from: string;
  quote: string;
  retrieval_channels: string[];
  retrieval_rank: number;
  reranker_score: number | null;
}

export interface ChatRequest {
  question: string;
  session_id?: string;
  as_of?: string;
}

export interface ChatResult {
  status: ResultStatus;
  answer: string;
  citations: Citation[];
  evidence: RetrievalEvidence[];
  refusal_reason?: string | null;
  degradation_reason?: string | null;
}

export interface ProgressEvent {
  stage: string;
  label: string;
  status: string;
}

export interface DocumentOverview {
  document_id: string;
  title: string;
  version: string;
  department: string;
  visibility: string;
  status: string;
  effective_from: string;
  effective_to: string | null;
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
  document_type: "policy" | "process" | "handbook" | "faq";
  department: string;
  visibility: "public" | "department" | "restricted";
  allowed_roles: SessionInfo["role"][];
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

export type AppView = "chat" | "knowledge" | "evaluation";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: ChatResult;
}
