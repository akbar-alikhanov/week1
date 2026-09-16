import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-playground-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

test("SQL Playground runs a query against the sandbox and shows results", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Playground E2E User");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  await page.goto("/playground");
  await expect(page.getByRole("heading", { name: "SQL Playground" })).toBeVisible();
  await expect(page.getByText("customers")).toBeVisible();

  await page.getByRole("button", { name: "Run Query" }).click();
  await expect(page.getByText("customer_id").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Alice Johnson")).toBeVisible();
});

test("SQL Playground rejects a write query", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Playground E2E User 2");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  await page.goto("/playground");
  const editor = page.locator(".monaco-editor").first();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("DELETE FROM customers;", { delay: 20 });
  await page.getByRole("button", { name: "Run Query" }).click();

  await expect(page.getByText(/only select queries/i)).toBeVisible();
});
