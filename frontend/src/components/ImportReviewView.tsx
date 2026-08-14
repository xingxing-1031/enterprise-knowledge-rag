import { KnowledgeImportWorkspace } from "./KnowledgeImportWorkspace";

export function ImportReviewView({ onIndexed }: { onIndexed: () => Promise<void> }) {
  return <main className="page-view"><header className="page-heading"><div><span className="panel-kicker">知识治理 / INTAKE</span><h1>导入审核</h1><p>文件先解析、清洗和预览，管理员确认元数据后才会进入索引。</p></div></header><KnowledgeImportWorkspace onIndexed={onIndexed} /></main>;
}
