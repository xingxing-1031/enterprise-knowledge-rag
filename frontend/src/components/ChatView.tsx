import {
  ArrowUp,
  BookOpenCheck,
  CircleAlert,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import type { FormEvent } from "react";

import type { ChatMessage, ProgressEvent, RetrievalEvidence } from "../types";


const EXAMPLE_QUESTIONS = [
  "出差结束后最晚多久提交报销？",
  "按2025年8月的制度，报销期限是多少？",
  "普通员工能查询全员付款审批额度吗？",
  "公司的育儿假每年有多少天？",
];


interface ChatViewProps {
  messages: ChatMessage[];
  question: string;
  onQuestionChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onExample: (question: string) => void;
  onClear: () => void;
  progress: ProgressEvent[];
  loading: boolean;
  error: string | null;
  evidence: RetrievalEvidence[];
  onOpenEvidence: () => void;
}


const STATUS_LABELS = {
  success: "依据已核验",
  degraded: "已降级返回",
  refused: "已按规则拒答",
  failed: "请求失败",
};


export function ChatView({
  messages,
  question,
  onQuestionChange,
  onSubmit,
  onExample,
  onClear,
  progress,
  loading,
  error,
  evidence,
  onOpenEvidence,
}: ChatViewProps) {
  return (
    <main className="chat-view">
      <header className="chat-heading">
        <div>
          <span className="panel-kicker">企业制度问答</span>
          <h1>知识问答</h1>
        </div>
        <button className="text-button" type="button" onClick={onClear}>
          <RotateCcw size={16} />
          清空会话
        </button>
      </header>

      <section className="conversation" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <BookOpenCheck size={30} strokeWidth={1.5} />
            <h2>开始一次制度查询</h2>
            <div className="example-list">
              {EXAMPLE_QUESTIONS.map((item) => (
                <button key={item} type="button" onClick={() => onExample(item)}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <span className="message-role">
                {message.role === "user" ? "你" : "制度智查"}
              </span>
              <div className="message-body">
                {message.result ? (
                  <span className={`result-state result-${message.result.status}`}>
                    {STATUS_LABELS[message.result.status]}
                  </span>
                ) : null}
                <p>{message.content}</p>
                {message.result?.degradation_reason ? (
                  <p className="degradation-note">{message.result.degradation_reason}</p>
                ) : null}
                {message.result && message.result.citations.length > 0 ? (
                  <button className="citation-link" type="button" onClick={onOpenEvidence}>
                    <BookOpenCheck size={15} />
                    查看 {message.result.citations.length} 条引用
                  </button>
                ) : null}
              </div>
            </article>
          ))
        )}

        {loading ? (
          <div className="progress-ledger">
            <div className="progress-title">
              <LoaderCircle className="spin" size={17} />
              <strong>正在核对制度依据</strong>
            </div>
            <ol>
              {progress.length === 0 ? (
                <li><span />正在接收请求</li>
              ) : (
                progress.map((item, index) => (
                  <li key={`${item.stage}-${index}`}><span />{item.label}</li>
                ))
              )}
            </ol>
          </div>
        ) : null}

        {error ? (
          <div className="inline-error" role="alert">
            <CircleAlert size={18} />
            <span>{error}</span>
          </div>
        ) : null}
      </section>

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="question-input">输入企业制度或流程问题</label>
        <div className="composer-row">
          <textarea
            id="question-input"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder="例如：出差结束后最晚多久提交报销？"
            maxLength={2000}
            rows={2}
            disabled={loading}
          />
          <button
            className="send-button"
            type="submit"
            aria-label="发送问题"
            disabled={loading || question.trim().length === 0}
          >
            <ArrowUp size={20} />
          </button>
        </div>
        <div className="composer-footer">
          <span>答案仅使用已授权且生效的制度依据</span>
          <button className="mobile-evidence-button" type="button" onClick={onOpenEvidence} disabled={evidence.length === 0}>
            引用 {evidence.length}
          </button>
        </div>
      </form>
    </main>
  );
}
