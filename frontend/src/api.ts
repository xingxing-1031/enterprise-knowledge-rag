import type {
  ChatRequest,
  ChatResult,
  DocumentOverview,
  EvaluationOverview,
  ImportMetadata,
  KnowledgeImport,
  ProgressEvent,
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
  return response.json() as Promise<T>;
}


export function fetchSession(): Promise<SessionInfo> {
  return requestJson<SessionInfo>("/session");
}


export function fetchDocuments(): Promise<DocumentOverview[]> {
  return requestJson<DocumentOverview[]>("/documents");
}


export function fetchLatestEvaluation(): Promise<EvaluationOverview> {
  return requestJson<EvaluationOverview>("/evaluations/latest");
}

export function fetchKnowledgeImports(): Promise<KnowledgeImport[]> {
  return requestJson<KnowledgeImport[]>("/knowledge/imports");
}

export function uploadKnowledgeDocument(
  file: File,
  metadata: ImportMetadata,
): Promise<KnowledgeImport> {
  const body = new FormData();
  body.append("file", file);
  body.append("metadata", JSON.stringify(metadata));
  return requestJson<KnowledgeImport>("/knowledge/imports", {
    method: "POST",
    body,
  });
}

export function approveKnowledgeImport(
  importId: string,
  metadata: ImportMetadata,
): Promise<KnowledgeImport> {
  return requestJson<KnowledgeImport>(`/knowledge/imports/${importId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
}


export function login(username: string, password: string): Promise<SessionInfo> {
  return requestJson<SessionInfo>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}


export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "same-origin",
  });
}


export async function clearChat(request: ChatRequest): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/clear`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`清空会话失败（${response.status}）`);
  }
}


function parseBlock(block: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) };
}


export async function streamChat(
  request: ChatRequest,
  onProgress: (event: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResult> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`知识服务暂时不可用（${response.status}）`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResult | null = null;

  const consume = (block: string) => {
    const parsed = parseBlock(block);
    if (!parsed) return;
    if (parsed.event === "progress") {
      onProgress(parsed.data as ProgressEvent);
    } else if (parsed.event === "result") {
      result = parsed.data as ChatResult;
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    blocks.forEach(consume);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!result) throw new Error("知识服务未返回完整结果");
  return result;
}
