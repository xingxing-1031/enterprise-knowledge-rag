import { describe, expect, it, vi } from "vitest";

import { streamChat } from "./api";


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
