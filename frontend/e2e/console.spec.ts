import { test, expect } from "@playwright/test";

test("create, validate, publish and execute three edited sequential steps", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Execution activity" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Create workflow" }).click();
  await page
    .getByLabel("Workflow name")
    .fill("Document normalization " + Date.now());
  await page
    .getByLabel("Description", { exact: true })
    .fill("Validates, transforms and returns text.");
  await page.getByLabel("Step name").fill("Validate input");
  await page.getByLabel("Configuration JSON").fill('{"required":["text"]}');
  await page.getByRole("button", { name: "Add step" }).click();
  await page.getByLabel("Task type").selectOption("text.transform");
  await page.getByLabel("Step name").fill("Transform text");
  await page.getByLabel("Configuration JSON").fill('{"source":"step_1"}');
  await page.getByLabel("Maximum attempts").fill("2");
  await page.getByRole("button", { name: "Add step" }).click();
  await page.getByLabel("Step name").fill("Return result");
  await page.getByLabel("Task type").selectOption("text.concatenate");
  await page
    .getByLabel("Configuration JSON")
    .fill('{"source":"step_2","suffix":"!"}');
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(page.getByText("Definition is valid")).toBeVisible();
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run workflow" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run workflow" }).click();
  await page.getByLabel("Input JSON").fill('{"text":"verified"}');
  await page.getByRole("button", { name: "Start execution" }).click();
  await expect(
    page.getByRole("heading", { name: "Step timeline" }),
  ).toBeVisible();
  await expect(page.locator(".page-head .badge")).toHaveText("completed", {
    timeout: 30000,
  });
  await expect(
    page.getByRole("heading", { name: "Final output" }).locator("xpath=../.."),
  ).toContainText("VERIFIED!");
  await expect(page.getByText("WORKFLOW_COMPLETED")).toBeVisible();
  await page.reload();
  await expect(page.locator(".page-head .badge")).toHaveText("completed");
  expect(errors).toEqual([]);
});

test("navigate health, workers, workflow library and narrow overview", async ({
  page,
}) => {
  await page.goto("/workers");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByRole("link", { name: "System health", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "PostgreSQL queue" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByLabel("Search workflows").fill("Retry Exhaustion Demo");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.locator("tbody a").first().click();
  await page.getByRole("button", { name: "Run workflow" }).click();
  await page.getByRole("button", { name: "Start execution" }).click();
  await expect(page.locator(".page-head .badge")).toHaveText("failed", {
    timeout: 30000,
  });
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(4, { timeout: 20000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Event log", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Recent events" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
