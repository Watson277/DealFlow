import { expect, test, type Page } from "@playwright/test";

const rfpId = "11111111-1111-4111-8111-111111111111";
const customerId = "22222222-2222-4222-8222-222222222222";
const proposalId = "33333333-3333-4333-8333-333333333333";

async function mockWorkspace(page: Page, initial = "REVIEW_PENDING", empty = false) {
  const state = { status: initial, lastUpload: "", customerError: false,
    markdown: "# 验证方案\n\n已生成的方案内容",
    rfpDeleted: false, customerDeleted: false, knowledgeVisible: false,
    knowledgeDeleteError: false, deleteCalls: [] as string[] };
  const customer = { id: customerId, name: "验证客户", code: "CHECK", industry: null };
  const record = () => ({ id: rfpId, customer_id: customerId, title: "验证 RFP",
    reference_number: null, status: state.status, current_stage: "human_review",
    created_at: "2026-08-31T08:00:00", updated_at: "2026-08-31T08:00:00" });
  await page.route(/\/(rfps|customers|knowledge|proposals)([/?]|$)/, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (json: unknown, status = 200) => route.fulfill({ json, status });
    if (request.method() === "DELETE") {
      state.deleteCalls.push(path);
      if (path === `/rfps/${rfpId}`) state.rfpDeleted = true;
      else if (path === `/customers/${customerId}`) {
        if (!state.rfpDeleted) return reply({ detail: "该客户仍有关联任务，请先删除其全部 RFP 任务" }, 409);
        state.customerDeleted = true;
      } else if (path === "/knowledge/44444444-4444-4444-8444-444444444444") {
        if (state.knowledgeDeleteError) return reply({ detail: "知识库索引删除失败，请稍后重试；文档尚未删除" }, 503);
        state.knowledgeVisible = false;
      } else throw new Error(`Unexpected deletion: ${path}`);
      return route.fulfill({ status: 204 });
    }
    if (request.method() === "POST") {
      if (path.endsWith("/retry")) { state.status = "QUEUED"; return reply({}, 202); }
      if (path.endsWith("/reviews")) {
        expect(request.postDataJSON().decision).toBe("APPROVED");
        state.status = "APPROVED";
        return reply({});
      }
      if (path === "/rfps") {
        state.lastUpload = request.postData() || "";
        return reply({}, 202);
      }
      if (path === "/customers") return reply({ detail: [
        { loc: ["body", "name"], msg: "名称不符合要求" },
      ] }, 422);
      return reply({});
    }
    if (path === "/customers") return reply({ items: empty || state.customerDeleted ? [] : [customer], total: empty || state.customerDeleted ? 0 : 1 });
    if (path === "/rfps") return reply({ items: empty || state.rfpDeleted ? [] : [record()], total: empty || state.rfpDeleted ? 0 : 1 });
    if (path === "/knowledge") return reply({ items: state.knowledgeVisible ? [{
      id: "44444444-4444-4444-8444-444444444444", status: "READY", original_filename: "企业资料.pdf",
      extra_data: { title: "验证知识库" }, size_bytes: 1024, knowledge_category: "security",
      created_at: "2026-08-31T08:00:00", document_version: "1",
    }] : [], total: state.knowledgeVisible ? 1 : 0 });
    if (path.endsWith("/status")) return reply({
      rfp_id: rfpId, status: state.status, current_stage: "human_review", stage_label: "等待审核",
      progress_percent: state.status === "APPROVED" ? 100 : 80,
      stage_started_at: "2026-08-31T08:00:00", elapsed_seconds: 25, attempt: 0,
      error_message: state.status === "FAILED" ? "LLM request timed out" : null,
    });
    if (path.endsWith("/proposals")) return reply({ items: [
      { id: proposalId, rfp_id: rfpId, version: 1, status: state.status, title: "验证方案" },
    ], total: 1 });
    if (path.endsWith("/markdown")) return route.fulfill({ body: state.markdown, contentType: "text/markdown" });
    return reply({ items: [], total: 0 });
  });
  return state;
}

test("empty workspace has no example cards or prefilled values", async ({ page }) => {
  await mockWorkspace(page, "QUEUED", true);
  await page.goto("/");
  await expect(page.getByText("还没有 RFP", { exact: true })).toBeVisible();
  await expect(page.getByText(/Example Value|示例/)).toHaveCount(0);
  await page.getByRole("button", { name: "新建 RFP", exact: true }).click();
  await expect(page.getByLabel("RFP 标题", { exact: true })).toHaveValue("");
  await expect(page.getByText("请先到客户管理创建客户。")).toBeVisible();
});

test("422 errors do not crash the form or discard input", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await page.getByRole("button", { name: "客户管理", exact: true }).click();
  await page.getByRole("button", { name: "新增客户", exact: true }).click();
  await page.getByLabel("客户名称").fill("验证客户");
  await page.getByLabel("客户编码").fill("CHECK");
  await page.getByRole("button", { name: "确认提交" }).click();
  await expect(page.getByText("name：名称不符合要求")).toBeVisible();
  await expect(page.getByLabel("客户名称")).toHaveValue("验证客户");
});

test("upload omits blank optional fields", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "验证 RFP", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "新建 RFP", exact: true }).click();
  await page.locator('select[name="customer_id"]').selectOption(customerId);
  await page.getByLabel("RFP 标题", { exact: true }).fill("上传检查");
  await page.locator('input[type="file"]').setInputFiles({ name: "rfp.pdf", mimeType: "application/pdf", buffer: Buffer.from("upload-test") });
  await page.getByRole("button", { name: "确认提交" }).click();
  await expect(page.getByText("RFP 已进入处理队列")).toBeVisible();
  expect(state.lastUpload).toContain('name="title"');
  expect(state.lastUpload).not.toContain('name="due_at"');
  expect(state.lastUpload).not.toContain('name="reference_number"');
});

test("retry replaces failure state in the open detail", async ({ page }) => {
  await mockWorkspace(page, "FAILED");
  await page.goto("/");
  await page.getByRole("button", { name: "验证 RFP", exact: true }).click();
  await page.getByRole("button", { name: "重试失败阶段" }).click();
  await expect(page.getByText("已重新提交失败阶段")).toBeVisible();
  await expect(page.locator(".progress-card .status")).toHaveText("等待处理");
  await expect(page.getByRole("button", { name: "重试失败阶段" })).toHaveCount(0);
});

test("approval refreshes proposal and polling preserves review input focus", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  await page.getByRole("button", { name: "验证 RFP", exact: true }).click();
  await page.getByRole("button", { name: /方案与审核/ }).click();
  const input = page.getByRole("textbox", { name: "修改意见" });
  await input.fill("保留审核意见");
  await input.focus();
  await page.waitForTimeout(5500);
  await expect(input).toBeFocused();
  await page.getByRole("button", { name: "通过审核", exact: true }).click();
  await expect(page.getByText("方案已通过审核")).toBeVisible();
  await expect(page.locator(".progress-card .status")).toHaveText("已通过");
  await expect(page.getByRole("button", { name: "通过审核", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "下载 Markdown" })).toHaveAttribute("download", "proposal-v1.md");
});

test("mobile layout fits viewport", async ({ page }) => {
  await mockWorkspace(page, "QUEUED", true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("还没有 RFP", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("task deletion requires confirmation and closes the deleted detail", async ({ page }) => {
  const state = await mockWorkspace(page, "QUEUED");
  await page.goto("/");
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("验证 RFP");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "删除任务 验证 RFP", exact: true }).click();
  expect(state.deleteCalls).toEqual([]);
  await expect(page.getByRole("button", { name: "验证 RFP", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "验证 RFP", exact: true }).click();
  page.once("dialog", async (dialog) => { await dialog.accept(); });
  await page.getByRole("button", { name: "删除任务", exact: true }).click();
  await expect(page.getByText("任务已删除", { exact: true })).toBeVisible();
  await expect(page.locator(".progress-card")).toHaveCount(0);
  await expect(page.locator(".rfp-title")).toHaveCount(0);
  expect(state.deleteCalls).toEqual([`/rfps/${rfpId}`]);
  await page.waitForTimeout(5500);
  await expect(page.locator(".rfp-title")).toHaveCount(0);
  await expect(page.locator(".alert.error")).toHaveCount(0);
});

test("customer deletion displays conflict then succeeds after its tasks are deleted", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/");
  page.on("dialog", async (dialog) => { await dialog.accept(); });
  await page.getByRole("button", { name: "客户管理", exact: true }).click();
  await page.getByRole("button", { name: "删除客户 验证客户", exact: true }).click();
  await expect(page.getByText("该客户仍有关联任务，请先删除其全部 RFP 任务")).toBeVisible();
  await expect(page.locator(".customer-card")).toHaveCount(1);
  await page.getByRole("button", { name: /^RFP 工作台/ }).click();
  await page.getByRole("button", { name: "删除任务 验证 RFP", exact: true }).click();
  await expect(page.getByText("任务已删除", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "客户管理", exact: true }).click();
  await page.getByRole("button", { name: "删除客户 验证客户", exact: true }).click();
  await expect(page.getByText("客户已删除", { exact: true })).toBeVisible();
  await expect(page.locator(".customer-card")).toHaveCount(0);
  expect(state.customerDeleted).toBe(true);
  await page.getByRole("button", { name: "新建 RFP", exact: true }).click();
  await expect(page.getByText("请先到客户管理创建客户。")).toBeVisible();
});

test("knowledge deletion retains the card on failure and removes it on success", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.knowledgeVisible = true;
  state.knowledgeDeleteError = true;
  await page.goto("/");
  await page.getByRole("button", { name: "企业知识库", exact: true }).click();
  page.on("dialog", async (dialog) => {
    expect(dialog.message()).toContain("向量索引将删除");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "删除知识库文档 验证知识库", exact: true }).click();
  await expect(page.getByText("知识库索引删除失败，请稍后重试；文档尚未删除")).toBeVisible();
  await expect(page.locator(".document-card")).toHaveCount(1);
  state.knowledgeDeleteError = false;
  await page.getByRole("button", { name: "删除知识库文档 验证知识库", exact: true }).click();
  await expect(page.getByText("知识库文档已删除", { exact: true })).toBeVisible();
  await expect(page.locator(".document-card")).toHaveCount(0);
  await expect(page.locator(".alert.error")).toHaveCount(0);
});

test("delete controls remain usable on mobile", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.knowledgeVisible = true;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  for (const [nav, button] of [["客户管理", "删除客户 验证客户"], ["企业知识库", "删除知识库文档 验证知识库"]]) {
    await page.getByRole("button", { name: nav, exact: true }).click();
    await expect(page.getByRole("button", { name: button, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
  await page.screenshot({ path: "test-results/delete-controls-mobile.png", fullPage: true });
});

const formattedProposal = [
  "# 企业服务建设方案",
  "",
  "## 执行摘要",
  "",
  "提供 **单点登录** 和 *私有化部署*，使用 `SAML 2.0` 集成。",
  "",
  "## Requirement Response Matrix",
  "",
  "| Requirement | Status | Response | Evidence | Risk / Gap |",
  "| --- | --- | --- | --- | --- |",
  "| REQ-0001：SSO | SUPPORTED | 支持 SAML 登录 | 产品手册 | 无 |",
  "| REQ-0002：部署 | PARTIALLY_SUPPORTED | 支持私有化部署 | 交付记录 | 需确认环境 |",
  "",
  "### 实施步骤",
  "",
  "1. 确认需求",
  "2. 部署验证",
  "",
  "- 安全审查",
  "- 接口联调",
  "",
  "- [x] 已完成需求梳理",
  "- [ ] 等待验收",
  "",
  "> 交付周期以确认后的范围为准。",
  "",
  "~~旧版本说明~~",
  "",
  "```json",
  '{"deployment": "private", "enabled": true}',
  "```",
  "",
  "[技术文档](https://example.test/docs)",
].join("\n");

async function openProposal(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "验证 RFP", exact: true }).click();
  await page.getByRole("button", { name: /方案与审核/ }).click();
  await expect(page.locator(".markdown-body")).toBeVisible();
}

test("proposal renders Markdown headings, tables, lists and code without changing download", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.markdown = formattedProposal;
  await openProposal(page);
  const preview = page.locator(".markdown-body");
  await expect(preview.getByRole("heading", { level: 1 })).toHaveText("企业服务建设方案");
  await expect(preview.getByRole("heading", { level: 2 })).toHaveCount(2);
  await expect(preview.locator("strong")).toHaveText("单点登录");
  await expect(preview.locator("em")).toHaveText("私有化部署");
  await expect(preview.getByRole("table")).toBeVisible();
  await expect(preview.getByRole("columnheader")).toHaveCount(5);
  await expect(preview.getByRole("cell", { name: "REQ-0001：SSO", exact: true })).toBeVisible();
  await expect(preview.locator("ol > li")).toHaveCount(2);
  await expect(preview.locator("ul > li:not(.task-list-item)").first()).toHaveCSS("list-style-type", "disc");
  await expect(preview.locator("li.task-list-item").first()).toHaveCSS("list-style-type", "none");
  await expect(preview.getByRole("checkbox")).toHaveCount(2);
  await expect(preview.getByRole("checkbox").first()).toBeChecked();
  await expect(preview.getByRole("checkbox").first()).toBeDisabled();
  await expect(preview.locator("blockquote")).toContainText("交付周期");
  await expect(preview.locator("del")).toHaveText("旧版本说明");
  await expect(preview.locator("pre code")).toHaveText('{"deployment": "private", "enabled": true}');
  await expect(preview.getByRole("link", { name: "技术文档" })).toHaveAttribute("rel", "noopener noreferrer");
  const downloadLink = page.getByRole("link", { name: "下载 Markdown" });
  await expect(downloadLink).toHaveAttribute("download", "proposal-v1.md");
  await expect(downloadLink).toHaveAttribute("href", `/proposals/${proposalId}/markdown`);
  // Mocked navigation downloads are canceled by Edge; check the unchanged source
  // here and verify actual downloaded bytes in the real-server test below.
  const source = await page.evaluate(async (url) => (await fetch(url)).text(), `/proposals/${proposalId}/markdown`);
  expect(source).toBe(formattedProposal);
  await expect(page.getByRole("button", { name: "通过审核", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/markdown-preview-desktop.png", fullPage: true });
});

test("Markdown does not execute HTML, allow dangerous URLs or auto-load images", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.markdown = [
    "# 安全预览",
    "",
    '<script>window.__markdownUnsafe = true</script>',
    "",
    '<img src="https://tracker.invalid/raw" onerror="window.__markdownUnsafe = true">',
    "",
    '<iframe src="https://tracker.invalid/frame"></iframe>',
    "",
    '[危险链接](javascript:alert%281%29)',
    "",
    '[内嵌数据](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)',
    "",
    '![外部示意图](https://tracker.invalid/image)',
    "",
    '```html',
    '<script>shown as code</script>',
    '```',
  ].join("\n");
  const externalRequests: string[] = [];
  await page.route("https://tracker.invalid/**", async (route) => {
    externalRequests.push(route.request().url());
    await route.abort();
  });
  await openProposal(page);
  const preview = page.locator(".markdown-body");
  await expect(preview.locator("script, iframe, img, [onerror]")).toHaveCount(0);
  await expect(preview.locator('a[href^="javascript:"], a[href^="data:"]')).toHaveCount(0);
  await expect(preview.getByRole("link", { name: "查看图片" })).toHaveAttribute("href", "https://tracker.invalid/image");
  await expect(preview.locator("pre code")).toHaveText("<script>shown as code</script>");
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__markdownUnsafe)).toBeUndefined();
  expect(externalRequests).toEqual([]);
});

test("wide Markdown tables and code scroll without expanding the mobile page", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.markdown = `${formattedProposal}\n\n\`\`\`text\n${"long-code-".repeat(70)}\n\`\`\``;
  await page.setViewportSize({ width: 390, height: 844 });
  await openProposal(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const table = page.getByRole("region", { name: "方案表格" });
  expect(await table.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  await table.focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("button", { name: "通过审核", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/markdown-preview-mobile.png", fullPage: true });
});

test("running container serves real records and the complete read-only workflow", async ({ page }) => {
  test.skip(!process.env.WEB_TEST_URL, "only runs against an explicitly selected server");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "RFP 处理进度" })).toBeVisible();
  await expect(page.locator(".alert.error")).toHaveCount(0);
  await page.screenshot({ path: "test-results/dealflow-overview.png", fullPage: true });
  if (await page.locator(".rfp-title").count()) {
    await page.locator(".rfp-title").first().click();
    await expect(page.locator(".progress-card")).toBeVisible();
    await page.getByRole("button", { name: /能力判断/ }).click();
    await expect(page.locator(".loading.compact")).toHaveCount(0);
    await page.getByRole("button", { name: /方案与审核/ }).click();
    await expect(page.locator(".loading.compact")).toHaveCount(0);
    await expect(page.locator(".alert.error")).toHaveCount(0);
    if (await page.locator(".markdown-body").count()) {
      await expect(page.locator(".markdown-body h1")).toBeVisible();
      await expect(page.locator(".markdown-body table")).toBeVisible();
      const downloadLink = page.getByRole("link", { name: "下载 Markdown" });
      const href = await downloadLink.getAttribute("href");
      const response = await page.request.get(href!);
      expect(response.ok()).toBe(true);
      expect(response.headers()["content-type"]).toContain("text/markdown");
      const downloadPromise = page.waitForEvent("download");
      await downloadLink.click();
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toMatch(/^proposal-v\d+\.md$/);
      const stream = await download.createReadStream();
      const chunks: Buffer[] = [];
      for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
      expect(Buffer.concat(chunks)).toEqual(await response.body());
    }
    await page.screenshot({ path: "test-results/dealflow-detail.png", fullPage: true });
  }
  await page.getByRole("button", { name: "企业知识库", exact: true }).click();
  await expect(page.getByRole("heading", { name: "企业知识库", exact: true }).last()).toBeVisible();
  expect(errors).toEqual([]);
});
