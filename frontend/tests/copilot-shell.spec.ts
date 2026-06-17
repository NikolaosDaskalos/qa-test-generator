import { expect, test } from "@playwright/test"

test("Authenticated user lands on the Copilot shell", async ({ page }) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })

  await page.goto("/")

  await expect(page.getByRole("heading", { name: "Copilot" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Repository" })).toBeVisible()
  await expect(page.getByRole("region", { name: "Chat" })).toBeVisible()
})

test("Empty repository list renders an empty state", async ({ page }) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })

  await page.goto("/")

  await expect(page.getByText("No repositories registered yet.")).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeDisabled()
})

test("Repository selector lists repositories with status and failure reason", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "repo-ready",
            user_id: "user-1",
            repository_url: "https://github.com/acme/ready-api",
            name: "ready-api",
            provider: "github",
            owner: "acme",
            default_branch: "main",
            indexed_commit_sha: "abc123",
            status: "ready",
            failed_reason: null,
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:05:00Z",
          },
          {
            id: "repo-failed",
            user_id: "user-1",
            repository_url: "https://github.com/acme/broken-api",
            name: "broken-api",
            provider: "github",
            owner: "acme",
            default_branch: null,
            indexed_commit_sha: null,
            status: "failed",
            failed_reason: "GitHub token expired",
            created_at: "2026-06-17T09:10:00Z",
            updated_at: "2026-06-17T09:12:00Z",
          },
        ],
        count: 2,
      },
    })
  })

  await page.goto("/")

  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(
    repositoryRegion.getByRole("button", { name: /ready-api/i }),
  ).toBeVisible()
  await expect(repositoryRegion.getByText(/^ready$/)).toBeVisible()
  await expect(
    repositoryRegion.getByRole("button", { name: /broken-api/i }),
  ).toBeVisible()
  await expect(repositoryRegion.getByText(/^failed$/)).toBeVisible()
  await expect(repositoryRegion.getByText("GitHub token expired")).toBeVisible()
})

test("Chat is enabled only for the selected ready repository", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "repo-indexing",
            user_id: "user-1",
            repository_url: "https://github.com/acme/indexing-api",
            name: "indexing-api",
            provider: "github",
            owner: "acme",
            default_branch: "main",
            indexed_commit_sha: null,
            status: "indexing",
            failed_reason: null,
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:05:00Z",
          },
          {
            id: "repo-ready",
            user_id: "user-1",
            repository_url: "https://github.com/acme/ready-api",
            name: "ready-api",
            provider: "github",
            owner: "acme",
            default_branch: "main",
            indexed_commit_sha: "abc123",
            status: "ready",
            failed_reason: null,
            created_at: "2026-06-17T09:10:00Z",
            updated_at: "2026-06-17T09:12:00Z",
          },
        ],
        count: 2,
      },
    })
  })

  await page.goto("/")

  await page.getByRole("button", { name: /indexing-api/i }).click()
  await expect(page.getByText("indexing-api selected")).toBeVisible()
  await expect(
    page.getByText("Chat is disabled while the repository is indexing."),
  ).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeDisabled()

  await page.getByRole("button", { name: /ready-api/i }).click()
  await expect(page.getByText("ready-api selected")).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeEnabled()
})
