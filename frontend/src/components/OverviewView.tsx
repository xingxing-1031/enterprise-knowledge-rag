import { Activity, Database, FileCheck2, Files, Gauge, RefreshCw, ShieldCheck } from "lucide-react";
import type { AdminAuditEvent, AdminOverview } from "../types";

const formatTime = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "暂无记录";

export function OverviewView({ overview, audit, onRefresh, loading }: { overview: AdminOverview | null; audit: AdminAuditEvent[]; onRefresh: () => void; loading: boolean }) {
  const cards = [
    { label: "文档版本", value: overview?.document_count ?? "—", note: `${overview?.active_count ?? 0} 个正在生效`, icon: Files, tone: "blue" },
    { label: "知识切片", value: overview?.chunk_count ?? "—", note: `${overview?.indexed_count ?? 0} 个版本已索引`, icon: Database, tone: "slate" },
    { label: "待审核导入", value: overview?.needs_review_count ?? "—", note: "清洗后等待管理员确认", icon: FileCheck2, tone: "amber" },
    { label: "停用版本", value: overview?.inactive_count ?? "—", note: "不参与用户检索", icon: ShieldCheck, tone: "red" },
  ];
  return <main className="page-view">
    <header className="page-heading"><div><span className="panel-kicker">控制面板 / OVERVIEW</span><h1>知识库运行总览</h1><p>查看当前语料规模、索引状态和最近的治理动作。</p></div><button className="secondary-button" type="button" onClick={onRefresh} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : undefined} />刷新数据</button></header>
    <section className="metric-grid">{cards.map(({ label, value, note, icon: Icon, tone }) => <article className={`stat-card tone-${tone}`} key={label}><div className="stat-icon"><Icon size={18} /></div><div><span>{label}</span><strong>{value}</strong><small>{note}</small></div></article>)}</section>
    <section className="overview-grid">
      <article className="panel-card health-card"><div className="panel-header"><div><span className="panel-kicker">服务健康</span><h2>索引与检索状态</h2></div><span className="health-badge"><Activity size={14} />运行正常</span></div><div className="health-row"><div className="health-ring"><Gauge size={25} /><strong>{overview?.document_count ? Math.round((overview.indexed_count / overview.document_count) * 100) : 0}%</strong></div><div><strong>版本索引覆盖率</strong><p>所有有效版本都应具备向量和 BM25 可用数据。</p><div className="progress-track"><span style={{ width: `${overview?.document_count ? Math.min(100, (overview.indexed_count / overview.document_count) * 100) : 0}%` }} /></div><small>最近索引：{formatTime(overview?.last_indexed_at ?? null)}</small></div></div></article>
      <article className="panel-card audit-card"><div className="panel-header"><div><span className="panel-kicker">治理记录</span><h2>最近操作</h2></div><span className="panel-count">{audit.length} 条</span></div>{audit.length === 0 ? <div className="empty-inline">还没有管理员操作记录</div> : <div className="audit-list">{audit.slice(0, 6).map((item) => <div className="audit-row" key={item.event_id}><span className={`audit-dot ${item.result === "success" ? "is-success" : "is-warning"}`} /><div><strong>{item.action}</strong><small>{item.actor_id} · {formatTime(item.created_at)}</small></div><code>{item.result}</code></div>)}</div>}</article>
    </section>
  </main>;
}
