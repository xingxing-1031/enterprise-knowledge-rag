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
