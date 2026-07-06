import { useQuery } from "@tanstack/react-query"

import { CostsService } from "@/client"
import useAuth from "@/hooks/useAuth"
import { formatEstimatedCost } from "@/lib/cost"

// Shows the requesting user's rolled-up AI Cost total, and — for a superuser only —
// the global all-users total. A dimension with no recorded usage reads back a
// well-defined zero, so these render "$0.00" rather than nothing (ADR-0014).
const AiCostSummary = () => {
  const { user } = useAuth()

  const myCostQuery = useQuery({
    queryKey: ["my-cost"],
    queryFn: CostsService.readMyCost,
  })

  const allUsersCostQuery = useQuery({
    queryKey: ["all-users-cost"],
    queryFn: CostsService.readAllUsersCost,
    enabled: Boolean(user?.is_superuser),
  })

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">AI Cost</h3>
      <p className="text-sm text-muted-foreground">
        Estimated spend across your repositories.
      </p>
      <p
        data-testid="user-total-cost"
        className="py-2 text-sm text-muted-foreground"
      >
        Your estimated AI Cost:{" "}
        {formatEstimatedCost(myCostQuery.data?.cost ?? 0)}
      </p>
      {user?.is_superuser ? (
        <p
          data-testid="all-users-total-cost"
          className="py-2 text-sm text-muted-foreground"
        >
          All users&apos; estimated AI Cost:{" "}
          {formatEstimatedCost(allUsersCostQuery.data?.cost ?? 0)}
        </p>
      ) : null}
    </div>
  )
}

export default AiCostSummary
