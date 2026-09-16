import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-dashboard-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

test("dashboard, roadmap and navigation reflect progress after completing a lesson", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Dashboard E2E User");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  // Roadmap: Excel unlocked, SQL locked (Excel not complete yet).
  await page.getByRole("link", { name: "Roadmap" }).first().click();
  await expect(page).toHaveURL(/\/roadmap/);
  const main = page.getByRole("main");
  await expect(main.getByText("Excel")).toBeVisible();
  const sqlNode = main.getByText("SQL", { exact: true }).locator("..");
  await expect(sqlNode.getByText("Done")).not.toBeVisible();

  // Complete a lesson, then check dashboard reflects it.
  await page.goto("/courses/excel/module-01-basics/01-interface");
  await page.getByRole("button", { name: "Mark lesson as complete" }).click();

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /good to see you/i })).toBeVisible();
  await expect(page.getByText("Continue learning")).toBeVisible();

  // Practice hub lists exercises across the whole catalog.
  await page.getByRole("link", { name: "Exercises" }).first().click();
  await expect(page).toHaveURL(/\/exercises/);
  await expect(page.getByText("Адрес ячейки")).toBeVisible();

  // Achievements page shows FIRST_LESSON unlocked.
  await page.getByRole("link", { name: "Achievements" }).first().click();
  await expect(page).toHaveURL(/\/profile\/achievements/);
  await expect(page.getByText("First Lesson", { exact: true })).toBeVisible();
});
