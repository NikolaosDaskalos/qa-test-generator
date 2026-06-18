import { Link } from "@tanstack/react-router"
import { Bot } from "lucide-react"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content = (
    <span className={cn("flex items-center gap-2", className)}>
      <Bot className="size-5 shrink-0" />
      <span
        className={cn(
          "font-semibold tracking-tight whitespace-nowrap",
          variant === "icon" && "hidden",
          variant === "responsive" && "group-data-[collapsible=icon]:hidden",
        )}
      >
        AI Codebase Copilot
      </span>
    </span>
  )

  if (!asLink) {
    return content
  }

  return (
    <Link to="/" aria-label="AI Codebase Copilot">
      {content}
    </Link>
  )
}
