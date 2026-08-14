import { Archive, BarChart3, Database, FileCheck2, FileText, LayoutDashboard, LogOut, SearchCheck, ShieldCheck } from "lucide-react";
import type { AppView, SessionInfo } from "../types";

const ITEMS: Array<{ id: AppView; label: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "总览", icon: LayoutDashboard },
  { id: "documents", label: "文档库", icon: Database },
  { id: "imports", label: "导入审核", icon: FileCheck2 },
  { id: "retrieval", label: "检索实验室", icon: SearchCheck },
  { id: "evaluation", label: "评测中心", icon: BarChart3 },
];

export function Navigation({ active, onChange, session, onLogout }: {
  active: AppView;
  onChange: (view: AppView) => void;
  session: SessionInfo;
  onLogout: () => void;
}) {
  return (
    <aside className="navigation" aria-label="管理员导航">
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true"><ShieldCheck size={19} /></span>
        <div><strong>知库控制台</strong><span>企业知识治理</span></div>
      </div>
      <div className="workspace-label">管理工作区</div>
      <nav className="nav-items">
        {ITEMS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={active === id ? "nav-item is-active" : "nav-item"} type="button" onClick={() => onChange(id)} aria-current={active === id ? "page" : undefined}>
            <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="identity-block">
        <span className="identity-dot" aria-hidden="true" />
        <div><strong>知识库管理员</strong><span>{session.user_id}</span></div>
        <button className="logout-button" type="button" onClick={onLogout} aria-label="退出登录" title="退出登录"><LogOut size={16} /></button>
      </div>
    </aside>
  );
}
