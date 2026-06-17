import type { Citation } from "@/client"
import { OpenAPI } from "@/client"

export type AgentStreamEvent =
  | { type: "stage"; stage: string }
  | { type: "token"; content: string }
  | { type: "result"; answer: string; citations: Citation[] }
  | { type: "run_started"; coding_run_id: string }
  | { type: "review_result"; [key: string]: unknown }
  | { type: "patch_result"; [key: string]: unknown }
  | { type: "run_failure"; [key: string]: unknown }
  | { type: "run_approved"; [key: string]: unknown }
  | { type: "run_rejected"; [key: string]: unknown }
  | { type: "transport_error"; message: string }

export async function* askRepositoryQuestionStream({
  repositorySessionId,
  question,
}: {
  repositorySessionId: string
  question: string
}): AsyncGenerator<AgentStreamEvent> {
  try {
    const token = await resolveToken()
    const response = await fetch(
      `${OpenAPI.BASE}/api/v1/sessions/${repositorySessionId}/questions`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question }),
      },
    )

    if (!response.ok || !response.body) {
      yield {
        type: "transport_error",
        message: `Question stream failed with status ${response.status}.`,
      }
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ""

      for (const line of lines) {
        const event = parseSseLine(line)
        if (event) {
          yield event
        }
      }
    }

    const finalEvent = parseSseLine(buffer)
    if (finalEvent) {
      yield finalEvent
    }
  } catch (error) {
    yield {
      type: "transport_error",
      message:
        error instanceof Error
          ? error.message
          : "Question stream failed unexpectedly.",
    }
  }
}

async function resolveToken() {
  if (typeof OpenAPI.TOKEN === "function") {
    return OpenAPI.TOKEN({} as never)
  }

  return OpenAPI.TOKEN
}

function parseSseLine(line: string): AgentStreamEvent | null {
  if (!line.startsWith("data:")) {
    return null
  }

  const data = line.slice("data:".length).trim()
  if (!data || data === "[DONE]") {
    return null
  }

  return JSON.parse(data) as AgentStreamEvent
}
