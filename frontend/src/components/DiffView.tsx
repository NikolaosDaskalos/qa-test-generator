import { useMemo } from "react"

import { cn } from "@/lib/utils"

type LineKind = "add" | "del" | "context" | "meta"

type DiffLine = {
  kind: LineKind
  /** Old-file line number, when applicable. */
  oldNumber: number | null
  /** New-file line number, when applicable. */
  newNumber: number | null
  content: string
}

type DiffHunk = {
  header: string
  lines: DiffLine[]
}

type FileStatus = "added" | "deleted" | "renamed" | "modified"

type DiffFile = {
  /** Display path (new path, falling back to old path). */
  path: string
  oldPath: string | null
  status: FileStatus
  hunks: DiffHunk[]
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/

function stripPrefix(path: string): string {
  if (path === "/dev/null") return path
  // git diff prefixes paths with a/ and b/.
  return path.replace(/^[ab]\//, "")
}

function parseDiff(raw: string): DiffFile[] {
  const lines = raw.split("\n")
  const files: DiffFile[] = []
  let current: DiffFile | null = null
  let hunk: DiffHunk | null = null
  let oldNumber = 0
  let newNumber = 0

  const pushFile = () => {
    if (current) files.push(current)
  }

  for (const line of lines) {
    if (line.startsWith("diff --git")) {
      pushFile()
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/)
      const path = match ? match[2] : line.replace("diff --git ", "")
      current = {
        path,
        oldPath: match ? match[1] : null,
        status: "modified",
        hunks: [],
      }
      hunk = null
      continue
    }

    if (!current) {
      // Diff without a `diff --git` header (e.g. raw `--- / +++`). Start one.
      if (line.startsWith("--- ")) {
        current = {
          path: stripPrefix(line.slice(4).trim()),
          oldPath: stripPrefix(line.slice(4).trim()),
          status: "modified",
          hunks: [],
        }
        hunk = null
      }
      continue
    }

    if (line.startsWith("new file mode")) {
      current.status = "added"
      continue
    }
    if (line.startsWith("deleted file mode")) {
      current.status = "deleted"
      continue
    }
    if (line.startsWith("rename from ")) {
      current.oldPath = line.slice("rename from ".length).trim()
      current.status = "renamed"
      continue
    }
    if (line.startsWith("rename to ")) {
      current.path = line.slice("rename to ".length).trim()
      current.status = "renamed"
      continue
    }
    if (line.startsWith("--- ")) {
      const p = stripPrefix(line.slice(4).trim())
      if (p !== "/dev/null") current.oldPath = p
      continue
    }
    if (line.startsWith("+++ ")) {
      const p = stripPrefix(line.slice(4).trim())
      if (p !== "/dev/null") current.path = p
      continue
    }
    if (line.startsWith("index ") || line.startsWith("similarity index")) {
      continue
    }

    const hunkMatch = line.match(HUNK_RE)
    if (hunkMatch) {
      oldNumber = Number.parseInt(hunkMatch[1], 10)
      newNumber = Number.parseInt(hunkMatch[2], 10)
      hunk = { header: line, lines: [] }
      current.hunks.push(hunk)
      continue
    }

    if (!hunk) continue

    if (line.startsWith("\\")) {
      // "\ No newline at end of file" — attach as meta context.
      hunk.lines.push({
        kind: "meta",
        oldNumber: null,
        newNumber: null,
        content: line.slice(1).trim(),
      })
      continue
    }

    const marker = line[0]
    const content = line.slice(1)
    if (marker === "+") {
      hunk.lines.push({
        kind: "add",
        oldNumber: null,
        newNumber: newNumber++,
        content,
      })
    } else if (marker === "-") {
      hunk.lines.push({
        kind: "del",
        oldNumber: oldNumber++,
        newNumber: null,
        content,
      })
    } else {
      hunk.lines.push({
        kind: "context",
        oldNumber: oldNumber++,
        newNumber: newNumber++,
        content,
      })
    }
  }

  pushFile()
  return files
}

const STATUS_LABEL: Record<FileStatus, string> = {
  added: "added",
  deleted: "deleted",
  renamed: "renamed",
  modified: "modified",
}

const STATUS_CLASS: Record<FileStatus, string> = {
  added:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  deleted: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  renamed: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  modified: "bg-muted text-muted-foreground",
}

function countChanges(file: DiffFile): {
  additions: number
  deletions: number
} {
  let additions = 0
  let deletions = 0
  for (const hunk of file.hunks) {
    for (const line of hunk.lines) {
      if (line.kind === "add") additions++
      else if (line.kind === "del") deletions++
    }
  }
  return { additions, deletions }
}

function gutterText(value: number | null): string {
  return value === null ? "" : String(value)
}

function DiffFileBlock({ file }: { file: DiffFile }) {
  const { additions, deletions } = countChanges(file)
  const showRename = file.status === "renamed" && file.oldPath

  return (
    <div className="overflow-hidden rounded-md border bg-background">
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/50 px-3 py-2 text-xs">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 font-medium uppercase tracking-wide",
            STATUS_CLASS[file.status],
          )}
        >
          {STATUS_LABEL[file.status]}
        </span>
        <span className="font-mono font-medium">
          {showRename ? `${file.oldPath} → ${file.path}` : file.path}
        </span>
        <span className="ml-auto flex items-center gap-2 font-mono">
          {additions > 0 ? (
            <span className="text-emerald-600 dark:text-emerald-400">
              +{additions}
            </span>
          ) : null}
          {deletions > 0 ? (
            <span className="text-red-600 dark:text-red-400">-{deletions}</span>
          ) : null}
        </span>
      </div>

      {file.hunks.length === 0 ? (
        <div className="px-3 py-2 font-mono text-xs text-muted-foreground">
          No textual changes
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-xs leading-relaxed">
            <tbody>
              {file.hunks.map((hunk, hunkIndex) => (
                <HunkRows key={hunkIndex} hunk={hunk} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function HunkRows({ hunk }: { hunk: DiffHunk }) {
  return (
    <>
      <tr className="bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
        <td className="select-none px-2 text-right opacity-70" />
        <td className="select-none px-2 text-right opacity-70" />
        <td className="whitespace-pre px-3 py-0.5">{hunk.header}</td>
      </tr>
      {hunk.lines.map((line, index) => {
        if (line.kind === "meta") {
          return (
            <tr
              key={index}
              className="bg-muted/40 text-muted-foreground italic"
            >
              <td className="select-none px-2 text-right" />
              <td className="select-none px-2 text-right" />
              <td className="whitespace-pre-wrap px-3 py-0.5">
                {line.content}
              </td>
            </tr>
          )
        }

        const rowClass =
          line.kind === "add"
            ? "bg-emerald-50 dark:bg-emerald-950/40"
            : line.kind === "del"
              ? "bg-red-50 dark:bg-red-950/40"
              : ""
        const marker =
          line.kind === "add" ? "+" : line.kind === "del" ? "-" : " "
        const contentClass =
          line.kind === "add"
            ? "text-emerald-800 dark:text-emerald-200"
            : line.kind === "del"
              ? "text-red-800 dark:text-red-200"
              : "text-foreground"

        return (
          <tr key={index} className={rowClass}>
            <td className="w-[1%] select-none border-r px-2 text-right align-top text-muted-foreground">
              {gutterText(line.oldNumber)}
            </td>
            <td className="w-[1%] select-none border-r px-2 text-right align-top text-muted-foreground">
              {gutterText(line.newNumber)}
            </td>
            <td className={cn("whitespace-pre-wrap px-3 py-0.5", contentClass)}>
              <span className="select-none pr-2 opacity-60">{marker}</span>
              {line.content}
            </td>
          </tr>
        )
      })}
    </>
  )
}

export function DiffView({
  diff,
  className,
}: {
  diff: string
  className?: string
}) {
  const files = useMemo(() => parseDiff(diff), [diff])

  if (!diff.trim()) {
    return (
      <p className="text-xs text-muted-foreground italic">
        No changes to show.
      </p>
    )
  }

  if (files.length === 0) {
    // Couldn't parse as a unified diff — fall back to raw text.
    return (
      <pre
        className={cn(
          "max-w-full overflow-x-auto rounded-md border bg-muted p-3 text-xs",
          className,
        )}
      >
        {diff}
      </pre>
    )
  }

  return (
    <div className={cn("grid gap-3", className)}>
      {files.map((file, index) => (
        <DiffFileBlock key={`${file.path}:${index}`} file={file} />
      ))}
    </div>
  )
}
