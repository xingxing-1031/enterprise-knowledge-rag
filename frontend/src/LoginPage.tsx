import { LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { FormEvent, useState } from "react";
import { login } from "./api";
import type { SessionInfo } from "./types";

const demoAccounts = [
  {
    username: "knowledge-admin-demo",
    password: "KnowledgeAdmin2026!",
    title: "知识库管理员",
    description: "可查看全部制度文档与入库审批，推荐用于整体演示。",
  },
  {
    username: "department-admin-demo",
    password: "DepartmentAdmin2026!",
    title: "部门管理员",
    description: "可访问本部门与受控文档，例如付款审批权限表。",
  },
  {
    username: "employee-demo",
    password: "EmployeeDemo2026!",
    title: "普通员工",
    description: "仅可见公开制度，敏感内容会被权限拦截。",
  },
] as const;

const TRUST_POINTS = ["按需多 Agent", "权限隔离", "证据可溯源"];

export default function LoginPage({
  onLogin,
}: {
  onLogin: (session: SessionInfo) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      onLogin(await login(username, password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand-panel">
          <div className="login-brand">
            <span className="logo-mark large" aria-hidden="true">
              <ShieldCheck size={24} strokeWidth={1.8} />
            </span>
            <h1>企业运营 Agent</h1>
          </div>
          <p className="login-hero">通用对话 · 企业知识 · 经营分析</p>
          <p className="login-tagline">
            普通问题直接对话，企业任务按需调用知识与数据 Agent。
            企业事实只使用授权证据，经营分析通过受治理工具执行。
          </p>
          <ul className="login-points">
            {TRUST_POINTS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <div className="login-demo-heading">
            <span className="login-demo-label">选择演示身份</span>
          </div>
          <div className="demo-account-list" aria-label="公开演示账号">
            {demoAccounts.map((account) => (
              <button
                className="demo-account"
                type="button"
                key={account.username}
                onClick={() => {
                  setUsername(account.username);
                  setPassword(account.password);
                }}
              >
                <span>
                  <strong>{account.title}</strong>
                  <small>{account.description}</small>
                </span>
                <code>{account.username}</code>
              </button>
            ))}
          </div>
        </div>

        <div className="login-form-area">
          <p className="login-subtitle">企业运营多 Agent 工作台 · 请选择演示身份登录</p>
          <label htmlFor="username">用户名</label>
          <div className="input-with-icon">
            <UserRound size={16} />
            <input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="请输入用户名"
              required
            />
          </div>
          <label htmlFor="password">密码</label>
          <div className="input-with-icon">
            <LockKeyhole size={16} />
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入密码"
              required
            />
          </div>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button login-submit" type="submit" disabled={submitting}>
            {submitting ? "正在登录" : "登录"}
          </button>
          <div className="login-notice">
            <span className="service-dot online" aria-hidden="true" />
            <p>公开演示数据 · 角色与权限均由服务器校验</p>
          </div>
        </div>
      </form>
    </main>
  );
}
