import type {
  AdminAuditEvent,
  AdminOverview,
  DeleteResult,
  EvaluationOverview,
  ImportMetadata,
  KnowledgeImport,
  ManagedDocument,
  RetrievalDebugResponse,
  SessionInfo,
} from "./types";

const API_BASE = import.meta.env.DEV ? "/api" : "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    const error = new Error(payload?.detail ?? `服务请求失败（${response.status}）`);
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const fetchSession = () => requestJson<SessionInfo>("/session");
export const fetchAdminOverview = () => requestJson<AdminOverview>("/admin/overview");
export const fetchDocuments = () => requestJson<ManagedDocument[]>("/documents");
export const fetchLatestEvaluation = () => requestJson<EvaluationOverview>("/evaluations/latest");
export const fetchAdminAudit = (limit = 20) => requestJson<AdminAuditEvent[]>(`/admin/audit?limit=${limit}`);
export const fetchKnowledgeImports = () => requestJson<KnowledgeImport[]>("/knowledge/imports");

export function uploadKnowledgeDocument(file: File, metadata: ImportMetadata): Promise<KnowledgeImport> {
  const body = new FormData();
  body.append("file", file);
  body.append("metadata", JSON.stringify(metadata));
  return requestJson<KnowledgeImport>("/knowledge/imports", { method: "POST", body });
}

export function approveKnowledgeImport(importId: string, metadata: ImportMetadata): Promise<KnowledgeImport> {
  return requestJson<KnowledgeImport>(`/knowledge/imports/${importId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
}

export const login = (username: string, password: string) => requestJson<SessionInfo>("/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
});

export async function logout(): Promise<void> {
  await requestJson<void>("/auth/logout", { method: "POST" });
}

export function indexDocuments() {
  return requestJson<Record<string, unknown>>("/documents/index", { method: "POST" });
}

export function deactivateDocument(documentId: string, version: string) {
  return requestJson<ManagedDocument>(`/admin/documents/${encodeURIComponent(documentId)}/${encodeURIComponent(version)}/deactivate`, { method: "POST" });
}

export function restoreDocument(documentId: string, version: string) {
  return requestJson<ManagedDocument>(`/admin/documents/${encodeURIComponent(documentId)}/${encodeURIComponent(version)}/restore`, { method: "POST" });
}

export function reindexDocument(documentId: string, version: string) {
  return requestJson<ManagedDocument>(`/admin/documents/${encodeURIComponent(documentId)}/${encodeURIComponent(version)}/reindex`, { method: "POST" });
}

export function deleteDocument(documentId: string, version: string, confirmation: string) {
  return requestJson<DeleteResult>(`/admin/documents/${encodeURIComponent(documentId)}/${encodeURIComponent(version)}?confirmation=${encodeURIComponent(confirmation)}`, { method: "DELETE" });
}

export function debugRetrieval(payload: { query: string; simulated_role: string; simulated_departments: string[]; top_k: number; strategy: string }) {
  return requestJson<RetrievalDebugResponse>("/admin/retrieval/debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
