import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./api";


vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    fetchSession: vi.fn(),
    fetchDocuments: vi.fn(),
    fetchLatestEvaluation: vi.fn(),
    streamChat: vi.fn(),
  };
});


describe("enterprise knowledge workbench", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchSession).mockResolvedValue({
      user_id: "demo-employee",
      role: "employee",
      departments: ["finance"],
      public_demo_mode: true,
    });
    vi.mocked(api.fetchDocuments).mockResolvedValue([]);
    vi.mocked(api.fetchLatestEvaluation).mockResolvedValue({ status: "not_run" });
    vi.mocked(api.streamChat).mockImplementation(async (_request, onProgress) => {
      onProgress({ stage: "retrieve", label: "检索企业知识", status: "ready" });
      return {
        status: "success",
        answer: "出差结束后十五个自然日内提交报销申请。",
        citations: [{ evidence_id: "ev:expense", label: "报销期限" }],
        evidence: [
          {
            evidence_id: "ev:expense",
            chunk_id: "expense:deadline",
            document_id: "finance-expense-policy",
            title: "差旅与费用报销管理制度",
            section_path: ["差旅与费用报销管理制度", "报销期限"],
            version: "2.0",
            effective_from: "2026-06-01T00:00:00+08:00",
            quote: "出差结束后 15 个自然日内提交报销申请。",
            retrieval_channels: ["bm25", "vector"],
            retrieval_rank: 1,
            reranker_score: 0.92,
          },
        ],
      };
    });
  });

  it("submits a question and displays grounded answer and evidence", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("输入企业制度或流程问题"), "报销多久内提交？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByText(/十五个自然日内提交/)).toBeInTheDocument();
    expect(screen.getByText("差旅与费用报销管理制度")).toBeInTheDocument();
    expect(screen.getByText("版本 2.0")).toBeInTheDocument();
  });

  it("keeps trusted session data when one metadata request fails", async () => {
    vi.mocked(api.fetchDocuments).mockRejectedValueOnce(new Error("database down"));

    render(<App />);

    expect(await screen.findByText("普通员工")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("部分服务状态暂时不可用");
  });
});
