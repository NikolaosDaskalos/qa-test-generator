import { useMutation, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { type FormEvent, useState } from "react"
import type { RepositoryPublic } from "@/client"
import { RepositoriesService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getErrorMessage } from "@/lib/apiError"

export const Route = createFileRoute("/_layout/repositories/new")({
  component: RegisterRepository,
  head: () => ({
    meta: [{ title: "Add repository - AI Codebase Copilot" }],
  }),
})

function RegisterRepository() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [repositoryUrl, setRepositoryUrl] = useState("")
  const [token, setToken] = useState("")
  const [tokenExpirationDays, setTokenExpirationDays] = useState("")

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
      navigate({ to: "/", search: { selected: repository.id } })
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedExpiration = tokenExpirationDays.trim()
    createRepositoryMutation.mutate({
      requestBody: {
        repository_url: repositoryUrl,
        token,
        token_expiration_days:
          trimmedExpiration === "" ? null : Number(trimmedExpiration),
      },
    })
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Button asChild variant="ghost" size="sm" className="self-start px-2">
          <Link to="/">← Back</Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Add a repository</h1>
        <p className="text-sm text-muted-foreground">
          Connect a GitHub repository so the copilot can index it.
        </p>
      </header>

      <form
        className="flex flex-col gap-4 rounded-lg border bg-background p-6"
        onSubmit={handleSubmit}
      >
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
          <Label htmlFor="token-expiration-days">
            Token expiration in days
          </Label>
          <Input
            id="token-expiration-days"
            type="number"
            min="1"
            placeholder="Optional"
            value={tokenExpirationDays}
            onChange={(event) => setTokenExpirationDays(event.target.value)}
          />
        </div>
        {getErrorMessage(createRepositoryMutation.error) ? (
          <p className="text-sm text-destructive">
            {getErrorMessage(createRepositoryMutation.error)}
          </p>
        ) : null}
        <div className="flex gap-3">
          <Button type="submit" disabled={createRepositoryMutation.isPending}>
            {createRepositoryMutation.isPending
              ? "Registering..."
              : "Register repository"}
          </Button>
          <Button asChild variant="outline" type="button">
            <Link to="/">Cancel</Link>
          </Button>
        </div>
      </form>
    </div>
  )
}
