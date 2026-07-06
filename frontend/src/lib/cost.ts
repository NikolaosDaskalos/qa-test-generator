// Presents an AI Cost figure as an estimated USD amount. AI Cost is always an
// *estimate* derived from token usage and a local price table, never a billed
// amount, so every surface renders it through this one formatter (ADR-0014).
export function formatEstimatedCost(cost: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(cost)
}
