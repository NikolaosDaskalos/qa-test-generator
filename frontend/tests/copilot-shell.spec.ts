import { expect, test } from "@playwright/test"

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
    page.getByRole("region", { name: "Repository details" }),
  ).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toHaveCount(0)

  await page.getByRole("button", { name: /ready-api/i }).click()
  await expect(page.getByText("ready-api selected")).toBeVisible()
  await expect(
    page.getByRole("textbox", { name: "Ask about the selected repository" }),
  ).toBeEnabled()
})

test("Selecting a ready Repository does not create a Repository Session implicitly", async ({
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

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()

  await expect(page.getByText("Start a new session")).toBeVisible()
  await expect(page.getByRole("button", { name: "Ask" })).toBeDisabled()
  expect(createSessionRequested).toBe(false)
})

test("Repository tree expands only the active Repository and lists its sessions", async ({
  page,
}) => {
  await page.route("**/api/v1/repositories/**", async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "repo-one",
            user_id: "user-1",
            repository_url: "https://github.com/acme/one-api",
            name: "one-api",
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
            id: "repo-two",
            user_id: "user-1",
            repository_url: "https://github.com/acme/two-api",
            name: "two-api",
            provider: "github",
            owner: "acme",
            default_branch: "main",
            indexed_commit_sha: "def456",
            status: "ready",
            failed_reason: null,
            created_at: "2026-06-17T10:00:00Z",
            updated_at: "2026-06-17T10:05:00Z",
          },
        ],
        count: 2,
      },
    })
  })
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    const url = new URL(route.request().url())
    const repositoryId = url.searchParams.get("repository_id")
    await route.fulfill({
      json: {
        data:
          repositoryId === "repo-one"
            ? [
                {
                  id: "session-one",
                  title: "Auth questions",
                  owner_id: "user-1",
                  repository_id: "repo-one",
                  created_at: "2026-06-17T09:00:00Z",
                  updated_at: "2026-06-17T09:10:00Z",
                },
              ]
            : [
                {
                  id: "session-two",
                  title: "Billing questions",
                  owner_id: "user-1",
                  repository_id: "repo-two",
                  created_at: "2026-06-17T10:00:00Z",
                  updated_at: "2026-06-17T10:10:00Z",
                },
              ],
        count: 1,
      },
    })
  })

  await page.goto("/")
  await page.getByRole("button", { name: /one-api/i }).click()

  const repositoryRegion = page.getByRole("region", { name: "Repository" })
  await expect(repositoryRegion.getByText("Auth questions")).toBeVisible()
  await expect(repositoryRegion.getByText("Billing questions")).toHaveCount(0)
  await expect(
    repositoryRegion.getByRole("button", { name: "New Session" }),
  ).toBeVisible()

  await page.getByRole("button", { name: /two-api/i }).click()

  await expect(repositoryRegion.getByText("Auth questions")).toHaveCount(0)
  await expect(repositoryRegion.getByText("Billing questions")).toBeVisible()
})

test("Direct Repository Session URL restores the selected chat workspace", async ({
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "session-stored",
            title: "Login questions",
            owner_id: "user-1",
            repository_id: "repo-ready",
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:10:00Z",
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
              id: "message-assistant",
              session_id: "session-stored",
              role: "assistant",
              content: "Login routes are tested in the browser suite.",
              citations: [{ source: "frontend/tests/login.spec.ts" }],
              position: 1,
              created_at: "2026-06-17T09:00:01Z",
            },
          ],
        },
      })
    },
  )

  await page.goto("/?repository=repo-ready&session=session-stored")

  await expect(page.getByText("ready-api selected")).toBeVisible()
  await expect(
    page.getByText("Login routes are tested in the browser suite."),
  ).toBeVisible()
  await expect(page.getByText("frontend/tests/login.spec.ts")).toBeVisible()
  expect(createSessionRequested).toBe(false)
})

test("Root workspace reopens the last-used accessible Repository Session", async ({
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "session-stored",
            title: "Stored questions",
            owner_id: "user-1",
            repository_id: "repo-ready",
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:10:00Z",
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
              content: "Stored history is visible after login.",
              citations: [],
              position: 1,
              created_at: "2026-06-17T09:00:01Z",
            },
          ],
        },
      })
    },
  )

  await page.goto("/")
  await page.evaluate(() => {
    localStorage.setItem(
      "repository-session:last",
      JSON.stringify({
        repositoryId: "repo-ready",
        sessionId: "session-stored",
      }),
    )
  })
  await page.reload()

  await expect(page.getByText("ready-api selected")).toBeVisible()
  await expect(
    page.getByText("Stored history is visible after login."),
  ).toBeVisible()
  await expect(page).toHaveURL(
    /\/\?repository=repo-ready&session=session-stored$/,
  )
})

test("Root workspace ignores a stale last-used Repository Session", async ({
  page,
}) => {
  let historyRequested = false

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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
  })
  await page.route(
    "**/api/v1/sessions/session-stale/history",
    async (route) => {
      historyRequested = true
      await route.fulfill({ status: 404 })
    },
  )

  await page.goto("/")
  await page.evaluate(() => {
    localStorage.setItem(
      "repository-session:last",
      JSON.stringify({
        repositoryId: "repo-ready",
        sessionId: "session-stale",
      }),
    )
  })
  await page.reload()

  await expect(page.getByText("ready-api selected")).toBeVisible()
  await expect(page.getByText("Start a new session")).toBeVisible()
  await expect(page).toHaveURL(/\/\?repository=repo-ready$/)
  expect(historyRequested).toBe(false)
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
  await page.getByRole("button", { name: "New Session" }).click()
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "session-stored",
            title: "Stored Repository Session",
            owner_id: "user-1",
            repository_id: "repo-ready",
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:00:00Z",
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
  await expect(page).toHaveURL(
    /\/\?repository=repo-ready&session=session-stored$/,
  )
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            id: "session-stored",
            title: "Stored Repository Session",
            owner_id: "user-1",
            repository_id: "repo-ready",
            created_at: "2026-06-17T09:00:00Z",
            updated_at: "2026-06-17T09:00:00Z",
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
  await expect(page).toHaveURL(/\/\?repository=repo-ready&session=session-new$/)
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
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Will this fail?")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(
    page.getByText("Question stream failed with status 502."),
  ).toBeVisible()
  await expect(page.getByRole("region", { name: "Chat" })).toBeVisible()
})

test("User can request test generation and see the reviewed Test Patch", async ({
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"stage","stage":"planning"}\n\n',
          'data: {"type":"stage","stage":"retrieving"}\n\n',
          'data: {"type":"stage","stage":"researching"}\n\n',
          'data: {"type":"stage","stage":"generating"}\n\n',
          'data: {"type":"run_started","coding_run_id":"run-123"}\n\n',
          'data: {"type":"stage","stage":"reviewing"}\n\n',
          'data: {"type":"review_result","coding_run_id":"run-123","accepted":true,"score":8,"threshold":7,"findings":[{"category":"coverage","detail":"Covers the successful login path."},{"category":"conventions","detail":"Uses existing test fixtures."}],"diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_success():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Add tests for login")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(page.getByText("planning")).toBeVisible()
  await expect(page.getByText("retrieving")).toBeVisible()
  await expect(page.getByText("researching")).toBeVisible()
  await expect(page.getByText("generating")).toBeVisible()
  await expect(page.getByText("reviewing")).toBeVisible()
  await expect(page.getByText("Coding Run run-123")).toBeVisible()
  await expect(page.getByText("Accepted")).toBeVisible()
  await expect(page.getByText("Score 8/10; threshold 7")).toBeVisible()
  await expect(
    page.getByText("Covers the successful login path."),
  ).toBeVisible()
  await expect(page.getByText("Uses existing test fixtures.")).toBeVisible()
  await expect(
    page.getByText("diff --git a/tests/test_login.py").last(),
  ).toBeVisible()
  await expect(
    page
      .getByText(
        "These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only.",
      )
      .last(),
  ).toBeVisible()
  await expect(page.getByText("Awaiting the owner's decision.")).toBeVisible()
})

test("User can approve a reviewed Test Patch and see the pushed branch", async ({
  page,
}) => {
  let streamCount = 0

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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
      streamCount += 1

      if (streamCount === 1) {
        await route.fulfill({
          contentType: "text/event-stream",
          body: [
            'data: {"type":"run_started","coding_run_id":"run-approve"}\n\n',
            'data: {"type":"review_result","coding_run_id":"run-approve","accepted":true,"score":8,"threshold":7,"findings":[{"category":"coverage","detail":"Covers the successful login path."}],"diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_success():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
          ].join(""),
        })
        return
      }

      expect(route.request().postDataJSON()).toEqual({
        coding_run_id: "run-approve",
        approved: true,
        feedback: "",
      })
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"stage","stage":"git_push"}\n\n',
          'data: {"type":"run_approved","coding_run_id":"run-approve","branch":"qa-tests/run-approve","diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_success():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Add tests for login")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible()
  await page.getByRole("button", { name: "Approve" }).click()

  await expect(page.getByText("git_push")).toBeVisible()
  await expect(page.getByText("Approved and pushed")).toBeVisible()
  await expect(page.getByText("Branch qa-tests/run-approve")).toBeVisible()
  await expect(
    page.getByText("diff --git a/tests/test_login.py").last(),
  ).toBeVisible()
  await expect(
    page
      .getByText(
        "These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only.",
      )
      .last(),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible()
  await expect(page.getByRole("button", { name: "Reject" })).not.toBeVisible()
})

test("User can reject a reviewed Test Patch with optional feedback", async ({
  page,
}) => {
  let streamCount = 0

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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
      streamCount += 1

      if (streamCount === 1) {
        await route.fulfill({
          contentType: "text/event-stream",
          body: [
            'data: {"type":"run_started","coding_run_id":"run-reject"}\n\n',
            'data: {"type":"review_result","coding_run_id":"run-reject","accepted":true,"score":8,"threshold":7,"findings":[{"category":"coverage","detail":"Covers the successful login path."}],"diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_success():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
          ].join(""),
        })
        return
      }

      expect(route.request().postDataJSON()).toEqual({
        coding_run_id: "run-reject",
        approved: false,
        feedback: "Please cover the locked account path too.",
      })
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"run_rejected","coding_run_id":"run-reject","findings":[{"category":"coverage","detail":"Missing locked account coverage."}],"diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_success():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Add tests for login")
  await page.getByRole("button", { name: "Ask" }).click()

  await page
    .getByRole("textbox", { name: "Reject feedback" })
    .fill("Please cover the locked account path too.")
  await page.getByRole("button", { name: "Reject" }).click()

  await expect(page.getByText("Rejected and discarded")).toBeVisible()
  await expect(page.getByText("Missing locked account coverage.")).toBeVisible()
  await expect(
    page.getByText("diff --git a/tests/test_login.py").last(),
  ).toBeVisible()
  await expect(
    page
      .getByText(
        "These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only.",
      )
      .last(),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible()
  await expect(page.getByRole("button", { name: "Reject" })).not.toBeVisible()
})

test("Failed test generation renders the failed stage and sanitized reason", async ({
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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"stage","stage":"planning"}\n\n',
          'data: {"type":"run_started","coding_run_id":"run-failed"}\n\n',
          'data: {"type":"stage","stage":"generating"}\n\n',
          'data: {"type":"run_failure","coding_run_id":"run-failed","failed_stage":"generating","reason":"The requested target is outside the allowed test file boundary."}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Add tests outside the test root")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(page.getByText("Coding Run run-failed").first()).toBeVisible()
  await expect(page.getByText("Run failed during generating.")).toBeVisible()
  await expect(
    page.getByText(
      "The requested target is outside the allowed test file boundary.",
    ),
  ).toBeVisible()
  await expect(
    page.getByText("Question stream failed", { exact: false }),
  ).not.toBeVisible()
})

test("Repository questions and test generation coexist in one chat history", async ({
  page,
}) => {
  let questionCount = 0

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
  await page.route(/\/api\/v1\/sessions\?/, async (route) => {
    await route.fulfill({ json: { data: [], count: 0 } })
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
      questionCount += 1

      if (questionCount === 1) {
        await route.fulfill({
          contentType: "text/event-stream",
          body: [
            'data: {"type":"stage","stage":"retrieving"}\n\n',
            'data: {"type":"result","answer":"The login route lives in backend/app/api/routes/login.py.","citations":[{"source":"backend/app/api/routes/login.py"}]}\n\n',
          ].join(""),
        })
        return
      }

      await route.fulfill({
        contentType: "text/event-stream",
        body: [
          'data: {"type":"stage","stage":"planning"}\n\n',
          'data: {"type":"run_started","coding_run_id":"run-mixed"}\n\n',
          'data: {"type":"review_result","coding_run_id":"run-mixed","accepted":true,"score":9,"threshold":7,"findings":[{"category":"coverage","detail":"Adds login route coverage."}],"diff":"diff --git a/tests/test_login.py b/tests/test_login.py\\n+def test_login_route():\\n+    assert True\\n","disclaimer":"These tests were not executed and their runtime correctness was not verified; the patch was assessed statically only."}\n\n',
        ].join(""),
      })
    },
  )

  await page.goto("/")
  await page.getByRole("button", { name: /ready-api/i }).click()
  await page.getByRole("button", { name: "New Session" }).click()
  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Where is the login route?")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(
    page.getByText("The login route lives in backend/app/api/routes/login.py."),
  ).toBeVisible()

  await page
    .getByRole("textbox", { name: "Ask about the selected repository" })
    .fill("Add tests for the login route")
  await page.getByRole("button", { name: "Ask" }).click()

  await expect(page.getByText("Where is the login route?")).toBeVisible()
  await expect(page.getByText("Add tests for the login route")).toBeVisible()
  await expect(
    page.getByText("The login route lives in backend/app/api/routes/login.py."),
  ).toBeVisible()
  await expect(page.getByText("Coding Run run-mixed")).toBeVisible()
  await expect(page.getByText("Adds login route coverage.")).toBeVisible()
})
