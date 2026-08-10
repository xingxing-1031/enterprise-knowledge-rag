import { useEffect, useRef, useState } from "react";

import {
  clearChat,
  fetchDocuments,
  fetchLatestEvaluation,
  fetchSession,
  streamChat,
} from "./api";
import { ChatView } from "./components/ChatView";
import { EvaluationView } from "./components/EvaluationView";
import { EvidencePanel } from "./components/EvidencePanel";
import { KnowledgeView } from "./components/KnowledgeView";
import { Navigation } from "./components/Navigation";
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
  const [documents, setDocuments] = useState<DocumentOverview[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationOverview>({ status: "not_run" });
  const [metadataLoading, setMetadataLoading] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [evidence, setEvidence] = useState<RetrievalEvidence[]>([]);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.allSettled([fetchSession(), fetchDocuments(), fetchLatestEvaluation()])
      .then(([sessionResult, documentResult, evaluationResult]) => {
        if (!mounted) return;
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

  return (
    <div className="app-shell">
      <Navigation active={activeView} onChange={setActiveView} session={session} />
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
              onOpenEvidence={() => setEvidenceOpen(true)}
            />
            <EvidencePanel evidence={evidence} mobileOpen={evidenceOpen} onClose={() => setEvidenceOpen(false)} />
            {evidenceOpen ? <button className="drawer-scrim" type="button" aria-label="关闭引用" onClick={() => setEvidenceOpen(false)} /> : null}
          </div>
        ) : null}
        {activeView === "knowledge" ? <KnowledgeView documents={documents} loading={metadataLoading} session={session} onDocumentsChanged={refreshDocuments} /> : null}
        {activeView === "evaluation" ? <EvaluationView evaluation={evaluation} /> : null}
      </section>
    </div>
  );
}
