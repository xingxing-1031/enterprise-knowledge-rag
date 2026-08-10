import { expect, test } from "@playwright/test";


const viewports = [
  { name: "mobile-360", width: 360, height: 800 },
  { name: "mobile-390", width: 390, height: 844 },
  { name: "desktop-1440", width: 1440, height: 900 },
];


for (const viewport of viewports) {
  test(`${viewport.name} keeps the workbench inside the viewport`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/session", (route) =>
      route.fulfill({
        json: {
          user_id: "demo-employee",
          role: "employee",
          departments: ["hr", "finance", "admin"],
          public_demo_mode: true,
        },
      }),
    );
    await page.route("**/documents", (route) => route.fulfill({ json: [] }));
    await page.route("**/evaluations/latest", (route) =>
      route.fulfill({ json: { status: "not_run" } }),
    );

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "知识问答" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    const navigation = page.getByRole("complementary", { name: "主导航" });
    if (viewport.width <= 760) {
      await expect(navigation).toHaveCSS("position", "fixed");
      await expect(page.getByText("公开演示身份")).toBeHidden();
    } else {
      await expect(navigation).toHaveCSS("position", "sticky");
      await expect(page.getByText("公开演示身份")).toBeVisible();
      await expect(page.getByRole("heading", { name: "引用台账" })).toBeVisible();
    }
  });

  test(`${viewport.name} keeps the administrator import workspace responsive`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/session", (route) => route.fulfill({ json: {
      user_id: "knowledge-admin-1",
      role: "knowledge_admin",
      departments: [],
      public_demo_mode: false,
    } }));
    await page.route("**/documents", (route) => route.fulfill({ json: [] }));
    await page.route("**/evaluations/latest", (route) =>
      route.fulfill({ json: { status: "not_run" } }),
    );
    await page.route("**/knowledge/imports", (route) => route.fulfill({ json: [] }));

    await page.goto("/");
    await page.getByRole("button", { name: "知识库" }).click();
    await expect(page.getByRole("heading", { name: "文档入库工作台" })).toBeVisible();
    await expect(page.getByText("选择 PDF、Word、Markdown 或 TXT")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
