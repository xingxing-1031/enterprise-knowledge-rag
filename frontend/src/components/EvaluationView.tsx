import { BarChart3, ClipboardCheck } from "lucide-react";

import type { EvaluationOverview } from "../types";


const METRIC_LABELS: Record<string, string> = {
  core_pass_rate: "核心通过率",
  recall_at_k: "证据召回率",
  reciprocal_rank: "首个证据排名",
  ndcg_at_k: "整体排序质量",
  access_leakage_rate: "权限泄漏率",
  version_accuracy: "版本准确率",
  citation_accuracy: "引用准确率",
  correct_refusal_rate: "正确拒答率",
  false_refusal_rate: "错误拒答率",
  execution_success_rate: "执行成功率",
};


function formatMetric(value: number | null) {
  return value === null ? "未评测" : `${(value * 100).toFixed(1)}%`;
}


export function EvaluationView({ evaluation }: { evaluation: EvaluationOverview }) {
  const entries = Object.entries(evaluation.metrics ?? {}).filter(
    ([key]) => key in METRIC_LABELS,
  );
  const hasReport = evaluation.status !== "not_run" && entries.length > 0;

  return (
    <main className="page-view">
      <header className="page-heading">
        <div>
          <span className="panel-kicker">受控实验</span>
          <h1>评测概览</h1>
          <p>只展示已保存报告中的真实结果，冻结集未运行时不生成准确率。</p>
        </div>
        <span className={hasReport ? "report-state is-ready" : "report-state"}>
          {hasReport ? "报告可用" : "尚未运行"}
        </span>
      </header>

      {!hasReport ? (
        <div className="page-empty evaluation-empty">
          <ClipboardCheck size={30} />
          <strong>真实评测尚未运行</strong>
          <span>先完成数据库、模型和 development smoke，再生成三方案对比报告。</span>
        </div>
      ) : (
        <>
          <section className="experiment-meta" aria-label="实验条件">
            <div>
              <span>检索方案</span>
              <strong>{evaluation.strategy ?? "未记录"}</strong>
            </div>
            <div>
              <span>语料快照</span>
              <code>{evaluation.corpus_snapshot ?? "未记录"}</code>
            </div>
          </section>
          <section className="metrics-grid" aria-label="评测指标">
            {entries.map(([key, value]) => (
              <article className="metric-item" key={key}>
                <BarChart3 size={18} aria-hidden="true" />
                <span>{METRIC_LABELS[key]}</span>
                <strong>{formatMetric(value)}</strong>
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
