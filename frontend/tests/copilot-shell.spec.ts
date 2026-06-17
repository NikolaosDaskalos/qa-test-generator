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

test("User can register a repository and see it while indexing starts", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()

    if (request.method() === "GET") {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }

    expect(request.method()).toBe("POST")
    expect(request.postDataJSON()).toEqual({
      repository_url: "https://github.com/acme/new-api",
      token: "github-token",
      token_expiration_days: 30,
    })
    await route.fulfill({
      status: 202,
      json: {
        id: "repo-new",
        user_id: "user-1",
        repository_url: "https://github.com/acme/new-api",
        name: "new-api",
        provider: "github",
        owner: "acme",
        default_branch: null,
        indexed_commit_sha: null,
        status: "pending",
        failed_reason: null,
        created_at: "2026-06-17T09:00:00Z",
        updated_at: "2026-06-17T09:00:00Z",
      },
    })
  })

  await page.goto("/")

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("30")
  await page.getByRole("button", { name: "Register repository" }).click()

  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(
    repositoryRegion.getByRole("button", { name: /new-api/i }),
  ).toBeVisible()
  await expect(repositoryRegion.getByText(/^pending$/)).toBeVisible()
  await expect(page.getByText("new-api selected")).toBeVisible()
})

test("New repository status updates live until it is ready", async ({
  page,
}) => {
  let repositoryReadCount = 0

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "GET" && url.pathname.endsWith("/repositories/")) {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }

    if (request.method() === "POST") {
      await route.fulfill({
        status: 202,
        json: {
          id: "repo-new",
          user_id: "user-1",
          repository_url: "https://github.com/acme/new-api",
          name: "new-api",
          provider: "github",
          owner: "acme",
          default_branch: null,
          indexed_commit_sha: null,
          status: "indexing",
          failed_reason: null,
          created_at: "2026-06-17T09:00:00Z",
          updated_at: "2026-06-17T09:00:00Z",
        },
      })
      return
    }

    repositoryReadCount += 1
    await route.fulfill({
      json: {
        id: "repo-new",
        user_id: "user-1",
        repository_url: "https://github.com/acme/new-api",
        name: "new-api",
        provider: "github",
        owner: "acme",
        default_branch: "main",
        indexed_commit_sha: repositoryReadCount > 1 ? "abc123" : null,
        status: repositoryReadCount > 1 ? "ready" : "indexing",
        failed_reason: null,
        created_at: "2026-06-17T09:00:00Z",
        updated_at: "2026-06-17T09:00:00Z",
      },
    })
  })

  await page.goto("/")

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("30")
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

test("Failed repository indexing shows the failure reason and stops polling", async ({
  page,
}) => {
  let repositoryReadCount = 0

  await page.route("**/api/v1/repositories/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (request.method() === "GET" && url.pathname.endsWith("/repositories/")) {
      await route.fulfill({ json: { data: [], count: 0 } })
      return
    }

    if (request.method() === "POST") {
      await route.fulfill({
        status: 202,
        json: {
          id: "repo-new",
          user_id: "user-1",
          repository_url: "https://github.com/acme/new-api",
          name: "new-api",
          provider: "github",
          owner: "acme",
          default_branch: null,
          indexed_commit_sha: null,
          status: "cloning",
          failed_reason: null,
          created_at: "2026-06-17T09:00:00Z",
          updated_at: "2026-06-17T09:00:00Z",
        },
      })
      return
    }

    repositoryReadCount += 1
    await route.fulfill({
      json: {
        id: "repo-new",
        user_id: "user-1",
        repository_url: "https://github.com/acme/new-api",
        name: "new-api",
        provider: "github",
        owner: "acme",
        default_branch: null,
        indexed_commit_sha: null,
        status: "failed",
        failed_reason: "GitHub token expired",
        created_at: "2026-06-17T09:00:00Z",
        updated_at: "2026-06-17T09:01:00Z",
      },
    })
  })

  await page.goto("/")

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://github.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("30")
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
  expect(repositoryReadCount).toBe(1)
})

test("Repository creation backend errors are shown", async ({ page }) => {
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

  await page
    .getByRole("textbox", { name: "GitHub repository URL" })
    .fill("https://example.com/acme/new-api")
  await page.getByRole("textbox", { name: "GitHub token" }).fill("github-token")
  await page
    .getByRole("spinbutton", { name: "Token expiration in days" })
    .fill("30")
  await page.getByRole("button", { name: "Register repository" }).click()

  await expect(
    page.getByText("Input should be a valid GitHub URL"),
  ).toBeVisible()
})

test("User can ask a ready Repository question and see streamed answer citations", async ({
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
        ],
        count: 1,
      },
    })
  })
  await page.route("**/api/v1/sessions", async (route) => {
    expect(route.request().method()).toBe("POST")
    expect(route.request().postDataJSON()).toEqual({
      repository_id: "repo-ready",
    })
    await route.fulfill({
      json: {
        id: "session-ready",
        title: "New Repository Session",
        owner_id: "user-1",
        repository_id: "repo-ready",
        created_at: "2026-06-17T09:00:00Z",
        updated_at: "2026-06-17T09:00:00Z",
      },
    })
  })
  await page.route(
    "**/api/v1/sessions/session-ready/history",
    async (route) => {
      await route.fulfill({ json: { data: [] } })
    },
  )
  await page.route(
    "**/api/v1/sessions/session-ready/questions",
    async (route) => {
      expect(route.request().method()).toBe("POST")
      expect(route.request().headers().authorization).toBe("Bearer test-token")
      expect(route.request().postDataJSON()).toEqual({
        question: "Where is the login route tested?",
      })

      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"stage","stage":"retrieving"}\n\n',
          'data: {"type":"token","content":"Login "}\n\n',
          'data: {"type":"token","content":"is tested."}\n\n',
          'data: {"type":"result","answer":"Login is tested.","citations":[{"source":"frontend/tests/login.spec.ts"}]}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.evaluate(() => localStorage.setItem("access_token", "test-token"))
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Where is the login route tested?")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(page.getByText("retrieving")).toBeVisible()
  await expect(page.getByText("Login is tested.")).toBeVisible()
  await expect(page.getByText("frontend/tests/login.spec.ts")).toBeVisible()
})

test("Selecting a ready Repository resumes stored Repository Session history", async ({
  page,
}) => {
  let createSessionRequested = false

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
        ],
        count: 1,
      },
    })
  })
  await page.route("**/api/v1/sessions", async (route) => {
    createSessionRequested = true
    await route.fulfill({ status: 500 })
  })
  await page.route(
    "**/api/v1/sessions/session-stored/history",
    async (route) => {
      await route.fulfill({
        json: {
          data: [
            {
              id: "message-user",
              session_id: "session-stored",
              role: "user",
              content: "Where is login tested?",
              citations: [],
              position: 1,
              created_at: "2026-06-17T09:00:00Z",
            },
            {
              id: "message-assistant",
              session_id: "session-stored",
              role: "assistant",
              content: "Login is tested in the browser spec.",
              citations: [{ source: "frontend/tests/login.spec.ts" }],
              position: 2,
              created_at: "2026-06-17T09:00:01Z",
            },
          ],
        },
      })
    },
  )

  await page.goto("/")
  await page.evaluate(() =>
    localStorage.setItem("repository-session:repo-ready", "session-stored"),
  )
  await page.getByRole("button", { name: /ready-api/i }).click()

  await expect(page.getByText("Where is login tested?")).toBeVisible()
  await expect(
    page.getByText("Login is tested in the browser spec."),
  ).toBeVisible()
  await expect(page.getByText("frontend/tests/login.spec.ts")).toBeVisible()
  expect(createSessionRequested).toBe(false)
})

test("New Session creates a fresh Repository Session and clears chat", async ({
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
        ],
        count: 1,
      },
    })
  })
  await page.route(
    "**/api/v1/sessions/session-stored/history",
    async (route) => {
      await route.fulfill({
        json: {
          data: [
            {
              id: "message-assistant",
              session_id: "session-stored",
              role: "assistant",
              content: "Previous answer.",
              citations: [{ source: "backend/app/api/routes/login.py" }],
              position: 1,
              created_at: "2026-06-17T09:00:01Z",
            },
          ],
        },
      })
    },
  )
  await page.route("**/api/v1/sessions", async (route) => {
    expect(route.request().method()).toBe("POST")
    await route.fulfill({
      json: {
        id: "session-new",
        title: "New Repository Session",
        owner_id: "user-1",
        repository_id: "repo-ready",
        created_at: "2026-06-17T09:10:00Z",
        updated_at: "2026-06-17T09:10:00Z",
      },
    })
  })
  await page.route("**/api/v1/sessions/session-new/history", async (route) => {
    await route.fulfill({ json: { data: [] } })
  })

  await page.goto("/")
  await page.evaluate(() =>
    localStorage.setItem("repository-session:repo-ready", "session-stored"),
  )
  await page.getByRole("button", { name: /ready-api/i }).click()
  await expect(page.getByText("Previous answer.")).toBeVisible()

  await page.getByRole("button", { name: "New Session" }).click()

  await expect(page.getByText("Previous answer.")).not.toBeVisible()
  await expect(page.getByText("Chat is ready for ready-api.")).toBeVisible()
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("repository-session:repo-ready"),
      ),
    )
    .toBe("session-new")
})

test("Question stream transport errors are shown without crashing", async ({
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
        ],
        count: 1,
      },
    })
  })
  await page.route("**/api/v1/sessions", async (route) => {
    await route.fulfill({
      json: {
        id: "session-ready",
        title: "New Repository Session",
        owner_id: "user-1",
        repository_id: "repo-ready",
        created_at: "2026-06-17T09:00:00Z",
        updated_at: "2026-06-17T09:00:00Z",
      },
    })
  })
  await page.route(
    "**/api/v1/sessions/session-ready/history",
    async (route) => {
      await route.fulfill({ json: { data: [] } })
    },
  )
  await page.route(
    "**/api/v1/sessions/session-ready/questions",
    async (route) => {
      await route.fulfill({ status: 502, body: "upstream failed" })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Will this fail?")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(
    page.getByText("Question stream failed with status 502."),
  ).toBeVisible()
  await expect(page.getByRole("region", { name: "Chat" })).toBeVisible()
})
