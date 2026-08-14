import { BarChart3, CheckCircle2, ClipboardCheck, ShieldAlert, Target } from "lucide-react";
import type { EvaluationOverview } from "../types";

const LABELS: Record<string, string> = { core_pass_rate: "核心通过率", recall_at_k: "证据召回率", reciprocal_rank: "首证据排名", ndcg_at_k: "整体排序质量", access_leakage_rate: "权限泄漏率", version_accuracy: "版本准确率", citation_accuracy: "引用准确率", correct_refusal_rate: "正确拒答率", false_refusal_rate: "错误拒答率", execution_success_rate: "执行成功率" };
const format = (value: number | null) => value === null ? "未评测" : `${(value * 100).toFixed(1)}%`;

export function EvaluationView({ evaluation }: { evaluation: EvaluationOverview }) {
  const entries = Object.entries(evaluation.metrics ?? {}).filter(([key]) => key in LABELS);
  const ready = evaluation.status !== "not_run" && entries.length > 0;
  return <main className="page-view"><header className="page-heading"><div><span className="panel-kicker">质量保障 / EVALUATION</span><h1>评测中心</h1><p>只展示冻结集真实运行结果，不用估算数字填充报告。</p></div><span className={ready ? "report-state is-ready" : "report-state"}>{ready ? <><CheckCircle2 size={14} />报告可用</> : "尚未运行"}</span></header>{ready ? <><section className="evaluation-summary panel-card"><div><span>当前检索策略</span><strong>{evaluation.strategy ?? "未记录"}</strong></div><div><span>语料快照</span><code>{evaluation.corpus_snapshot ?? "未记录"}</code></div><div><span>指标数量</span><strong>{entries.length}</strong></div></section><section className="metric-grid evaluation-metrics">{entries.map(([key, value], index) => <article className="stat-card" key={key}><div className="stat-icon">{index % 3 === 0 ? <Target size={18} /> : index % 3 === 1 ? <BarChart3 size={18} /> : <ShieldAlert size={18} />}</div><div><span>{LABELS[key]}</span><strong>{format(value)}</strong><small>{key}</small></div></article>)}</section></> : <div className="page-empty"><ClipboardCheck size={30} /><strong>真实评测尚未运行</strong><span>完成数据库、模型和 development smoke 后再生成三方案对比报告。</span></div>}</main>;
}
