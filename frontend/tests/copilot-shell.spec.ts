import { expect, test } from "@playwright/test"

test("Authenticated user lands on the Copilot shell", async ({ page }) => {
  await page.goto("/")

  await expect(page.getByRole("heading", { name: "Copilot" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Repository" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Chat" })).toBeVisible()
})
