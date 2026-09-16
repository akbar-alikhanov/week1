import { expect, test } from "@playwright/test";

function uniqueEmail() {
  return `e2e-career-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

async function registerAndSignIn(page: import("@playwright/test").Page) {
  const email = uniqueEmail();
  await page.goto("/register");
  await page.getByLabel("Name").fill("Career E2E User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test("interview prep shows SQL questions and switches to Excel questions", async ({
  page,
}) => {
  await registerAndSignIn(page);

  await page.goto("/career");
  await expect(page.getByRole("heading", { name: "Interview prep" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /INNER JOIN и LEFT JOIN/ }),
  ).toBeVisible();

  await page.getByRole("button", { name: /INNER JOIN и LEFT JOIN/ }).click();
  await expect(page.getByText(/возвращает только строки/)).toBeVisible();

  await page.getByRole("tab", { name: "Excel" }).click();
  await expect(page.getByRole("button", { name: /ВПР \(VLOOKUP\)/ })).toBeVisible();
});

test("resume builder fills in fields and updates the live preview", async ({ page }) => {
  await registerAndSignIn(page);

  await page.goto("/career/resume");
  await expect(page.getByRole("heading", { name: "Resume builder" })).toBeVisible();

  await page.getByLabel("Full name").fill("Ada Lovelace");
  await page.getByLabel("Email").fill("ada@example.com");

  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("ada@example.com")).toBeVisible();
});
