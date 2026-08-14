import { LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { login } from "./api";
import type { SessionInfo } from "./types";

export default function LoginPage({ onLogin }: { onLogin: (session: SessionInfo) => void }) {
  const [username, setUsername] = useState("knowledge-admin-demo");
  const [password, setPassword] = useState("KnowledgeAdmin2026!");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      onLogin(await login(username.trim(), password));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "登录失败，请检查管理员凭据");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand"><span className="brand-mark large" aria-hidden="true"><ShieldCheck size={25} /></span><div><strong>知库控制台</strong><span>Enterprise Knowledge Control Plane</span></div></div>
        <div className="login-copy"><span className="panel-kicker">受控访问</span><h1 id="login-title">管理员登录</h1><p>文档入库、权限检索、索引维护和评测报告都在这里完成。</p></div>
        <form className="login-form" onSubmit={(event) => void submit(event)}>
          <label htmlFor="username">管理员账号</label>
          <input id="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
          <label htmlFor="password">访问密码</label>
          <div className="password-field"><LockKeyhole size={16} aria-hidden="true" /><input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
          {error ? <div className="form-error" role="alert">{error}</div> : null}
          <button className="primary-button" disabled={submitting} type="submit">{submitting ? "正在验证" : "进入管理控制台"}</button>
        </form>
        <div className="login-footnote"><span className="status-dot" aria-hidden="true" />仅允许知识库管理员访问，普通用户通过项目一的内部证据接口获取知识。</div>
      </section>
    </main>
  );
}
