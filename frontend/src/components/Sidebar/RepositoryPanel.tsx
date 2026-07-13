import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useSearch } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { useState } from "react"

import type { RepositoryPublic, RepositorySessionPublic } from "@/client"
import { CostsService, RepositoriesService, SessionsService } from "@/client"
import { RollupCostLabel } from "@/components/Common/RollupCostLabel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SidebarGroup, SidebarGroupContent } from "@/components/ui/sidebar"

// The Repository/Session browser lives in the app sidebar so the chat column can
// take the full main area. Selection is URL-driven: the panel only navigates with
// the repository/session search params and the Copilot shell's URL-sync effect
// persists the choice and loads history.
export function RepositoryPanel() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const {
    repository: durableRepositoryId,
    selected: legacyRepositoryId,
    session: activeSessionId,
  } = useSearch({ strict: false })
  const selectedRepositoryId = durableRepositoryId ?? legacyRepositoryId
  const [isCreatingSession, setIsCreatingSession] = useState(false)

  const repositoriesQuery = useQuery({
    queryKey: ["repositories"],
    queryFn: () => RepositoriesService.readRepositories({}),
  })
  const repositories = repositoriesQuery.data?.data ?? []
  const activeRepository =
    repositories.find((repository) => repository.id === selectedRepositoryId) ??
    null

  const sessionsQuery = useQuery({
    queryKey: ["sessions", activeRepository?.id],
    queryFn: () =>
      SessionsService.readRepositorySessions({
        repositoryId: activeRepository?.id ?? "",
      }),
    enabled: !!activeRepository && activeRepository.status === "ready",
  })
  const sessions = sessionsQuery.data?.data ?? []

  async function handleCreateSession(repository: RepositoryPublic) {
    setIsCreatingSession(true)
    try {
      const session = await SessionsService.createRepositorySession({
        requestBody: { repository_id: repository.id },
      })
      // Seed the shared sessions cache so the shell's URL-sync effect sees the
      // new session as accessible before the server refetch lands.
      queryClient.setQueryData(
        ["sessions", repository.id],
        (
          current:
            | { data: RepositorySessionPublic[]; count: number }
            | undefined,
        ) => ({
          data: [session, ...(current?.data ?? [])],
          count: (current?.count ?? 0) + 1,
        }),
      )
      navigate({
        to: "/",
        search: { repository: repository.id, session: session.id },
      })
      queryClient.invalidateQueries({ queryKey: ["sessions", repository.id] })
    } finally {
      setIsCreatingSession(false)
    }
  }

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupContent>
        <section
          aria-label="Repository"
          className="flex min-w-0 flex-col gap-4 p-2"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold">Repositories</h2>
              <p className="text-sm text-muted-foreground">
                {activeRepository
                  ? `${activeRepository.name} selected`
                  : "No repository selected"}
              </p>
              {activeRepository ? (
                <RepositoryTotalCost repositoryId={activeRepository.id} />
              ) : null}
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
            activeSessionId={activeSessionId ?? null}
            isCreatingSession={isCreatingSession}
            isSessionsLoading={sessionsQuery.isLoading}
            repositories={repositories}
            sessions={sessions}
            onCreateSession={() => {
              if (!activeRepository) {
                return
              }
              handleCreateSession(activeRepository)
            }}
            onSelectRepository={(repository) => {
              navigate({
                to: "/",
                search: { repository: repository.id },
              })
            }}
            onSelectSession={(sessionId) => {
              if (!activeRepository || sessionId === activeSessionId) {
                return
              }
              navigate({
                to: "/",
                search: { repository: activeRepository.id, session: sessionId },
              })
            }}
          />
        </section>
      </SidebarGroupContent>
    </SidebarGroup>
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
    <div className="flex min-w-0 flex-col gap-2">
      {repositories.map((repository) => {
        const isExpanded = activeRepository?.id === repository.id

        return (
          <div key={repository.id} className="grid min-w-0 gap-2">
            <Button
              type="button"
              variant="outline"
              aria-expanded={isExpanded}
              aria-pressed={isExpanded}
              className="h-auto w-full min-w-0 justify-start p-3 text-left"
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
    <div className="ml-3 flex min-w-0 flex-col gap-2 border-l pl-3">
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
        <ul className="flex max-h-48 min-w-0 flex-col gap-1 overflow-y-auto">
          {sessions.map((session) => (
            <li key={session.id} className="min-w-0">
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

// Reads a Repository's AI Cost total across all its sessions off the persisted Usage
// Records, shown in the repository panel while the Repository is selected.
function RepositoryTotalCost({ repositoryId }: { repositoryId: string }) {
  const costQuery = useQuery({
    queryKey: ["repository-cost", repositoryId],
    queryFn: () => CostsService.readRepositoryCost({ repositoryId }),
  })

  return (
    <RollupCostLabel
      label="Est. Repository AI Cost"
      testId="repository-total-cost"
      cost={costQuery.data}
    />
  )
}
