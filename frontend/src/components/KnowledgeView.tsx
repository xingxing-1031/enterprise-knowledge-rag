import { BookOpenText, LockKeyhole } from "lucide-react";

import type { DocumentOverview } from "../types";


const STATUS_LABELS: Record<string, string> = {
  active: "生效中",
  expired: "已过期",
  revoked: "已废止",
  draft: "草案",
};

const DEPARTMENT_LABELS: Record<string, string> = {
  hr: "人力资源",
  finance: "财务",
  procurement: "采购",
  security: "信息安全",
  admin: "行政",
};


interface KnowledgeViewProps {
  documents: DocumentOverview[];
  loading: boolean;
}


export function KnowledgeView({ documents, loading }: KnowledgeViewProps) {
  return (
    <main className="page-view">
      <header className="page-heading">
        <div>
          <span className="panel-kicker">可见范围</span>
          <h1>知识库</h1>
          <p>仅展示当前服务器身份有权访问的文档元数据。</p>
        </div>
        <div className="page-count">
          <strong>{documents.length}</strong>
          <span>可见版本</span>
        </div>
      </header>

      {loading ? (
        <div className="table-loading" aria-label="正在加载知识库">
          <span />
          <span />
          <span />
        </div>
      ) : documents.length === 0 ? (
        <div className="page-empty">
          <BookOpenText size={28} />
          <strong>知识库尚未准备完成</strong>
          <span>管理员完成索引后，可见文档会显示在这里。</span>
        </div>
      ) : (
        <div className="document-table-wrap">
          <table className="document-table">
            <thead>
              <tr>
                <th>文档</th>
                <th>部门</th>
                <th>版本</th>
                <th>状态</th>
                <th>可见性</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={`${document.document_id}@${document.version}`}>
                  <td>
                    <strong>{document.title}</strong>
                    <code>{document.document_id}</code>
                  </td>
                  <td>{DEPARTMENT_LABELS[document.department] ?? "其他部门"}</td>
                  <td>{document.version}</td>
                  <td>
                    <span className={`status-chip status-${document.status}`}>
                      {STATUS_LABELS[document.status] ?? "未知状态"}
                    </span>
                  </td>
                  <td>
                    <span className="visibility-label">
                      {document.visibility !== "public" ? <LockKeyhole size={14} /> : null}
                      {document.visibility === "public" ? "公开" : "受限"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
