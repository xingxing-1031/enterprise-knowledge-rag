import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api";

vi.mock("./api", () => ({
  fetchSession: vi.fn(), fetchAdminOverview: vi.fn(), fetchDocuments: vi.fn(),
  fetchLatestEvaluation: vi.fn(), fetchAdminAudit: vi.fn(), fetchKnowledgeImports: vi.fn(),
  uploadKnowledgeDocument: vi.fn(), approveKnowledgeImport: vi.fn(), login: vi.fn(), logout: vi.fn(),
  deactivateDocument: vi.fn(), restoreDocument: vi.fn(), reindexDocument: vi.fn(), deleteDocument: vi.fn(), debugRetrieval: vi.fn(),
}));

const document = {
  document_id: "hr-leave-policy", version: "2.0", title: "员工请假制度",
  document_type: "policy" as const, department: "hr", visibility: "restricted" as const,
  status: "active" as const, effective_from: "2026-08-10T00:00:00Z", effective_to: null,
  topic_tags: ["请假"], source_filename: "leave-policy.md", chunk_count: 12, indexed: true,
  indexed_at: "2026-08-10T00:00:00Z",
};

describe("knowledge administrator console", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchSession).mockResolvedValue({ user_id: "demo-knowledge-admin", role: "knowledge_admin", departments: ["hr"], public_demo_mode: true });
    vi.mocked(api.fetchAdminOverview).mockResolvedValue({ document_count: 1, active_count: 1, inactive_count: 0, needs_review_count: 0, chunk_count: 12, indexed_count: 1, last_indexed_at: null, recent_audit_count: 0 });
    vi.mocked(api.fetchDocuments).mockResolvedValue([document]);
    vi.mocked(api.fetchLatestEvaluation).mockResolvedValue({ status: "not_run" });
    vi.mocked(api.fetchAdminAudit).mockResolvedValue([]);
    vi.mocked(api.fetchKnowledgeImports).mockResolvedValue([]);
    vi.mocked(api.logout).mockResolvedValue();
    vi.mocked(api.login).mockResolvedValue({ user_id: "demo-knowledge-admin", role: "knowledge_admin", departments: [], public_demo_mode: true });
  });

  it("shows only administrator navigation", async () => {
    render(<App />);
    expect(await screen.findByRole("button", { name: "总览" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "检索实验室" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "智能助手" })).not.toBeInTheDocument();
  });

  it("requires exact title before permanent deletion", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "文档库" }));
    await user.click(screen.getByText("员工请假制度"));
    await user.click(screen.getByRole("button", { name: "永久删除" }));
    const confirm = screen.getByRole("button", { name: "确认永久删除" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("输入文档标题确认"), "员工请假制度");
    expect(confirm).toBeEnabled();
  });

  it("shows the administrator login when session is unauthorized", async () => {
    vi.mocked(api.fetchSession).mockRejectedValueOnce(Object.assign(new Error("请先登录"), { status: 401 }));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "管理员登录" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("knowledge-admin-demo")).toBeInTheDocument();
  });
});
