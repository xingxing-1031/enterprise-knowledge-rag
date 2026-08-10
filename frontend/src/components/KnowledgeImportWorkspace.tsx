import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  RefreshCw,
  Upload,
} from "lucide-react";

import {
  approveKnowledgeImport,
  fetchKnowledgeImports,
  uploadKnowledgeDocument,
} from "../api";
import type { ImportMetadata, KnowledgeImport } from "../types";


const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  parsed: "已解析",
  needs_review: "待审核",
  approved: "已批准",
  indexed: "已入库",
  quarantined: "已隔离",
  failed: "处理失败",
};

const today = () => new Date().toISOString().slice(0, 10);

const INITIAL_METADATA: ImportMetadata = {
  document_id: "",
  title: "",
  document_type: "policy",
  department: "hr",
  visibility: "restricted",
  allowed_roles: ["employee"],
  version: "1.0",
  effective_from: today(),
  effective_to: null,
  supersedes_id: null,
  topic_tags: [],
};


interface KnowledgeImportWorkspaceProps {
  onIndexed: () => Promise<void>;
}


function toApiMetadata(metadata: ImportMetadata): ImportMetadata {
  const atStartOfDay = (value: string) =>
    new Date(`${value}T00:00:00+08:00`).toISOString();
  return {
    ...metadata,
    effective_from: atStartOfDay(metadata.effective_from),
    effective_to: metadata.effective_to
      ? atStartOfDay(metadata.effective_to)
      : null,
    topic_tags: metadata.topic_tags
      .flatMap((tag) => tag.split(/[，,]/))
      .map((tag) => tag.trim())
      .filter(Boolean),
  };
}


export function KnowledgeImportWorkspace({ onIndexed }: KnowledgeImportWorkspaceProps) {
  const [imports, setImports] = useState<KnowledgeImport[]>([]);
  const [selected, setSelected] = useState<KnowledgeImport | null>(null);
  const [metadata, setMetadata] = useState<ImportMetadata>(INITIAL_METADATA);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadImports = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchKnowledgeImports();
      setImports(result);
      setSelected((current) =>
        current
          ? result.find((item) => item.import_id === current.import_id) ?? result[0] ?? null
          : result[0] ?? null,
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "无法读取导入任务");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadImports();
  }, []);

  const updateMetadata = <K extends keyof ImportMetadata>(
    key: K,
    value: ImportMetadata[K],
  ) => setMetadata((current) => ({ ...current, [key]: value }));

  const submitImport = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) {
      setError("请选择要导入的企业文档");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const preview = await uploadKnowledgeDocument(file, toApiMetadata(metadata));
      setImports((current) => [preview, ...current]);
      setSelected(preview);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "文档上传失败");
    } finally {
      setSubmitting(false);
    }
  };

  const approveSelected = async () => {
    if (!selected?.metadata) return;
    setSubmitting(true);
    setError(null);
    try {
      const approved = await approveKnowledgeImport(
        selected.import_id,
        selected.metadata,
      );
      setSelected(approved);
      setImports((current) =>
        current.map((item) => item.import_id === approved.import_id ? approved : item),
      );
      await onIndexed();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "批准入库失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="import-workspace" aria-labelledby="import-heading">
      <div className="section-heading-row">
        <div>
          <span className="panel-kicker">管理员工具</span>
          <h2 id="import-heading">文档入库工作台</h2>
          <p>文件先解析和清洗，确认业务元数据后才会进入知识索引。</p>
        </div>
        <button className="icon-button" type="button" onClick={() => void loadImports()} aria-label="刷新导入任务">
          <RefreshCw size={16} />
        </button>
      </div>

      {error ? <div className="import-error" role="alert">{error}</div> : null}

      <form className="import-form" onSubmit={(event) => void submitImport(event)}>
        <label className="file-drop">
          <Upload size={20} />
          <span>{file?.name ?? "选择 PDF、Word、Markdown 或 TXT"}</span>
          <input
            type="file"
            accept=".pdf,.docx,.md,.txt"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <div className="metadata-grid">
          <label>文档编号<input required pattern="[a-z0-9][a-z0-9-]+" value={metadata.document_id} onChange={(event) => updateMetadata("document_id", event.target.value)} placeholder="hr-leave-policy" /></label>
          <label>文档标题<input required value={metadata.title} onChange={(event) => updateMetadata("title", event.target.value)} placeholder="员工请假管理制度" /></label>
          <label>文档类型<select value={metadata.document_type} onChange={(event) => updateMetadata("document_type", event.target.value as ImportMetadata["document_type"])}><option value="policy">制度</option><option value="process">流程</option><option value="handbook">手册</option><option value="faq">常见问题</option></select></label>
          <label>所属部门<select value={metadata.department} onChange={(event) => updateMetadata("department", event.target.value)}><option value="hr">人力资源</option><option value="finance">财务</option><option value="procurement">采购</option><option value="security">信息安全</option><option value="admin">行政</option></select></label>
          <label>可见范围<select value={metadata.visibility} onChange={(event) => updateMetadata("visibility", event.target.value as ImportMetadata["visibility"])}><option value="restricted">指定角色</option><option value="department">本部门</option><option value="public">全员可见</option></select></label>
          <label>版本号<input required value={metadata.version} onChange={(event) => updateMetadata("version", event.target.value)} placeholder="1.0" /></label>
          <label>生效日期<input required type="date" value={metadata.effective_from.slice(0, 10)} onChange={(event) => updateMetadata("effective_from", event.target.value)} /></label>
          <label>主题标签<input value={metadata.topic_tags.join("，")} onChange={(event) => updateMetadata("topic_tags", [event.target.value])} placeholder="请假，病假，审批" /></label>
        </div>
        <button className="primary-command" type="submit" disabled={submitting}>
          <Upload size={16} />{submitting ? "正在处理" : "上传并生成预览"}
        </button>
      </form>

      <div className="import-review-layout">
        <div className="import-task-list" aria-label="导入任务">
          {loading ? <div className="import-list-state">正在读取导入任务</div> : null}
          {!loading && imports.length === 0 ? <div className="import-list-state">还没有导入任务</div> : null}
          {imports.map((item) => (
            <button key={item.import_id} type="button" className={selected?.import_id === item.import_id ? "import-task is-selected" : "import-task"} onClick={() => setSelected(item)}>
              <FileText size={16} />
              <span><strong>{item.metadata?.title ?? item.original_filename}</strong><small>{item.original_filename}</small></span>
              <em className={`import-status status-${item.status}`}>{STATUS_LABELS[item.status]}</em>
            </button>
          ))}
        </div>

        <div className="import-preview" aria-live="polite">
          {selected ? (
            <>
              <div className="preview-heading"><div><span className="panel-kicker">清洗结果</span><h3>{selected.metadata?.title ?? selected.original_filename}</h3></div><span className={`import-status status-${selected.status}`}>{STATUS_LABELS[selected.status]}</span></div>
              <dl className="cleaning-stats"><div><dt>字符</dt><dd>{selected.cleaning_report?.characters_after ?? 0}</dd></div><div><dt>段落</dt><dd>{selected.cleaning_report?.blocks_after ?? 0}</dd></div><div><dt>表格</dt><dd>{selected.cleaning_report?.table_count ?? 0}</dd></div><div><dt>页数</dt><dd>{selected.page_count ?? "-"}</dd></div></dl>
              {selected.cleaning_report?.issues.length ? <ul className="cleaning-issues">{selected.cleaning_report.issues.map((issue) => <li key={`${issue.code}-${issue.message}`} className={`issue-${issue.severity}`}><AlertTriangle size={15} /><span>{issue.message}<code>{issue.code}</code></span></li>)}</ul> : <div className="cleaning-ok"><CheckCircle2 size={16} />未发现需要处理的清洗问题</div>}
              <pre className="normalized-preview">{selected.normalized_preview || "没有可预览的正文"}</pre>
              <button className="primary-command approve-command" type="button" disabled={!selected.can_approve || submitting} onClick={() => void approveSelected()}><CheckCircle2 size={16} />{selected.status === "indexed" ? "已建立索引" : "确认并建立索引"}</button>
            </>
          ) : <div className="import-preview-empty"><FileText size={24} /><span>选择一个导入任务查看解析与清洗结果</span></div>}
        </div>
      </div>
    </section>
  );
}
