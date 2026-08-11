import {
  BookOpenText,
  ChartNoAxesCombined,
  LogOut,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";

import type { AppView, SessionInfo } from "../types";


const NAV_ITEMS = [
  { id: "chat" as const, label: "知识问答", icon: MessageSquareText },
  { id: "knowledge" as const, label: "知识库", icon: BookOpenText },
  { id: "evaluation" as const, label: "评测", icon: ChartNoAxesCombined },
];


interface NavigationProps {
  active: AppView;
  onChange: (view: AppView) => void;
  session: SessionInfo | null;
  onLogout: () => void;
}


const ROLE_LABELS: Record<SessionInfo["role"], string> = {
  employee: "普通员工",
  department_admin: "部门管理员",
  knowledge_admin: "知识库管理员",
};


export function Navigation({ active, onChange, session, onLogout }: NavigationProps) {
  return (
    <aside className="navigation" aria-label="主导航">
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true">
          <ShieldCheck size={20} strokeWidth={1.8} />
        </span>
        <div>
          <strong>制度智查</strong>
          <span>企业知识工作台</span>
        </div>
      </div>

      <nav className="nav-items">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={active === item.id ? "nav-item is-active" : "nav-item"}
              key={item.id}
              type="button"
              onClick={() => onChange(item.id)}
              aria-current={active === item.id ? "page" : undefined}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="identity-block">
        <span className="identity-dot" aria-hidden="true" />
        <div>
          <strong>{session ? ROLE_LABELS[session.role] : "正在识别身份"}</strong>
          <span>{session?.public_demo_mode ? "公开演示身份" : "可信会话"}</span>
        </div>
        {session ? (
          <button className="logout-button" type="button" onClick={onLogout} title="退出登录">
            <LogOut size={16} />
            <span>退出</span>
          </button>
        ) : null}
      </div>
    </aside>
  );
}
