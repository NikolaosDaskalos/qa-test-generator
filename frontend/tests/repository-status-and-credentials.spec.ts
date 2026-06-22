import { expect, test } from "@playwright/test"

test("Selecting a non-ready repository shows a status details view instead of a chat composer", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const url = new URL(route.request().url())

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: { data: [repositoryFixture("indexing")], count: 1 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("indexing") })
  })

  await page.goto("/?selected=repo-1")

  await expect(
    page.getByRole("region", { name: "Repository details" }),
  ).toBeVisible()
  await expect(
    page
      .getByRole("region", { name: "Repository details" })
      .getByText(/^indexing$/),
  ).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toHaveCount(0)
})

test("Selecting a ready repository shows the enabled chat composer", async ({
  page,
}) => {
  await stubSessions(page)
  await page.route("**/api/v1/repositories/**", async (route) => {
    const url = new URL(route.request().url())

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: { data: [repositoryFixture("ready")], count: 1 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("ready") })
  })

  await page.goto("/?selected=repo-1")

  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeEnabled()
  await expect(
    page.getByRole("region", { name: "Repository details" }),
  ).toHaveCount(0)
})

test("Failed repository shows its sanitized reason and offers no retry action", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const url = new URL(route.request().url())

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: {
          data: [repositoryFixture("failed", "GitHub token expired")],
          count: 1,
        },
      })
      return
    }

    await route.fulfill({
      json: repositoryFixture("failed", "GitHub token expired"),
    })
  })

  await page.goto("/?selected=repo-1")

  const details = page.getByRole("region", { name: "Repository details" })
  await expect(
    details.getByText("GitHub token expired", { exact: true }),
  ).toBeVisible()
  await expect(details.getByRole("button", { name: /retry/i })).toHaveCount(0)
})

test("New session creation is unavailable while the repository is not ready", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const url = new URL(route.request().url())

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: { data: [repositoryFixture("cloning")], count: 1 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("cloning") })
  })

  await page.goto("/?selected=repo-1")

  await expect(
    page.getByRole("region", { name: "Repository details" }),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "New Session" })).toHaveCount(0)
})

for (const status of ["ready", "indexing", "failed"]) {
  test(`A ${status} repository exposes an Update token action in the details view`, async ({
    page,
  }) => {
    await stubSessions(page)
    await page.route("**/api/v1/repositories/**", async (route) => {
      const url = new URL(route.request().url())

      if (url.pathname.endsWith("/repositories/")) {
        await route.fulfill({
          json: { data: [repositoryFixture(status)], count: 1 },
        })
        return
      }

      await route.fulfill({ json: repositoryFixture(status) })
    })

    await page.goto("/?selected=repo-1")

    await expect(
      page.getByRole("button", { name: "Update token" }),
    ).toBeVisible()
  })
}

test("Updating the repository token succeeds and leaves the status unchanged", async ({
  page,
}) => {
  let putPayload: unknown = null

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "PUT") {
      putPayload = request.postDataJSON()
      await route.fulfill({ status: 204, body: "" })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: { data: [repositoryFixture("indexing")], count: 1 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("indexing") })
  })

  await page.goto("/?selected=repo-1")

  await page.getByRole("button", { name: "Update token" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("textbox", { name: "GitHub token" }).fill("new-token")
  await dialog
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("45")
  await dialog.getByRole("button", { name: "Save token" }).click()

  await expect(page.getByText("Repository token updated.")).toBeVisible()
  expect(putPayload).toEqual({ token: "new-token", token_expiration_days: 45 })

  await expect(
    page
      .getByRole("region", { name: "Repository details" })
      .getByText(/^indexing$/),
  ).toBeVisible()
})

test("Credential update validation errors are shown and keep the dialog open", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "PUT") {
      await route.fulfill({
        status: 422,
        json: {
          detail: [
            {
              loc: ["body", "token_expiration_days"],
              msg: "Token expiration must be a positive number of days",
              type: "value_error",
            },
          ],
        },
      })
      return
    }

    if (url.pathname.endsWith("/repositories/")) {
      await route.fulfill({
        json: { data: [repositoryFixture("indexing")], count: 1 },
      })
      return
    }

    await route.fulfill({ json: repositoryFixture("indexing") })
  })

  await page.goto("/?selected=repo-1")

  await page.getByRole("button", { name: "Update token" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("textbox", { name: "GitHub token" }).fill("new-token")
  await dialog.getByRole("button", { name: "Save token" }).click()

  await expect(
    dialog.getByText("Token expiration must be a positive number of days"),
  ).toBeVisible()
  await expect(dialog).toBeVisible()
})

async function stubSessions(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/sessions/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "POST") {
      await route.fulfill({ json: sessionFixture() })
      return
    }

    if (url.pathname.endsWith("/history")) {
      await route.fulfill({ json: { data: [] } })
      return
    }

    await route.fulfill({ json: { data: [], count: 0 } })
  })
}

function sessionFixture() {
  return {
    id: "session-1",
    title: "New session",
    user_id: "user-1",
    repository_id: "repo-1",
    created_at: "2026-06-17T09:00:00Z",
    updated_at: "2026-06-17T09:00:00Z",
  }
}

function repositoryFixture(status: string, failedReason: string | null = null) {
  return {
    id: "repo-1",
    user_id: "user-1",
    repository_url: "https://github.com/acme/new-api",
    name: "new-api",
    provider: "github",
    owner: "acme",
    default_branch: null,
    indexed_commit_sha: null,
    status,
    failed_reason: failedReason,
    created_at: "2026-06-17T09:00:00Z",
    updated_at: "2026-06-17T09:00:00Z",
  }
}
