/** Credit balances retain four decimal places in cents (six in dollars). */
export function creditMoney(cents: string | number | null | undefined): string {
  const amount = Number(cents ?? 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(Number.isFinite(amount) ? amount / 100 : 0);
}
