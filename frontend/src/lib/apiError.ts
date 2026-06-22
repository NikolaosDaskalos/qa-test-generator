export function getErrorMessage(error: unknown) {
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
