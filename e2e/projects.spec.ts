import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-project-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

async function registerAndSignIn(page: import("@playwright/test").Page) {
  const email = uniqueEmail();
  await page.goto("/register");
  await page.getByLabel("Name").fill("Project E2E User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  return email;
}

test("projects list shows the unlocked Excel project", async ({ page }) => {
  await registerAndSignIn(page);

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Анализ продаж розничной сети/ }),
  ).toBeVisible();
});

test("submitting a project awards XP and records the submission", async ({ page }) => {
  await registerAndSignIn(page);

  await page.goto("/projects/sales-analysis-excel");
  await expect(
    page.getByRole("heading", { name: "Анализ продаж розничной сети" }),
  ).toBeVisible();

  await page
    .getByLabel(/Summary of your approach/)
    .fill(
      "I aggregated revenue by store and category, found the strongest and weakest months, and shortlisted 3 slow-moving products for a discount.",
    );
  await page.getByRole("button", { name: "Submit project" }).click();

  await expect(page.getByText(/project submitted/i)).toBeVisible();
  await expect(page.getByText("Your submissions")).toBeVisible();
});
