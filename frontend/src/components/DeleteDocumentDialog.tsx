import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import type { ManagedDocument } from "../types";

export function DeleteDocumentDialog({ document, onClose, onConfirm, busy }: { document: ManagedDocument; onClose: () => void; onConfirm: (confirmation: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");
  const valid = value === document.title;
  return <div className="modal-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title"><button className="modal-close" type="button" onClick={onClose} aria-label="关闭确认窗口"><X size={18} /></button><div className="danger-symbol"><AlertTriangle size={22} /></div><span className="panel-kicker danger-kicker">不可逆操作</span><h2 id="delete-title">永久删除文档版本</h2><p>这会级联删除源文件、知识切片和向量。审计只保留不可逆的引用摘要。</p><div className="delete-target"><strong>{document.title}</strong><span>{document.document_id} · 版本 {document.version}</span></div><label htmlFor="delete-confirmation">输入文档标题确认</label><input id="delete-confirmation" value={value} onChange={(event) => setValue(event.target.value)} autoFocus /><div className="dialog-actions"><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="danger-button" type="button" disabled={!valid || busy} onClick={() => onConfirm(value)}>{busy ? "删除中" : "确认永久删除"}</button></div></section></div>;
}
