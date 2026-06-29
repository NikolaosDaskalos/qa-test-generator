import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type {
  Citation,
  HumanDecisionRequest,
  RepositoryPublic,
  RepositorySessionPublic,
  ReviewFinding,
  SessionHistoryPublic,
} from "@/client"
import { RepositoriesService, SessionsService } from "@/client"
import { DiffView } from "@/components/DiffView"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import useCustomToast from "@/hooks/useCustomToast"
import {
  askRepositoryQuestionStream,
  decideReviewedPatchStream,
} from "@/lib/agentStream"
import { getErrorMessage } from "@/lib/apiError"

type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  citations: Citation[]
  codingRunId?: string
  review?: ReviewResultView
  decision?: RunDecisionView
  failure?: RunFailureView
  noChanges?: RunNoChangesView
}

type RunNoChangesView = {
  message: string
}

type ReviewResultView = {
  accepted: boolean
  score: number
  threshold: number
  findings: ReviewFinding[]
  diff: string
  disclaimer: string
}

type RunFailureView = {
  failedStage: string
  reason: string
}

type RunDecisionView =
  | {
      status: "approved"
      branch: string
      message: string
      pullRequestUrl: string
      diff: string
      disclaimer: string
    }
  | {
      status: "rejected"
      findings: ReviewFinding[]
      diff: string
      disclaimer: string
    }

export const Route = createFileRoute("/_layout/")({
  component: CopilotShell,
  validateSearch: (
    search: Record<string, unknown>,
  ): { repository?: string; selected?: string; session?: string } => ({
    repository:
      typeof search.repository === "string" ? search.repository : undefined,
    selected: typeof search.selected === "string" ? search.selected : undefined,
    session: typeof search.session === "string" ? search.session : undefined,
  }),
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
  const navigate = Route.useNavigate()
  const {
    repository: durableRepositoryId,
    selected: legacyRepositoryId,
    session: selectedSessionId,
  } = Route.useSearch()
  const selectedRepositoryId = durableRepositoryId ?? legacyRepositoryId
  const [activeRepository, setActiveRepository] =
    useState<RepositoryPublic | null>(null)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState("")
  const [stageStatus, setStageStatus] = useState<string[]>([])
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [pendingDecisionRunId, setPendingDecisionRunId] = useState<
    string | null
  >(null)
  const [credentialRepository, setCredentialRepository] =
    useState<RepositoryPublic | null>(null)
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
  const repositories = repositoriesQuery.data?.data ?? []
  const isRepositoryReady = activeRepository?.status === "ready"

  useEffect(() => {
    if (!selectedRepositoryId) {
      return
    }
    const requested = repositories.find(
      (repository) => repository.id === selectedRepositoryId,
    )
    if (requested) {
      setActiveRepository((current) =>
        current &&
        current.id === requested.id &&
        current.status === requested.status
          ? current
          : requested,
      )
    }
  }, [selectedRepositoryId, repositories])

  useEffect(() => {
    if (selectedRepositoryId || repositoriesQuery.isLoading) {
      return
    }

    const lastSession = readLastRepositorySession()
    if (!lastSession) {
      return
    }

    const requested = repositories.find(
      (repository) => repository.id === lastSession.repositoryId,
    )
    if (!requested) {
      localStorage.removeItem(getLastRepositorySessionStorageKey())
      return
    }

    setActiveRepository(requested)
    navigate({
      to: "/",
      search: {
        repository: lastSession.repositoryId,
        session: lastSession.sessionId,
      },
      replace: true,
    })
  }, [
    navigate,
    repositories,
    repositoriesQuery.isLoading,
    selectedRepositoryId,
  ])
  const sessionsQuery = useQuery({
    queryKey: ["sessions", activeRepository?.id],
    queryFn: () =>
      SessionsService.readRepositorySessions({
        repositoryId: activeRepository?.id ?? "",
      }),
    enabled: !!activeRepository && isRepositoryReady,
  })
  const sessions = sessionsQuery.data?.data ?? []

  async function handleSelectSession(sessionId: string) {
    if (!activeRepository || sessionId === activeSessionId) {
      return
    }
    setStageStatus([])
    setStreamError(null)
    setActiveSessionId(sessionId)
    setChatMessages([])
    localStorage.setItem(
      getRepositorySessionStorageKey(activeRepository.id),
      sessionId,
    )
    localStorage.setItem(
      getLastRepositorySessionStorageKey(),
      JSON.stringify({
        repositoryId: activeRepository.id,
        sessionId,
      }),
    )
    navigate({
      to: "/",
      search: { repository: activeRepository.id, session: sessionId },
    })
    const history = await SessionsService.readRepositorySessionHistory({
      repositorySessionId: sessionId,
    })
    setChatMessages(toChatMessages(history.data))
  }

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
    setActiveRepository((current) =>
      current &&
      current.id === repository.id &&
      current.status === repository.status
        ? current
        : repository,
    )
  }, [queryClient, repositoryStatusQuery.data])

  useEffect(() => {
    if (!activeRepository || activeRepository.status !== "ready") {
      setActiveSessionId((current) => (current === null ? current : null))
      setChatMessages((messages) => (messages.length === 0 ? messages : []))
      return
    }

    if (isCreatingSession) {
      return
    }

    if (sessionsQuery.isLoading) {
      return
    }

    const storedSessionId = localStorage.getItem(
      getRepositorySessionStorageKey(activeRepository.id),
    )
    const nextSessionId = selectedSessionId ?? storedSessionId
    if (nextSessionId) {
      if (activeSessionId === nextSessionId) {
        return
      }

      const sessionIsAccessible = sessions.some(
        (session) => session.id === nextSessionId,
      )
      if (!sessionIsAccessible) {
        if (storedSessionId === nextSessionId) {
          localStorage.removeItem(
            getRepositorySessionStorageKey(activeRepository.id),
          )
        }
        const lastSession = readLastRepositorySession()
        if (
          lastSession?.repositoryId === activeRepository.id &&
          lastSession.sessionId === nextSessionId
        ) {
          localStorage.removeItem(getLastRepositorySessionStorageKey())
        }
        setActiveSessionId(null)
        setChatMessages([])
        if (selectedSessionId) {
          navigate({
            to: "/",
            search: { repository: activeRepository.id },
            replace: true,
          })
        }
        return
      }

      localStorage.setItem(
        getRepositorySessionStorageKey(activeRepository.id),
        nextSessionId,
      )
      localStorage.setItem(
        getLastRepositorySessionStorageKey(),
        JSON.stringify({
          repositoryId: activeRepository.id,
          sessionId: nextSessionId,
        }),
      )
      setActiveSessionId(nextSessionId)
      if (!selectedSessionId) {
        navigate({
          to: "/",
          search: { repository: activeRepository.id, session: nextSessionId },
          replace: true,
        })
      }
      SessionsService.readRepositorySessionHistory({
        repositorySessionId: nextSessionId,
      }).then((history) => setChatMessages(toChatMessages(history.data)))
      return
    }

    setActiveSessionId(null)
    setChatMessages([])
  }, [
    activeRepository,
    activeSessionId,
    isCreatingSession,
    navigate,
    selectedSessionId,
    sessions,
    sessionsQuery.isLoading,
  ])

  if (!repositoriesQuery.isLoading && repositories.length === 0) {
    return <RepositoryEmptyState />
  }

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
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold">Repositories</h2>
              <p className="text-sm text-muted-foreground">
                {activeRepository
                  ? `${activeRepository.name} selected`
                  : "No repository selected"}
              </p>
            </div>
            <Button
              asChild
              variant="outline"
              size="icon"
              className="size-8 shrink-0"
            >
              <Link to="/repositories/new" aria-label="Add repository">
                <Plus className="size-4" />
              </Link>
            </Button>
          </div>
          <RepositorySelector
            activeRepository={activeRepository}
            activeSessionId={activeSessionId}
            isCreatingSession={isCreatingSession}
            isSessionsLoading={sessionsQuery.isLoading}
            repositories={repositories}
            sessions={sessions}
            onCreateSession={() => {
              if (!activeRepository) {
                return
              }
              setStageStatus([])
              setStreamError(null)
              createRepositorySession({
                repositoryId: activeRepository.id,
                navigate,
                queryClient,
                setActiveSessionId,
                setChatMessages,
                setIsCreatingSession,
              })
            }}
            onSelectRepository={(repository) => {
              setActiveRepository(repository)
              setStageStatus([])
              setStreamError(null)
              navigate({
                to: "/",
                search: { repository: repository.id },
              })
            }}
            onSelectSession={handleSelectSession}
          />
        </section>

        {activeRepository && activeRepository.status !== "ready" ? (
          <RepositoryDetails
            repository={activeRepository}
            onUpdateToken={() => setCredentialRepository(activeRepository)}
          />
        ) : (
          <section
            aria-label="Chat"
            className="flex min-h-[32rem] flex-col rounded-lg border bg-background"
          >
            <div className="flex items-center justify-between gap-3 border-b p-4">
              <h2 className="text-base font-semibold">Chat</h2>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setCredentialRepository(activeRepository)}
                >
                  Update token
                </Button>
              </div>
            </div>
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6 text-sm">
              {chatMessages.length === 0 ? (
                <div className="flex flex-1 items-center justify-center text-center text-muted-foreground">
                  {activeSessionId && activeRepository?.status === "ready"
                    ? `Chat is ready for ${activeRepository.name}.`
                    : getChatStatusMessage(activeRepository)}
                </div>
              ) : (
                chatMessages.map((message) => (
                  <article
                    key={message.id}
                    className={
                      message.role === "user"
                        ? "max-w-[80%] self-end rounded-2xl bg-primary px-4 py-2 text-primary-foreground"
                        : "max-w-3xl self-start rounded-2xl border bg-muted px-4 py-3"
                    }
                  >
                    {message.role === "assistant" ? (
                      <MarkdownContent content={message.content} />
                    ) : (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    )}
                    {message.codingRunId && activeSessionId ? (
                      <RunDetails
                        repositorySessionId={activeSessionId}
                        codingRunId={message.codingRunId}
                      />
                    ) : null}
                    {message.review ? (
                      <ReviewResultSummary
                        isPending={pendingDecisionRunId === message.codingRunId}
                        message={message}
                        review={message.review}
                        onDecision={(decision) => {
                          if (!activeSessionId || !activeRepository) {
                            return
                          }
                          submitDecision({
                            queryClient,
                            repositoryId: activeRepository.id,
                            repositorySessionId: activeSessionId,
                            decision,
                            setChatMessages,
                            setPendingDecisionRunId,
                            setStageStatus,
                            setStreamError,
                          })
                        }}
                      />
                    ) : null}
                    {message.decision ? (
                      <RunDecisionSummary decision={message.decision} />
                    ) : null}
                    {message.failure ? (
                      <RunFailureSummary failure={message.failure} />
                    ) : null}
                    {message.noChanges ? (
                      <RunNoChangesSummary noChanges={message.noChanges} />
                    ) : null}
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
              {stageStatus.length > 0 ? (
                <ol
                  data-testid="stage-progress"
                  className="flex flex-wrap gap-2 text-xs text-muted-foreground"
                >
                  {stageStatus.map((stage) => (
                    <li key={stage}>{stage}</li>
                  ))}
                </ol>
              ) : null}
              {streamError ? (
                <p className="text-sm text-destructive">{streamError}</p>
              ) : null}
            </div>
            <form
              className="flex gap-3 border-t p-4"
              onSubmit={(event) => {
                event.preventDefault()
                if (!activeSessionId || !activeRepository || !question.trim()) {
                  return
                }
                submitQuestion({
                  queryClient,
                  repositoryId: activeRepository.id,
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
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
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
        )}
      </div>

      {credentialRepository ? (
        <UpdateCredentialDialog
          repository={credentialRepository}
          onClose={() => setCredentialRepository(null)}
        />
      ) : null}
    </div>
  )
}

function UpdateCredentialDialog({
  repository,
  onClose,
}: {
  repository: RepositoryPublic
  onClose: () => void
}) {
  const { showSuccessToast } = useCustomToast()
  const [token, setToken] = useState("")
  const [tokenExpirationDays, setTokenExpirationDays] = useState("")

  const updateCredentialMutation = useMutation({
    mutationFn: RepositoriesService.updateRepository,
    onSuccess: () => {
      showSuccessToast("Repository token updated.")
      onClose()
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedExpiration = tokenExpirationDays.trim()
    updateCredentialMutation.mutate({
      repositoryId: repository.id,
      requestBody: {
        token,
        token_expiration_days:
          trimmedExpiration === "" ? null : Number(trimmedExpiration),
      },
    })
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Update repository token</DialogTitle>
          <DialogDescription>
            Replace the GitHub credential for {repository.name}. This does not
            change the repository's processing status.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-2">
            <Label htmlFor="update-github-token">GitHub token</Label>
            <Input
              id="update-github-token"
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="update-token-expiration-days">
              Token expiration in days
            </Label>
            <Input
              id="update-token-expiration-days"
              type="number"
              min="1"
              placeholder="Optional"
              value={tokenExpirationDays}
              onChange={(event) => setTokenExpirationDays(event.target.value)}
            />
          </div>
          {getErrorMessage(updateCredentialMutation.error) ? (
            <p className="text-sm text-destructive">
              {getErrorMessage(updateCredentialMutation.error)}
            </p>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" type="button">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={updateCredentialMutation.isPending}>
              {updateCredentialMutation.isPending ? "Saving..." : "Save token"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RepositoryDetails({
  repository,
  onUpdateToken,
}: {
  repository: RepositoryPublic
  onUpdateToken: () => void
}) {
  return (
    <section
      aria-label="Repository details"
      className="flex min-h-[32rem] flex-col gap-4 rounded-lg border bg-background p-6"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 className="text-base font-semibold">{repository.name}</h2>
          <p className="text-sm text-muted-foreground">
            {repository.owner}/{repository.name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{repository.status}</Badge>
          <Button type="button" variant="ghost" onClick={onUpdateToken}>
            Update token
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        {getChatStatusMessage(repository)}
      </p>
      {repository.status === "failed" ? (
        <p className="text-sm text-destructive">
          {repository.failed_reason ?? "No failure reason was provided."}
        </p>
      ) : null}
    </section>
  )
}

function RepositoryEmptyState() {
  return (
    <div className="flex min-h-[calc(100vh-12rem)] flex-col items-center justify-center gap-4 text-center">
      <div className="grid gap-2">
        <h1 className="text-2xl font-bold tracking-tight">
          Connect a repository to get started
        </h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Register a GitHub repository to ask grounded questions and generate
          tests for its code.
        </p>
      </div>
      <Button asChild>
        <Link to="/repositories/new">Add your code repository</Link>
      </Button>
    </div>
  )
}

function RepositorySelector({
  activeRepository,
  activeSessionId,
  isCreatingSession,
  isSessionsLoading,
  sessions,
  repositories,
  onCreateSession,
  onSelectRepository,
  onSelectSession,
}: {
  activeRepository: RepositoryPublic | null
  activeSessionId: string | null
  isCreatingSession: boolean
  isSessionsLoading: boolean
  sessions: RepositorySessionPublic[]
  repositories: RepositoryPublic[]
  onCreateSession: () => void
  onSelectRepository: (repository: RepositoryPublic) => void
  onSelectSession: (sessionId: string) => void
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
      {repositories.map((repository) => {
        const isExpanded = activeRepository?.id === repository.id

        return (
          <div key={repository.id} className="grid gap-2">
            <Button
              type="button"
              variant="outline"
              aria-expanded={isExpanded}
              aria-pressed={isExpanded}
              className="h-auto justify-start p-3 text-left"
              onClick={() => onSelectRepository(repository)}
            >
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">
                    {repository.name}
                  </span>
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
            {isExpanded && repository.status === "ready" ? (
              <SessionList
                activeSessionId={activeSessionId}
                isCreatingSession={isCreatingSession}
                isLoading={isSessionsLoading}
                sessions={sessions}
                onCreateSession={onCreateSession}
                onSelectSession={onSelectSession}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function SessionList({
  sessions,
  activeSessionId,
  isCreatingSession,
  isLoading,
  onCreateSession,
  onSelectSession,
}: {
  sessions: RepositorySessionPublic[]
  activeSessionId: string | null
  isCreatingSession: boolean
  isLoading: boolean
  onCreateSession: () => void
  onSelectSession: (sessionId: string) => void
}) {
  return (
    <div className="ml-3 flex flex-col gap-2 border-l pl-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Sessions</h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isCreatingSession}
          onClick={onCreateSession}
        >
          New Session
        </Button>
      </div>
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading sessions...</p>
      ) : sessions.length === 0 ? (
        <p className="text-xs text-muted-foreground">No sessions yet.</p>
      ) : (
        <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
          {sessions.map((session) => (
            <li key={session.id}>
              <Button
                type="button"
                variant="ghost"
                aria-pressed={session.id === activeSessionId}
                className="h-auto w-full justify-start p-2 text-left aria-pressed:bg-muted"
                onClick={() => onSelectSession(session.id)}
              >
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-sm">{session.title}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {new Date(session.updated_at).toLocaleString()}
                  </span>
                </span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ReviewResultSummary({
  isPending,
  message,
  onDecision,
  review,
}: {
  isPending: boolean
  message: ChatMessage
  onDecision: (decision: HumanDecisionRequest) => void
  review: ReviewResultView
}) {
  const [feedback, setFeedback] = useState("")
  const canDecide =
    review.accepted &&
    !message.decision &&
    typeof message.codingRunId === "string"

  return (
    <div className="mt-3 grid gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant={review.accepted ? "default" : "secondary"}>
          {review.accepted ? "Accepted" : "Rejected"}
        </Badge>
        <span className="text-muted-foreground">
          Score {review.score}/10; threshold {review.threshold}
        </span>
      </div>
      {review.findings.length > 0 ? (
        <ul className="space-y-1 text-sm">
          {review.findings.map((finding) => (
            <li key={`${finding.category}:${finding.detail}`}>
              <span className="font-medium">{finding.category}: </span>
              {finding.detail}
            </li>
          ))}
        </ul>
      ) : null}
      <DiffView diff={review.diff} />
      <p className="text-xs text-muted-foreground">{review.disclaimer}</p>
      {canDecide ? (
        <div className="grid gap-2">
          <p className="text-sm font-medium">Awaiting the owner's decision.</p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              disabled={isPending}
              onClick={() =>
                onDecision({
                  coding_run_id: message.codingRunId ?? "",
                  approved: true,
                  feedback: "",
                })
              }
            >
              Approve
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={isPending}
              onClick={() =>
                onDecision({
                  coding_run_id: message.codingRunId ?? "",
                  approved: false,
                  feedback,
                })
              }
            >
              Reject
            </Button>
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`reject-feedback-${message.id}`}>
              Reject feedback
            </Label>
            <textarea
              id={`reject-feedback-${message.id}`}
              aria-label="Reject feedback"
              className="min-h-16 resize-none rounded-md border bg-background px-3 py-2 text-sm disabled:bg-muted/30 disabled:text-muted-foreground"
              disabled={isPending}
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function RunDecisionSummary({ decision }: { decision: RunDecisionView }) {
  return (
    <div className="mt-3 grid gap-3">
      {decision.status === "approved" ? (
        <>
          <p className="text-sm font-medium">Approved and pushed</p>
          {decision.message ? (
            <p className="text-sm text-muted-foreground">{decision.message}</p>
          ) : null}
          <p className="text-sm text-muted-foreground">
            Branch {decision.branch}
          </p>
          {decision.pullRequestUrl ? (
            <a
              className="text-sm text-primary underline"
              href={decision.pullRequestUrl}
              target="_blank"
              rel="noreferrer"
            >
              View Pull Request
            </a>
          ) : null}
          <DiffView diff={decision.diff} />
        </>
      ) : (
        <>
          <p className="text-sm font-medium">Rejected and discarded</p>
          {decision.findings.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {decision.findings.map((finding) => (
                <li key={`${finding.category}:${finding.detail}`}>
                  <span className="font-medium">{finding.category}: </span>
                  {finding.detail}
                </li>
              ))}
            </ul>
          ) : null}
          <DiffView diff={decision.diff} />
        </>
      )}
      <p className="text-xs text-muted-foreground">{decision.disclaimer}</p>
    </div>
  )
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed [&_a]:text-primary [&_a]:underline [&_code]:rounded [&_code]:bg-muted-foreground/15 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:my-1 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:bg-background [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function RunFailureSummary({ failure }: { failure: RunFailureView }) {
  return (
    <div className="mt-3 grid gap-1 text-sm">
      <p className="font-medium">Run failed during {failure.failedStage}.</p>
      <p>{failure.reason}</p>
    </div>
  )
}

function RunNoChangesSummary({ noChanges }: { noChanges: RunNoChangesView }) {
  return (
    <div className="mt-3 grid gap-1 text-sm">
      <p className="font-medium">No new tests were generated.</p>
      <p>{noChanges.message}</p>
    </div>
  )
}

function RunDetails({
  repositorySessionId,
  codingRunId,
}: {
  repositorySessionId: string
  codingRunId: string
}) {
  const [expanded, setExpanded] = useState(false)
  const runQuery = useQuery({
    queryKey: ["coding-run", repositorySessionId, codingRunId],
    queryFn: () =>
      SessionsService.readCodingRun({ repositorySessionId, codingRunId }),
    enabled: expanded,
  })
  const patchQuery = useQuery({
    queryKey: ["coding-run-patch", repositorySessionId, codingRunId],
    queryFn: () =>
      SessionsService.readCodingRunPatch({ repositorySessionId, codingRunId }),
    enabled: expanded,
  })

  const run = runQuery.data
  const patch = patchQuery.data
  const isLoading = runQuery.isLoading || patchQuery.isLoading
  const error = runQuery.error ?? patchQuery.error

  return (
    <div className="mt-3 grid gap-2 text-xs">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span>Coding Run {codingRunId}</span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-auto px-2 py-1 text-xs"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Hide run details" : "View run details"}
        </Button>
      </div>
      {expanded ? (
        isLoading ? (
          <p className="text-muted-foreground">Loading run details...</p>
        ) : error ? (
          <p className="text-destructive">
            {getErrorMessage(error) ?? "Failed to load run details."}
          </p>
        ) : run ? (
          <div className="grid gap-2 rounded-md border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{run.status}</Badge>
              {run.failed_stage ? (
                <span className="text-muted-foreground">
                  Failed at {run.failed_stage}
                </span>
              ) : null}
            </div>
            {run.failure_reason ? (
              <p className="text-destructive">{run.failure_reason}</p>
            ) : null}
            {run.pull_request_url ? (
              <a
                className="text-primary underline"
                href={run.pull_request_url}
                target="_blank"
                rel="noreferrer"
              >
                View Pull Request
              </a>
            ) : null}
            {run.review_findings && run.review_findings.length > 0 ? (
              <ul className="space-y-1">
                {run.review_findings.map((finding) => (
                  <li key={`${finding.category}:${finding.detail}`}>
                    <span className="font-medium">{finding.category}: </span>
                    {finding.detail}
                  </li>
                ))}
              </ul>
            ) : null}
            {patch?.diff ? (
              <DiffView diff={patch.diff} />
            ) : run.diff ? (
              <DiffView diff={run.diff} />
            ) : null}
            {patch?.generated_files && patch.generated_files.length > 0 ? (
              <div className="grid gap-1">
                <p className="font-medium">Generated files</p>
                <ul className="space-y-1">
                  {patch.generated_files.map((file) => (
                    <li key={file.path} className="text-muted-foreground">
                      {file.path}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {patch?.external_references &&
            patch.external_references.length > 0 ? (
              <div className="grid gap-1">
                <p className="font-medium">External references</p>
                <ul className="space-y-1">
                  {patch.external_references.map((reference) => (
                    <li key={reference.url}>
                      <a
                        className="text-primary underline"
                        href={reference.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {reference.title || reference.url}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {run.disclaimer ? (
              <p className="text-muted-foreground">{run.disclaimer}</p>
            ) : null}
          </div>
        ) : null
      ) : null}
    </div>
  )
}

function getChatStatusMessage(repository: RepositoryPublic | null) {
  if (!repository) {
    return "Select a repository to start a Repository Session."
  }

  if (repository.status === "ready") {
    return "Start a new session"
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

function getLastRepositorySessionStorageKey() {
  return "repository-session:last"
}

function readLastRepositorySession(): {
  repositoryId: string
  sessionId: string
} | null {
  const value = localStorage.getItem(getLastRepositorySessionStorageKey())
  if (!value) {
    return null
  }

  try {
    const parsed = JSON.parse(value) as {
      repositoryId?: unknown
      sessionId?: unknown
    }

    if (
      typeof parsed.repositoryId === "string" &&
      typeof parsed.sessionId === "string"
    ) {
      return {
        repositoryId: parsed.repositoryId,
        sessionId: parsed.sessionId,
      }
    }
  } catch {
    localStorage.removeItem(getLastRepositorySessionStorageKey())
  }

  return null
}

function toChatMessages(history: SessionHistoryPublic[]): ChatMessage[] {
  return history.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations,
    // Restore the link to the durable Coding Run so its card is reconstructed from the run on reload.
    codingRunId: message.coding_run_id ?? undefined,
  }))
}

async function createRepositorySession({
  navigate,
  repositoryId,
  queryClient,
  setActiveSessionId,
  setChatMessages,
  setIsCreatingSession,
}: {
  navigate: ReturnType<typeof Route.useNavigate>
  repositoryId: string
  queryClient: ReturnType<typeof useQueryClient>
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
    localStorage.setItem(
      getLastRepositorySessionStorageKey(),
      JSON.stringify({
        repositoryId,
        sessionId,
      }),
    )
    setActiveSessionId(sessionId)
    setChatMessages([])
    navigate({
      to: "/",
      search: { repository: repositoryId, session: sessionId },
    })

    const history = await SessionsService.readRepositorySessionHistory({
      repositorySessionId: sessionId,
    })
    setChatMessages(toChatMessages(history.data))
    queryClient.invalidateQueries({ queryKey: ["sessions", repositoryId] })
  } finally {
    setIsCreatingSession(false)
  }
}

async function submitQuestion({
  queryClient,
  repositoryId,
  repositorySessionId,
  question,
  setChatMessages,
  setQuestion,
  setStageStatus,
  setStreamError,
}: {
  queryClient: ReturnType<typeof useQueryClient>
  repositoryId: string
  repositorySessionId: string
  question: string
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  setQuestion: React.Dispatch<React.SetStateAction<string>>
  setStageStatus: React.Dispatch<React.SetStateAction<string[]>>
  setStreamError: React.Dispatch<React.SetStateAction<string | null>>
}) {
  const assistantMessageId = crypto.randomUUID()

  setQuestion("")
  setStreamError(null)
  setStageStatus([])
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

  try {
    for await (const event of askRepositoryQuestionStream({
      repositorySessionId,
      question,
    })) {
      if (event.type === "stage") {
        setStageStatus((stages) =>
          stages.includes(event.stage) ? stages : [...stages, event.stage],
        )
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
        setStageStatus([])
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

      if (event.type === "run_started") {
        setChatMessages((messages) =>
          messages.map((message) =>
            message.id === assistantMessageId
              ? { ...message, codingRunId: event.coding_run_id }
              : message,
          ),
        )
      }

      if (event.type === "review_result" && isReviewResultEvent(event)) {
        setStageStatus([])
        setChatMessages((messages) =>
          messages.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  codingRunId: event.coding_run_id,
                  review: {
                    accepted: event.accepted,
                    score: event.score,
                    threshold: event.threshold,
                    findings: event.findings,
                    diff: event.diff,
                    disclaimer: event.disclaimer,
                  },
                }
              : message,
          ),
        )
      }

      if (event.type === "run_failure" && isRunFailureEvent(event)) {
        setStageStatus([])
        setChatMessages((messages) =>
          messages.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  codingRunId: event.coding_run_id ?? undefined,
                  failure: {
                    failedStage: event.failed_stage,
                    reason: event.reason,
                  },
                }
              : message,
          ),
        )
      }

      if (event.type === "run_no_changes") {
        setStageStatus([])
        setChatMessages((messages) =>
          messages.map((message) =>
            message.id === assistantMessageId
              ? {
                  ...message,
                  codingRunId: event.coding_run_id,
                  noChanges: {
                    message: event.message,
                  },
                }
              : message,
          ),
        )
      }

      if (event.type === "transport_error") {
        setStageStatus([])
        setStreamError(event.message)
      }
    }
  } finally {
    queryClient.invalidateQueries({ queryKey: ["sessions", repositoryId] })
  }
}

async function submitDecision({
  queryClient,
  repositoryId,
  repositorySessionId,
  decision,
  setChatMessages,
  setPendingDecisionRunId,
  setStageStatus,
  setStreamError,
}: {
  queryClient: ReturnType<typeof useQueryClient>
  repositoryId: string
  repositorySessionId: string
  decision: HumanDecisionRequest
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  setPendingDecisionRunId: React.Dispatch<React.SetStateAction<string | null>>
  setStageStatus: React.Dispatch<React.SetStateAction<string[]>>
  setStreamError: React.Dispatch<React.SetStateAction<string | null>>
}) {
  setStreamError(null)
  setStageStatus([])
  setPendingDecisionRunId(decision.coding_run_id)

  try {
    for await (const event of decideReviewedPatchStream({
      repositorySessionId,
      decision,
    })) {
      if (event.type === "stage") {
        setStageStatus((stages) =>
          stages.includes(event.stage) ? stages : [...stages, event.stage],
        )
      }

      if (event.type === "run_approved" && isRunApprovedEvent(event)) {
        setStageStatus([])
        setChatMessages((messages) =>
          messages.map((message) =>
            message.codingRunId === event.coding_run_id
              ? {
                  ...message,
                  decision: {
                    status: "approved",
                    branch: event.branch,
                    message: event.message ?? "",
                    pullRequestUrl: event.pull_request_url ?? "",
                    diff: event.diff,
                    disclaimer: event.disclaimer,
                  },
                }
              : message,
          ),
        )
      }

      if (event.type === "run_rejected" && isRunRejectedEvent(event)) {
        setStageStatus([])
        setChatMessages((messages) =>
          messages.map((message) =>
            message.codingRunId === event.coding_run_id
              ? {
                  ...message,
                  decision: {
                    status: "rejected",
                    findings: event.findings,
                    diff: event.diff,
                    disclaimer: event.disclaimer,
                  },
                }
              : message,
          ),
        )
      }

      if (event.type === "transport_error") {
        setStageStatus([])
        setStreamError(event.message)
      }
    }
  } finally {
    queryClient.invalidateQueries({ queryKey: ["sessions", repositoryId] })
    setPendingDecisionRunId(null)
  }
}

function isReviewResultEvent(event: { [key: string]: unknown }): event is {
  coding_run_id: string
  accepted: boolean
  score: number
  threshold: number
  findings: ReviewFinding[]
  diff: string
  disclaimer: string
} {
  return (
    typeof event.coding_run_id === "string" &&
    typeof event.accepted === "boolean" &&
    typeof event.score === "number" &&
    typeof event.threshold === "number" &&
    Array.isArray(event.findings) &&
    event.findings.every(isReviewFinding) &&
    typeof event.diff === "string" &&
    typeof event.disclaimer === "string"
  )
}

function isRunApprovedEvent(event: { [key: string]: unknown }): event is {
  coding_run_id: string
  branch: string
  message?: string
  pull_request_url?: string
  diff: string
  disclaimer: string
} {
  return (
    typeof event.coding_run_id === "string" &&
    typeof event.branch === "string" &&
    typeof event.diff === "string" &&
    typeof event.disclaimer === "string"
  )
}

function isRunRejectedEvent(event: { [key: string]: unknown }): event is {
  coding_run_id: string
  findings: ReviewFinding[]
  diff: string
  disclaimer: string
} {
  return (
    typeof event.coding_run_id === "string" &&
    Array.isArray(event.findings) &&
    event.findings.every(isReviewFinding) &&
    typeof event.diff === "string" &&
    typeof event.disclaimer === "string"
  )
}

function isRunFailureEvent(event: { [key: string]: unknown }): event is {
  coding_run_id: string | null
  failed_stage: string
  reason: string
} {
  return (
    (typeof event.coding_run_id === "string" ||
      event.coding_run_id === null ||
      event.coding_run_id === undefined) &&
    typeof event.failed_stage === "string" &&
    typeof event.reason === "string"
  )
}

function isReviewFinding(value: unknown): value is ReviewFinding {
  return (
    typeof value === "object" &&
    value !== null &&
    "category" in value &&
    typeof value.category === "string" &&
    "detail" in value &&
    typeof value.detail === "string"
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
