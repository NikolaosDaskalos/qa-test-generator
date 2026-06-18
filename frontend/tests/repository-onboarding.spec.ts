import { expect, test } from "@playwright/test"

test("Authenticated shell is branded AI Codebase Copilot without template chrome", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })

  await page.goto("/")

  await expect(
    page.getByRole("link", { name: "AI Codebase Copilot" }),
  ).toBeVisible()
  await expect(page.getByText("Full Stack FastAPI Template")).toHaveCount(0)
  await expect(page.getByRole("link", { name: "GitHub" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "LinkedIn" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Dashboard" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Items" })).toHaveCount(0)

  await expect(page.getByText("Appearance")).toBeVisible()
  await expect(page.getByTestId("user-menu")).toBeVisible()
})

test("No repositories shows a central add-repository empty state", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })

  await page.goto("/")

  await expect(
    page.getByRole("link", { name: "Add your code repository" }),
  ).toBeVisible()

  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("textbox", { name: "GitHub repository URL" }),
  ).toHaveCount(0)
})

test("Add-repository action opens a dedicated registration screen with the panel and Back navigation", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()

  await expect(page).toHaveURL(/\/repositories\/new$/)
  await expect(
    page.getByRole("link", { name: "AI Codebase Copilot" }),
  ).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "GitHub repository URL" }),
  ).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "GitHub token" }),
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Register repository" }),
  ).toBeVisible()

  await page.getByRole("link", { name: "Back" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(
    page.getByRole("link", { name: "Add your code repository" }),
  ).toBeVisible()
})

test("Registering a repository returns to the workspace with it selected and its status visible", async ({
  page,
}) => {
  let created = false

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "POST") {
      expect(request.postDataJSON()).toEqual({
        repository_url: "https://github.com/acme/new-api",
        token: "github-token",
        token_expiration_days: 30,
      })
      created = true
      await route.fulfill({
        status: 202,
        json: repositoryFixture("pending"),
      })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: created
          ? { data: [repositoryFixture("pending")], count: 1 }
          : { data: [], count: 0 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("pending") })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("30")
  await page.getByRole("button", { name: "Register repository" }).click()

  await expect(page).toHaveURL(/\/\?selected=repo-new$/)
  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(
    repositoryRegion.getByRole("button", { name: /new-api/i }),
  ).toBeVisible()
  await expect(repositoryRegion.getByText(/^pending$/)).toBeVisible()
  await expect(page.getByText("new-api selected")).toBeVisible()
})

test("Registration screen shows backend validation errors and stays open", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()

    if (request.method() === "GET") {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }

    await route.fulfill({
      status: 422,
      json: {
        detail: [
          {
            loc: ["body", "repository_url"],
            msg: "Input should be a valid GitHub URL",
            type: "value_error",
          },
        ],
      },
    })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://example.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page.getByRole("button", { name: "Register repository" }).click()

  await expect(
    page.getByText("Input should be a valid GitHub URL"),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/repositories\/new$/)
})

test("Token expiration is optional and omitted when left blank", async ({
  page,
}) => {
  let created = false

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "POST") {
      expect(request.postDataJSON()).toEqual({
        repository_url: "https://github.com/acme/new-api",
        token: "github-token",
        token_expiration_days: null,
      })
      created = true
      await route.fulfill({ status: 202, json: repositoryFixture("pending") })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: created
          ? { data: [repositoryFixture("pending")], count: 1 }
          : { data: [], count: 0 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("pending") })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page.getByRole("button", { name: "Register repository" }).click()

  await expect(page.getByText("new-api selected")).toBeVisible()
})

test("Existing repositories expose a compact add action beside the heading", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { data: [repositoryFixture("ready")], count: 1 },
      })
      return
    }
    await route.fulfill({ json: repositoryFixture("ready") })
  })

  await page.goto("/")

  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(repositoryRegion.getByText("Repositories")).toBeVisible()
  await expect(
    repositoryRegion.getByRole("textbox", { name: "GitHub repository URL" }),
  ).toHaveCount(0)

  await repositoryRegion.getByRole("link", { name: "Add repository" }).click()
  await expect(page).toHaveURL(/\/repositories\/new$/)
})

test("New repository status updates live in the workspace until it is ready", async ({
  page,
}) => {
  let created = false
  let detailReadCount = 0

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "POST") {
      created = true
      await route.fulfill({ status: 202, json: repositoryFixture("indexing") })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: created
          ? { data: [repositoryFixture("indexing")], count: 1 }
          : { data: [], count: 0 },
      })
      return
    }

    detailReadCount += 1
    await route.fulfill({
      json:
        detailReadCount > 1
          ? repositoryFixture("ready")
          : repositoryFixture("indexing"),
    })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()
  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page.getByRole("button", { name: "Register repository" }).click()

  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(repositoryRegion.getByText(/^indexing$/)).toBeVisible()
  await expect(repositoryRegion.getByText(/^ready$/)).toBeVisible({
    timeout: 5000,
  })
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeEnabled()
})

test("Failed repository indexing shows the reason in the workspace and stops polling", async ({
  page,
}) => {
  let created = false
  let detailReadCount = 0

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "POST") {
      created = true
      await route.fulfill({ status: 202, json: repositoryFixture("cloning") })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: created
          ? { data: [repositoryFixture("cloning")], count: 1 }
          : { data: [], count: 0 },
      })
      return
    }

    detailReadCount += 1
    await route.fulfill({
      json: {
        ...repositoryFixture("failed"),
        failed_reason: "GitHub token expired",
      },
    })
  })

  await page.goto("/")
  await page.getByRole("link", { name: "Add your code repository" }).click()
  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page.getByRole("button", { name: "Register repository" }).click()

  await expect(page.getByText(/^failed$/)).toBeVisible()
  await expect(
    page
      .getByRole("region", { name: "Repository" })
      .getByText("GitHub token expired"),
  ).toBeVisible()
  await expect(
    page.getByText(
      "Chat is disabled because repository processing failed: GitHub token expired",
    ),
  ).toBeVisible()

  await page.waitForTimeout(1500)
  expect(detailReadCount).toBe(1)
})

function repositoryFixture(status: string) {
  return {
    id: "repo-new",
    user_id: "user-1",
    repository_url: "https://github.com/acme/new-api",
    name: "new-api",
    provider: "github",
    owner: "acme",
    default_branch: null,
    indexed_commit_sha: null,
    status,
    failed_reason: null,
    created_at: "2026-06-17T09:00:00Z",
    updated_at: "2026-06-17T09:00:00Z",
  }
}
