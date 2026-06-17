import { createFileRoute } from "@tanstack/react-router"

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
              No repository selected
            </p>
          </div>
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            Repository list
          </div>
          <button
            type="button"
            className="mt-auto h-9 rounded-md border px-3 text-sm font-medium text-muted-foreground"
            disabled
          >
            New repository
          </button>
        </section>

        <section
          aria-label="Chat"
          className="flex min-h-[32rem] flex-col rounded-lg border bg-background"
        >
          <div className="border-b p-4">
            <h2 className="text-base font-semibold">Chat</h2>
          </div>
          <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-muted-foreground">
            Select a repository to start a Repository Session.
          </div>
          <div className="border-t p-4">
            <div className="flex min-h-11 items-center rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
              Ask about the selected repository
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
