import { expect, test, type Page } from "@playwright/test";

const viewports = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "desktop-1280", width: 1280, height: 720 },
];

const document = {
  document_id: "hr-leave-policy", version: "2.0", title: "员工请假制度",
  document_type: "policy", department: "hr", visibility: "restricted", status: "active",
  effective_from: "2026-08-10T00:00:00Z", effective_to: null, topic_tags: ["请假"],
  source_filename: "leave-policy.md", chunk_count: 12, indexed: true,
  indexed_at: "2026-08-10T00:00:00Z",
};

async function mockConsole(page: Page) {
  await page.route("**/session", (route) => route.fulfill({ json: { user_id: "demo-knowledge-admin", role: "knowledge_admin", departments: ["hr"], public_demo_mode: true } }));
  await page.route("**/admin/overview", (route) => route.fulfill({ json: { document_count: 1, active_count: 1, inactive_count: 0, needs_review_count: 0, chunk_count: 12, indexed_count: 1, last_indexed_at: "2026-08-10T00:00:00Z", recent_audit_count: 0 } }));
  await page.route("**/documents", (route) => route.fulfill({ json: [document] }));
  await page.route("**/evaluations/latest", (route) => route.fulfill({ json: { status: "not_run" } }));
  await page.route("**/admin/audit**", (route) => route.fulfill({ json: [] }));
  await page.route("**/knowledge/imports", (route) => route.fulfill({ json: [] }));
  await page.route("**/admin/retrieval/debug", (route) => route.fulfill({ json: {
    query: "付款审批", strategy: "hybrid_rrf_reranker", simulated_role: "employee",
    simulated_departments: ["finance"], status: "ready", total_duration_ms: 48,
    stages: ["authorization", "bm25", "vector", "rrf", "rerank", "evidence"].map((name) => ({ name, candidate_count: 2, excluded_count: 0, duration_ms: 8, candidates: [] })),
  } }));
}

for (const viewport of viewports) {
  test(`${viewport.name} keeps all administrator pages inside the viewport`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockConsole(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "知识库运行总览" })).toBeVisible();
    for (const name of ["总览", "文档库", "导入审核", "检索实验室", "评测中心"]) {
      await expect(page.getByRole("button", { name })).toBeVisible();
    }
    for (const name of ["文档库", "导入审核", "检索实验室", "评测中心"]) {
      await page.getByRole("button", { name }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    }
  });

  test(`${viewport.name} supports document details and guarded deletion`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: "文档库" }).click();
    await page.getByText("员工请假制度").first().click();
    await page.getByRole("button", { name: "永久删除" }).click();
    await expect(page.getByRole("dialog", { name: "永久删除文档版本" })).toBeVisible();
    await expect(page.getByRole("button", { name: "确认永久删除" })).toBeDisabled();
  });

  test(`${viewport.name} renders the retrieval pipeline`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockConsole(page);
    await page.goto("/");
    await page.getByRole("button", { name: "检索实验室" }).click();
    await page.getByRole("button", { name: "运行检索" }).click();
    await expect(page.getByText("BM25 召回").first()).toBeVisible();
    await expect(page.getByText("RRF 融合").first()).toBeVisible();
    await expect(page.getByText("Rerank 重排").first()).toBeVisible();
  });
}
