import { FileText, Layers3, X } from "lucide-react";

import type { RetrievalEvidence } from "../types";


interface EvidencePanelProps {
  evidence: RetrievalEvidence[];
  mobileOpen: boolean;
  onClose: () => void;
}


function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}


export function EvidencePanel({ evidence, mobileOpen, onClose }: EvidencePanelProps) {
  return (
    <aside className={mobileOpen ? "evidence-panel is-open" : "evidence-panel"}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">可信依据</span>
          <h2>引用台账</h2>
        </div>
        <button className="icon-button mobile-only" type="button" onClick={onClose} aria-label="关闭引用">
          <X size={18} />
        </button>
      </div>

      {evidence.length === 0 ? (
        <div className="evidence-empty">
          <Layers3 size={24} strokeWidth={1.5} />
          <strong>暂无引用</strong>
          <span>完成制度查询后，这里会列出文档版本与原文。</span>
        </div>
      ) : (
        <ol className="evidence-list">
          {evidence.map((item, index) => (
            <li key={item.evidence_id} className="evidence-item">
              <span className="evidence-index">{String(index + 1).padStart(2, "0")}</span>
              <div className="evidence-content">
                <div className="evidence-title-row">
                  <FileText size={17} aria-hidden="true" />
                  <h3>{item.title}</h3>
                </div>
                <div className="evidence-meta">
                  <span>版本 {item.version}</span>
                  <span>{formatDate(item.effective_from)} 生效</span>
                </div>
                <p className="section-path">{item.section_path.join(" / ")}</p>
                <blockquote>{item.quote}</blockquote>
                <div className="technical-meta">
                  <code>{item.chunk_id}</code>
                  <span>{item.retrieval_channels.join(" + ")}</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
