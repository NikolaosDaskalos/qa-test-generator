import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { type FormEvent, useEffect, useState } from "react"
import type { Citation, RepositoryPublic, SessionHistoryPublic } from "@/client"
import { RepositoriesService, SessionsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { askRepositoryQuestionStream } from "@/lib/agentStream"

type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  citations: Citation[]
}

export const Route = createFileRoute("/_layout/")({
  component: CopilotShell,
  head: () => ({
    meta: [
      {
        title: "Copilot - AI Codebase Copilot",
      },
    ],
  }),
})

function CopilotShell() {
  const queryClient = useQueryClient()
  const [activeRepository, setActiveRepository] =
    useState<RepositoryPublic | null>(null)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState("")
  const [stageStatus, setStageStatus] = useState<string | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const repositoriesQuery = useQuery({
    queryKey: ["repositories"],
    queryFn: () => RepositoriesService.readRepositories({}),
  })
  const repositoryStatusQuery = useQuery({
    queryKey: ["repository", activeRepository?.id],
    queryFn: () =>
      RepositoriesService.readRepository({
        repositoryId: activeRepository?.id ?? "",
      }),
    enabled: !!activeRepository && !isTerminalStatus(activeRepository.status),
    refetchInterval: (query) => {
      const repository = query.state.data

      if (
        !isRepositoryPublic(repository) ||
        isTerminalStatus(repository.status)
      ) {
        return false
      }

      return 1000
    },
  })
  const createRepositoryMutation = useMutation({
    mutationFn: RepositoriesService.createRepository,
    onSuccess: (repository) => {
      queryClient.setQueryData(
        ["repositories"],
        (current: { data: RepositoryPublic[]; count: number } | undefined) => {
          const currentRepositories = current?.data ?? []
          const nextRepositories = [
            repository,
            ...currentRepositories.filter((item) => item.id !== repository.id),
          ]

          return {
            data: nextRepositories,
            count: current?.count ? current.count + 1 : nextRepositories.length,
          }
        },
      )
      setActiveRepository(repository)
    },
  })
  const repositories = repositoriesQuery.data?.data ?? []

  useEffect(() => {
    if (!isRepositoryPublic(repositoryStatusQuery.data)) {
      return
    }

    const repository = repositoryStatusQuery.data
    queryClient.setQueryData(
      ["repositories"],
      (current: { data: RepositoryPublic[]; count: number } | undefined) => {
        const currentRepositories = current?.data ?? []

        return {
          data: currentRepositories.map((item) =>
            item.id === repository.id ? repository : item,
          ),
          count: current?.count ?? currentRepositories.length,
        }
      },
    )
    setActiveRepository(repository)
  }, [queryClient, repositoryStatusQuery.data])

  useEffect(() => {
    if (!activeRepository || activeRepository.status !== "ready") {
      setActiveSessionId(null)
      setChatMessages([])
      return
    }

    const storedSessionId = localStorage.getItem(
      getRepositorySessionStorageKey(activeRepository.id),
    )
    if (storedSessionId) {
      setActiveSessionId(storedSessionId)
      SessionsService.readRepositorySessionHistory({
        repositorySessionId: storedSessionId,
      }).then((history) => setChatMessages(toChatMessages(history.data)))
      return
    }

    createRepositorySession({
      repositoryId: activeRepository.id,
      setActiveSessionId,
      setChatMessages,
      setIsCreatingSession,
    })
  }, [activeRepository])

  return (
    <div className="flex min-h-[calc(100vh-12rem)] flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Copilot</h1>
      </header>

      <div className="grid flex-1 gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <section
          aria-label="Repository"
          className="flex min-h-72 flex-col gap-4 rounded-lg border bg-background p-4"
        >
          <div>
            <h2 className="text-base font-semibold">Repository</h2>
            <p className="text-sm text-muted-foreground">
              {activeRepository
                ? `${activeRepository.name} selected`
                : "No repository selected"}
            </p>
          </div>
          <RepositorySelector
            activeRepository={activeRepository}
            repositories={repositories}
            onSelectRepository={(repository) => {
              setActiveRepository(repository)
              setStageStatus(null)
              setStreamError(null)
            }}
          />
          <RepositoryCreationForm
            error={getErrorMessage(createRepositoryMutation.error)}
            isSubmitting={createRepositoryMutation.isPending}
            onCreate={(values) =>
              createRepositoryMutation.mutate({
                requestBody: values,
              })
            }
          />
        </section>

        <section
          aria-label="Chat"
          className="flex min-h-[32rem] flex-col rounded-lg border bg-background"
        >
          <div className="flex items-center justify-between gap-3 border-b p-4">
            <h2 className="text-base font-semibold">Chat</h2>
            <Button
              type="button"
              variant="outline"
              disabled={
                activeRepository?.status !== "ready" || isCreatingSession
              }
              onClick={() => {
                if (!activeRepository) {
                  return
                }
                setStageStatus(null)
                setStreamError(null)
                createRepositorySession({
                  repositoryId: activeRepository.id,
                  setActiveSessionId,
                  setChatMessages,
                  setIsCreatingSession,
                })
              }}
            >
              New Session
            </Button>
          </div>
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6 text-sm">
            {chatMessages.length === 0 ? (
              <div className="flex flex-1 items-center justify-center text-center text-muted-foreground">
                {getChatStatusMessage(activeRepository)}
              </div>
            ) : (
              chatMessages.map((message) => (
                <article
                  key={message.id}
                  className={
                    message.role === "user"
                      ? "self-end rounded-md bg-primary px-3 py-2 text-primary-foreground"
                      : "max-w-3xl"
                  }
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.citations.length > 0 ? (
                    <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                      {message.citations.map((citation) => (
                        <li key={citation.source}>{citation.source}</li>
                      ))}
                    </ul>
                  ) : null}
                </article>
              ))
            )}
            {stageStatus ? (
              <p className="text-xs text-muted-foreground">{stageStatus}</p>
            ) : null}
            {streamError ? (
              <p className="text-sm text-destructive">{streamError}</p>
            ) : null}
          </div>
          <form
            className="flex gap-3 border-t p-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!activeSessionId || !question.trim()) {
                return
              }
              submitQuestion({
                repositorySessionId: activeSessionId,
                question: question.trim(),
                setChatMessages,
                setQuestion,
                setStageStatus,
                setStreamError,
              })
            }}
          >
            <textarea
              aria-label="Ask about the selected repository"
              className="min-h-20 flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm disabled:bg-muted/30 disabled:text-muted-foreground"
              disabled={activeRepository?.status !== "ready"}
              placeholder="Ask about the selected repository"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <Button
              type="submit"
              disabled={
                activeRepository?.status !== "ready" ||
                !activeSessionId ||
                !question.trim()
              }
            >
              Ask
            </Button>
          </form>
        </section>
      </div>
    </div>
  )
}

function RepositoryCreationForm({
  error,
  isSubmitting,
  onCreate,
}: {
  error: string | null
  isSubmitting: boolean
  onCreate: (values: {
    repository_url: string
    token: string
    token_expiration_days: number
  }) => void
}) {
  const [repositoryUrl, setRepositoryUrl] = useState("")
  const [token, setToken] = useState("")
  const [tokenExpirationDays, setTokenExpirationDays] = useState("30")

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onCreate({
      repository_url: repositoryUrl,
      token,
      token_expiration_days: Number(tokenExpirationDays),
    })
  }

  return (
    <form className="mt-auto flex flex-col gap-3" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <Label htmlFor="repository-url">GitHub repository URL</Label>
        <Input
          id="repository-url"
          type="url"
          value={repositoryUrl}
          onChange={(event) => setRepositoryUrl(event.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="github-token">GitHub token</Label>
        <Input
          id="github-token"
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="token-expiration-days">Token expiration in days</Label>
        <Input
          id="token-expiration-days"
          type="number"
          min="1"
          value={tokenExpirationDays}
          onChange={(event) => setTokenExpirationDays(event.target.value)}
          required
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Registering..." : "Register repository"}
      </Button>
    </form>
  )
}

function RepositorySelector({
  activeRepository,
  repositories,
  onSelectRepository,
}: {
  activeRepository: RepositoryPublic | null
  repositories: RepositoryPublic[]
  onSelectRepository: (repository: RepositoryPublic) => void
}) {
  if (repositories.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        No repositories registered yet.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {repositories.map((repository) => (
        <Button
          key={repository.id}
          type="button"
          variant="outline"
          aria-pressed={activeRepository?.id === repository.id}
          className="h-auto justify-start p-3 text-left"
          onClick={() => onSelectRepository(repository)}
        >
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{repository.name}</span>
              <Badge variant="secondary">{repository.status}</Badge>
            </span>
            <span className="truncate text-xs text-muted-foreground">
              {repository.owner}/{repository.name}
            </span>
            {repository.status === "failed" && repository.failed_reason ? (
              <span className="text-xs text-destructive">
                {repository.failed_reason}
              </span>
            ) : null}
          </span>
        </Button>
      ))}
    </div>
  )
}

function getChatStatusMessage(repository: RepositoryPublic | null) {
  if (!repository) {
    return "Select a repository to start a Repository Session."
  }

  if (repository.status === "ready") {
    return `Chat is ready for ${repository.name}.`
  }

  if (repository.status === "failed") {
    return `Chat is disabled because repository processing failed: ${repository.failed_reason ?? "No failure reason was provided."}`
  }

  return `Chat is disabled while the repository is ${repository.status}.`
}

function isTerminalStatus(status: RepositoryPublic["status"]) {
  return status === "ready" || status === "failed"
}

function getRepositorySessionStorageKey(repositoryId: string) {
  return `repository-session:${repositoryId}`
}

function toChatMessages(history: SessionHistoryPublic[]): ChatMessage[] {
  return history.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations,
  }))
}

async function createRepositorySession({
  repositoryId,
  setActiveSessionId,
  setChatMessages,
  setIsCreatingSession,
}: {
  repositoryId: string
  setActiveSessionId: React.Dispatch<React.SetStateAction<string | null>>
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  setIsCreatingSession: React.Dispatch<React.SetStateAction<boolean>>
}) {
  setIsCreatingSession(true)
  try {
    const session = await SessionsService.createRepositorySession({
      requestBody: { repository_id: repositoryId },
    })
    const sessionId = session.id

    localStorage.setItem(
      getRepositorySessionStorageKey(repositoryId),
      sessionId,
    )
    setActiveSessionId(sessionId)
    setChatMessages([])

    const history = await SessionsService.readRepositorySessionHistory({
      repositorySessionId: sessionId,
    })
    setChatMessages(toChatMessages(history.data))
  } finally {
    setIsCreatingSession(false)
  }
}

async function submitQuestion({
  repositorySessionId,
  question,
  setChatMessages,
  setQuestion,
  setStageStatus,
  setStreamError,
}: {
  repositorySessionId: string
  question: string
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  setQuestion: React.Dispatch<React.SetStateAction<string>>
  setStageStatus: React.Dispatch<React.SetStateAction<string | null>>
  setStreamError: React.Dispatch<React.SetStateAction<string | null>>
}) {
  const assistantMessageId = crypto.randomUUID()

  setQuestion("")
  setStreamError(null)
  setStageStatus(null)
  setChatMessages((messages) => [
    ...messages,
    {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      citations: [],
    },
    {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      citations: [],
    },
  ])

  for await (const event of askRepositoryQuestionStream({
    repositorySessionId,
    question,
  })) {
    if (event.type === "stage") {
      setStageStatus(event.stage)
    }

    if (event.type === "token") {
      setChatMessages((messages) =>
        messages.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: `${message.content}${event.content}` }
            : message,
        ),
      )
    }

    if (event.type === "result") {
      setChatMessages((messages) =>
        messages.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: event.answer,
                citations: event.citations,
              }
            : message,
        ),
      )
    }

    if (event.type === "transport_error") {
      setStageStatus(null)
      setStreamError(event.message)
    }
  }
}

function getErrorMessage(error: unknown) {
  if (!error) {
    return null
  }

  if (
    typeof error === "object" &&
    "body" in error &&
    hasValidationDetails(error.body)
  ) {
    return error.body.detail.map((detail) => detail.msg).join(" ")
  }

  if (error instanceof Error) {
    return error.message
  }

  return "Repository registration failed."
}

function hasValidationDetails(
  body: unknown,
): body is { detail: Array<{ msg: string }> } {
  return (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    Array.isArray(body.detail) &&
    body.detail.every(
      (detail) =>
        typeof detail === "object" &&
        detail !== null &&
        "msg" in detail &&
        typeof detail.msg === "string",
    )
  )
}

function isRepositoryPublic(value: unknown): value is RepositoryPublic {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "name" in value &&
    typeof value.name === "string" &&
    "status" in value &&
    typeof value.status === "string" &&
    ["pending", "cloning", "indexing", "ready", "failed"].includes(value.status)
  )
}
