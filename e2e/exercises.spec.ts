import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-exercise-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

async function registerAndSignIn(page: import("@playwright/test").Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Exercise E2E User");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test("solving a formula exercise grades correctly and awards XP", async ({ page }) => {
  await registerAndSignIn(page);

  await page.goto("/courses/excel/module-02-basic-formulas/09-sum");
  await expect(page.getByRole("heading", { name: "СУММ" })).toBeVisible();

  await page.getByPlaceholder(/Formula for/).fill("=СУММ(B2:B5)");
  await page.getByRole("button", { name: "Check answer" }).click();

  await expect(page.getByText("Correct!")).toBeVisible();
});

test("an incorrect multiple-choice answer shows feedback and allows retry", async ({
  page,
}) => {
  await registerAndSignIn(page);

  await page.goto("/courses/excel/module-01-basics/01-interface");
  await page.getByRole("button", { name: "7B" }).click();
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("Not quite.")).toBeVisible();

  await page.getByRole("button", { name: "B7" }).click();
  await page.getByRole("button", { name: "Check answer" }).click();
  await expect(page.getByText("Correct!")).toBeVisible();
});

test("solving a SQL exercise executes against the sandbox and grades correctly", async ({
  page,
}) => {
  await registerAndSignIn(page);

  await page.goto("/courses/sql/module-01-sql-basics/06-select");
  await expect(page.getByRole("heading", { name: "SELECT" })).toBeVisible();

  const editor = page.locator(".monaco-editor").first();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("SELECT name, price FROM products;", { delay: 20 });
  await page.getByRole("button", { name: "Check answer" }).first().click();

  await expect(page.getByText("Correct!").first()).toBeVisible({ timeout: 10_000 });
});

test("passing a lesson quiz awards XP", async ({ page }) => {
  await registerAndSignIn(page);

  await page.goto("/courses/excel/module-01-basics/01-interface");

  await page.getByRole("button", { name: "В строке формул" }).click();
  await page
    .getByRole("button", { name: "Весь файл, который может содержать несколько листов" })
    .click();

  await page.getByRole("button", { name: "Submit quiz" }).click();
  await expect(page.getByText(/you passed/i)).toBeVisible();
});
