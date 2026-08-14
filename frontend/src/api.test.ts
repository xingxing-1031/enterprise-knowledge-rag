import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAdminOverview, login } from "./api";

describe("admin api", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends administrator credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user_id: "demo-knowledge-admin", role: "knowledge_admin", departments: [], public_demo_mode: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await login("knowledge-admin-demo", "KnowledgeAdmin2026!");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/auth/login"), expect.objectContaining({ method: "POST" }));
  });

  it("loads overview from the protected endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ document_count: 0 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await fetchAdminOverview();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/admin/overview"), expect.objectContaining({ credentials: "same-origin" }));
  });
});
