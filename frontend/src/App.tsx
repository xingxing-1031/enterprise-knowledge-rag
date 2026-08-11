import { useEffect, useRef, useState } from "react";

import {
  clearChat,
  fetchDocuments,
  fetchLatestEvaluation,
  fetchSession,
  logout,
  streamChat,
} from "./api";
import { ChatView } from "./components/ChatView";
import { EvaluationView } from "./components/EvaluationView";
import { EvidencePanel } from "./components/EvidencePanel";
import { KnowledgeView } from "./components/KnowledgeView";
import { Navigation } from "./components/Navigation";
import LoginPage from "./LoginPage";
import type {
  AppView,
  ChatMessage,
  DocumentOverview,
  EvaluationOverview,
  ProgressEvent,
  RetrievalEvidence,
  SessionInfo,
} from "./types";
import "./styles.css";


const SESSION_ID = "public-demo-session";


export default function App() {
  const [activeView, setActiveView] = useState<AppView>("chat");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [documents, setDocuments] = useState<DocumentOverview[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationOverview>({ status: "not_run" });
  const [metadataLoading, setMetadataLoading] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [evidence, setEvidence] = useState<RetrievalEvidence[]>([]);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestAbort = useRef<AbortController | null>(null);
  const evidenceFlashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.allSettled([fetchSession(), fetchDocuments(), fetchLatestEvaluation()])
      .then(([sessionResult, documentResult, evaluationResult]) => {
        if (!mounted) return;
        if (sessionResult.status === "rejected") {
          const status = (sessionResult.reason as { status?: number } | undefined)?.status;
          if (status === 401) {
            setNeedsLogin(true);
            setMetadataLoading(false);
            return;
          }
        }
        if (sessionResult.status === "fulfilled") setSession(sessionResult.value);
        if (documentResult.status === "fulfilled") setDocuments(documentResult.value);
        if (evaluationResult.status === "fulfilled") setEvaluation(evaluationResult.value);
        const failedCount = [sessionResult, documentResult, evaluationResult].filter(
          (result) => result.status === "rejected",
        ).length;
        if (failedCount > 0) {
          setError(
            failedCount === 3
              ? "暂时无法读取服务状态，请稍后刷新页面。"
              : "部分服务状态暂时不可用，已保留可用信息。",
          );
        }
      })
      .finally(() => {
        if (mounted) setMetadataLoading(false);
      });
    return () => {
      mounted = false;
      requestAbort.current?.abort();
      if (evidenceFlashTimer.current) clearTimeout(evidenceFlashTimer.current);
    };
  }, []);

  const submitQuestion = async (submittedQuestion: string) => {
    const normalized = submittedQuestion.trim();
    if (!normalized || loading) return;
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: normalized,
    };
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setError(null);
    setProgress([]);
    setLoading(true);
    requestAbort.current?.abort();
    const controller = new AbortController();
    requestAbort.current = controller;
    try {
      const result = await streamChat(
        { question: normalized, session_id: SESSION_ID },
        (event) => setProgress((current) => [...current, event]),
        controller.signal,
      );
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: result.answer,
          result,
        },
      ]);
      setEvidence(result.evidence);
    } catch (requestError) {
      if (!(requestError instanceof DOMException && requestError.name === "AbortError")) {
        setError(requestError instanceof Error ? requestError.message : "知识服务暂时不可用");
      }
    } finally {
      if (requestAbort.current === controller) {
        requestAbort.current = null;
        setLoading(false);
      }
    }
  };

  const handleClear = async () => {
    try {
      await clearChat({ question: "清空会话", session_id: SESSION_ID });
      setMessages([]);
      setEvidence([]);
      setProgress([]);
      setError(null);
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : "清空会话失败");
    }
  };

  const refreshDocuments = async () => {
    const refreshed = await fetchDocuments();
    setDocuments(refreshed);
  };

  const handleOpenEvidence = (index: number) => {
    const target = evidence[index];
    setEvidenceOpen(true);
    if (!target) return;
    setActiveEvidenceId(target.evidence_id);
    if (evidenceFlashTimer.current) clearTimeout(evidenceFlashTimer.current);
    evidenceFlashTimer.current = setTimeout(() => setActiveEvidenceId(null), 2500);
  };

  const handleLogin = async (loginSession: SessionInfo) => {
    setSession(loginSession);
    setNeedsLogin(false);
    setError(null);
    setMessages([]);
    setEvidence([]);
    const [documentResult, evaluationResult] = await Promise.allSettled([
      fetchDocuments(),
      fetchLatestEvaluation(),
    ]);
    if (documentResult.status === "fulfilled") setDocuments(documentResult.value);
    if (evaluationResult.status === "fulfilled") setEvaluation(evaluationResult.value);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (logoutError) {
      // 会话可能已过期，忽略后仍回到登录页
    }
    setSession(null);
    setNeedsLogin(true);
    setActiveView("chat");
    setMessages([]);
    setEvidence([]);
    setDocuments([]);
    setEvaluation({ status: "not_run" });
    setProgress([]);
    setError(null);
  };

  if (needsLogin) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <Navigation
        active={activeView}
        onChange={setActiveView}
        session={session}
        onLogout={() => void handleLogout()}
      />
      <section className="workspace">
        {activeView === "chat" ? (
          <div className="chat-layout">
            <ChatView
              messages={messages}
              question={question}
              onQuestionChange={setQuestion}
              onSubmit={(event) => {
                event.preventDefault();
                void submitQuestion(question);
              }}
              onExample={(value) => void submitQuestion(value)}
              onClear={() => void handleClear()}
              progress={progress}
              loading={loading}
              error={error}
              evidence={evidence}
              onOpenEvidence={handleOpenEvidence}
            />
            <EvidencePanel evidence={evidence} mobileOpen={evidenceOpen} activeId={activeEvidenceId} onClose={() => setEvidenceOpen(false)} />
            {evidenceOpen ? <button className="drawer-scrim" type="button" aria-label="关闭引用" onClick={() => setEvidenceOpen(false)} /> : null}
          </div>
        ) : null}
        {activeView === "knowledge" ? <KnowledgeView documents={documents} loading={metadataLoading} session={session} onDocumentsChanged={refreshDocuments} /> : null}
        {activeView === "evaluation" ? <EvaluationView evaluation={evaluation} /> : null}
      </section>
    </div>
  );
}
