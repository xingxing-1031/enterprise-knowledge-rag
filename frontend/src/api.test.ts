import { describe, expect, it, vi } from "vitest";

import { streamChat, uploadKnowledgeDocument } from "./api";


describe("streamChat", () => {
  it("parses Chinese progress events and the final result", async () => {
    const body = [
      'event: progress\ndata: {"stage":"retrieve","label":"检索企业知识","status":"ready"}\n\n',
      'event: result\ndata: {"status":"success","answer":"十五个自然日内提交。","citations":[],"evidence":[]}\n\n',
    ].join("");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      ),
    );
    const progress: string[] = [];

    const result = await streamChat(
      { question: "报销多久内提交？", session_id: "test-session" },
      (event) => progress.push(event.label),
    );

    expect(progress).toEqual(["检索企业知识"]);
    expect(result.status).toBe("success");
    expect(result.answer).toContain("十五个自然日");
  });
});


describe("knowledge imports", () => {
  it("uploads the file and strict metadata as multipart form data", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ import_id: "i1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["制度正文"], "policy.txt", { type: "text/plain" });

    await uploadKnowledgeDocument(file, {
      document_id: "hr-leave-policy",
      title: "员工请假制度",
      document_type: "policy",
      department: "hr",
      visibility: "restricted",
      allowed_roles: ["employee"],
      version: "2.0",
      effective_from: "2026-08-10T00:00:00.000Z",
      topic_tags: ["请假"],
    });

    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const init = calls[0]?.[1];
    const body = init?.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(String(body.get("metadata"))).toContain("hr-leave-policy");
  });
});
