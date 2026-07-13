import type { AiCostRollupPublic } from "@/client"
import { formatEstimatedCost } from "@/lib/cost"

// Shared presentation for a rolled-up AI Cost total (session, Repository, or user).
// Unlike a per-turn card, a rollup always renders — a dimension with no recorded usage
// reads back a well-defined zero, so "$0.00" is a meaningful running total, not an error.
export function RollupCostLabel({
  label,
  testId,
  cost,
}: {
  label: string
  testId: string
  cost: AiCostRollupPublic | undefined
}) {
  return (
    <p data-testid={testId} className="text-xs text-muted-foreground">
      {label}: {formatEstimatedCost(cost?.cost ?? 0)}
    </p>
  )
}
