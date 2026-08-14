import { useCallback, useEffect, useState } from "react";
import {
  fetchAdminAudit,
  fetchAdminOverview,
  fetchDocuments,
  fetchLatestEvaluation,
  fetchSession,
  logout,
} from "./api";
import { DocumentLibraryView } from "./components/DocumentLibraryView";
import { EvaluationView } from "./components/EvaluationView";
import { ImportReviewView } from "./components/ImportReviewView";
import { Navigation } from "./components/Navigation";
import { OverviewView } from "./components/OverviewView";
import { RetrievalLabView } from "./components/RetrievalLabView";
import LoginPage from "./LoginPage";
import type { AdminAuditEvent, AdminOverview, AppView, EvaluationOverview, ManagedDocument, SessionInfo } from "./types";
import "./styles.css";

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [activeView, setActiveView] = useState<AppView>("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [documents, setDocuments] = useState<ManagedDocument[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationOverview>({ status: "not_run" });
  const [audit, setAudit] = useState<AdminAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAdminData = useCallback(async () => {
    setLoading(true);
    const [overviewResult, documentsResult, evaluationResult, auditResult] = await Promise.allSettled([
      fetchAdminOverview(),
      fetchDocuments(),
      fetchLatestEvaluation(),
      fetchAdminAudit(),
    ]);
    if (overviewResult.status === "fulfilled") setOverview(overviewResult.value);
    if (documentsResult.status === "fulfilled") setDocuments(documentsResult.value);
    if (evaluationResult.status === "fulfilled") setEvaluation(evaluationResult.value);
    if (auditResult.status === "fulfilled") setAudit(auditResult.value);
    const failures = [overviewResult, documentsResult, evaluationResult, auditResult].filter((item) => item.status === "rejected").length;
    if (failures > 0) setNotice(failures === 4 ? "暂时无法读取管理数据" : "部分管理数据暂时不可用");
    setLoading(false);
  }, []);

  const refreshDocuments = useCallback(async () => {
    const [nextDocuments, nextOverview, nextAudit] = await Promise.all([
      fetchDocuments(),
      fetchAdminOverview(),
      fetchAdminAudit(),
    ]);
    setDocuments(nextDocuments);
    setOverview(nextOverview);
    setAudit(nextAudit);
  }, []);

  useEffect(() => {
    let active = true;
    fetchSession().then((value) => {
      if (!active) return;
      if (value.role !== "knowledge_admin") {
        setNeedsLogin(true);
        setLoading(false);
        return;
      }
      setSession(value);
      void loadAdminData();
    }).catch((error: Error & { status?: number }) => {
      if (!active) return;
      setNeedsLogin(error.status === 401 || error.status === 403);
      if (error.status !== 401 && error.status !== 403) setNotice(error.message);
      setLoading(false);
    });
    return () => { active = false; };
  }, [loadAdminData]);

  const notify = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 3200);
  };

  if (needsLogin || (!session && !loading)) {
    return <LoginPage onLogin={(value) => { setSession(value); setNeedsLogin(false); setActiveView("overview"); void loadAdminData(); }} />;
  }

  if (!session) return <div className="boot-screen"><span className="boot-mark" />正在连接知识控制台</div>;

  return <div className="app-shell">
    <Navigation active={activeView} onChange={setActiveView} session={session} onLogout={() => void logout().finally(() => { setSession(null); setNeedsLogin(true); })} />
    <section className="workspace">
      {activeView === "overview" ? <OverviewView overview={overview} audit={audit} loading={loading} onRefresh={() => void loadAdminData()} /> : null}
      {activeView === "documents" ? <DocumentLibraryView documents={documents} onChanged={refreshDocuments} onNotify={notify} /> : null}
      {activeView === "imports" ? <ImportReviewView onIndexed={refreshDocuments} /> : null}
      {activeView === "retrieval" ? <RetrievalLabView onNotify={notify} /> : null}
      {activeView === "evaluation" ? <EvaluationView evaluation={evaluation} /> : null}
    </section>
    {notice ? <div className="toast" role="status">{notice}</div> : null}
  </div>;
}
