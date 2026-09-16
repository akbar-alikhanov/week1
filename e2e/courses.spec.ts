import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-course-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

test("browsing a course and completing a lesson updates progress", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Course E2E User");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  await page.goto("/courses");
  await expect(page.getByRole("heading", { name: "Courses" })).toBeVisible();
  await page.getByRole("link", { name: /^Excel/ }).click();
  await expect(page).toHaveURL(/\/courses\/excel/);

  await page.getByRole("link", { name: "Интерфейс Excel" }).click();
  await expect(page).toHaveURL(/\/courses\/excel\/module-01-basics\/01-interface/);
  await expect(page.getByRole("heading", { name: "Интерфейс Excel" })).toBeVisible();
  await expect(page.getByText("Строка формул").first()).toBeVisible();

  await page.getByRole("button", { name: "Mark lesson as complete" }).click();
  // Completing a lesson with a next lesson available auto-advances to it.
  await expect(page).toHaveURL(
    /\/courses\/excel\/module-01-basics\/02-cells-rows-columns/,
  );

  await page.goto("/courses/excel");
  const firstLessonRow = page.getByRole("link", { name: "Интерфейс Excel" });
  await expect(firstLessonRow.locator("svg").first()).toBeVisible();
});
