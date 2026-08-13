import {
  ArrowUp,
  BookOpenCheck,
  Bot,
  CircleAlert,
  Database,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";
import type { FormEvent } from "react";

import type { ChatMessage, ProgressEvent, RetrievalEvidence } from "../types";


const EXAMPLE_QUESTIONS = [
  "你好，介绍一下你能做什么",
  "出差结束后最晚多久提交报销？",
  "分析最近30天各渠道销售额",
  "分析退款率变化，并判断是否触发售后制度",
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
  onOpenEvidence: (index: number) => void;
}


const STATUS_LABELS = {
  success: "依据已核验",
  degraded: "已降级返回",
  refused: "已按规则拒答",
  failed: "请求失败",
};


const MODE_LABELS = {
  general: "通用对话",
  knowledge: "企业知识",
  data: "经营数据",
  collaboration: "多 Agent 协作",
};


const AGENT_LABELS: Record<string, string> = {
  general_agent: "通用对话 Agent",
  knowledge_agent: "知识 Agent",
  data_agent: "数据 Agent",
  synthesis_agent: "综合 Agent",
  review_agent: "审核 Agent",
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
          <h1>企业运营智能助手</h1>
        </div>
        <button className="text-button" type="button" onClick={onClear}>
          <RotateCcw size={16} />
          清空会话
        </button>
      </header>

      <section className="conversation" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <Bot size={30} strokeWidth={1.5} />
            <h2>开始一次对话或企业任务</h2>
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
                {message.result ? <div className="result-labels">
                  <span className={`result-state result-${message.result.status}`}>
                    {STATUS_LABELS[message.result.status]}
                  </span>
                  {message.result.agent_mode ? (
                    <span className="agent-mode">{MODE_LABELS[message.result.agent_mode]}</span>
                  ) : null}
                </div> : null}
                <p>{message.content}</p>
                {message.result?.task_plan && message.result.task_plan.length > 0 ? (
                  <div className="agent-execution" aria-label="Agent 执行概览">
                    <div className="agent-roster">
                      {(message.result.agents ?? []).map((agent) => (
                        <span key={agent}><Bot size={13} />{AGENT_LABELS[agent] ?? agent}</span>
                      ))}
                    </div>
                    <ol>
                      {message.result.task_plan.map((step, index) => (
                        <li key={`${step.agent}-${index}`} data-status={step.status}>
                          <span>{index + 1}</span>
                          <div><strong>{AGENT_LABELS[step.agent] ?? step.agent}</strong><small>{step.task}</small></div>
                        </li>
                      ))}
                    </ol>
                    {message.result.data_result?.evidence_ids.length ? (
                      <div className="data-evidence"><Database size={14} />数据证据 {message.result.data_result.evidence_ids.length} 项</div>
                    ) : null}
                    {message.result.review ? (
                      <div className={`review-state ${message.result.review.passed ? "is-passed" : "is-limited"}`}>
                        {message.result.review.passed ? "审核通过" : "审核发现证据缺口"}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {message.result?.degradation_reason ? (
                  <p className="degradation-note">{message.result.degradation_reason}</p>
                ) : null}
                {message.result && message.result.citations.length > 0 ? (
                  <div className="citation-list">
                    {message.result.citations.map((citation, index) => (
                      <button
                        className="citation-link"
                        type="button"
                        key={citation.evidence_id}
                        onClick={() => onOpenEvidence(index)}
                      >
                        <BookOpenCheck size={15} />
                        [{index + 1}] {citation.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </article>
          ))
        )}

        {loading ? (
          <div className="progress-ledger">
            <div className="progress-title">
              <LoaderCircle className="spin" size={17} />
              <strong>企业运营 Agent 正在执行</strong>
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
        <label htmlFor="question-input">输入对话或企业任务</label>
        <div className="composer-row">
          <textarea
            id="question-input"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder="例如：分析退款率变化，并判断是否触发售后制度"
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
          <span>企业事实使用授权证据，经营数据通过受治理工具查询</span>
          <button className="mobile-evidence-button" type="button" onClick={() => onOpenEvidence(0)} disabled={evidence.length === 0}>
            引用 {evidence.length}
          </button>
        </div>
      </form>
    </main>
  );
}
