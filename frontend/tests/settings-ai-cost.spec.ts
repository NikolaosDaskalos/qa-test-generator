import { expect, test } from "@playwright/test"

function mockUser(isSuperuser: boolean) {
  return {
    id: "user-1",
    email: "member@example.com",
    is_active: true,
    is_superuser: isSuperuser,
    full_name: "Member One",
  }
}

test("A user sees their own AI Cost total in settings", async ({ page }) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({ json: mockUser(false) })
  })
  await page.route("**/api/v1/costs/me", async (route) => {
    await route.fulfill({
      json: {
        cost: 3.4567,
        input_tokens: 250000,
        output_tokens: 40000,
        total_tokens: 290000,
      },
    })
  })

  await page.goto("/")
  await page.evaluate(() => localStorage.setItem("access_token", "test-token"))
  await page.goto("/settings")

  await expect(page.getByTestId("user-total-cost")).toHaveText(
    /Your estimated AI Cost: \$3\.4567/,
  )
})

test("A non-superuser never sees the global AI Cost total", async ({
  page,
}) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({ json: mockUser(false) })
  })
  await page.route("**/api/v1/costs/me", async (route) => {
    await route.fulfill({
      json: {
        cost: 3.4567,
        input_tokens: 250000,
        output_tokens: 40000,
        total_tokens: 290000,
      },
    })
  })

  await page.goto("/")
  await page.evaluate(() => localStorage.setItem("access_token", "test-token"))
  await page.goto("/settings")

  await expect(page.getByTestId("user-total-cost")).toBeVisible()
  await expect(page.getByTestId("all-users-total-cost")).toHaveCount(0)
})

test("A superuser additionally sees the global AI Cost total", async ({
  page,
}) => {
  await page.route("**/api/v1/users/me", async (route) => {
    await route.fulfill({ json: mockUser(true) })
  })
  await page.route("**/api/v1/costs/me", async (route) => {
    await route.fulfill({
      json: {
        cost: 3.4567,
        input_tokens: 250000,
        output_tokens: 40000,
        total_tokens: 290000,
      },
    })
  })
  await page.route("**/api/v1/costs/all", async (route) => {
    await route.fulfill({
      json: {
        cost: 42.5,
        input_tokens: 9000000,
        output_tokens: 1500000,
        total_tokens: 10500000,
      },
    })
  })

  await page.goto("/")
  await page.evaluate(() => localStorage.setItem("access_token", "test-token"))
  await page.goto("/settings")

  await expect(page.getByTestId("all-users-total-cost")).toHaveText(
    /All users' estimated AI Cost: \$42\.50/,
  )
})
