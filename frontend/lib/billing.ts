import { api, idempotencyKey, type BillingJob } from "./api";

export const BILLING_ERRORS: Record<string, string> = {
  stripe_not_configured: "Stripe is not configured for this deployment.",
  billing_provider_error:
    "The billing provider rejected the request. Please try again.",
  price_not_configured: "That plan has no price configured yet.",
  already_on_plan: "You are already on that plan.",
};

/** Starts a Stripe Checkout or Billing Portal session and resolves to its URL.
 * The backend runs the Stripe call in a worker, so this polls the job briefly. */
export async function startCheckout(
  prefix: string,
  body: {
    kind: "checkout" | "portal" | "credits";
    plan?: string;
    interval?: string;
    amount_cents?: number;
    return_to?: "onboarding";
  },
): Promise<string> {
  const job = await api<BillingJob>(
    `${prefix}/billing/`,
    "POST",
    body,
    undefined,
    {
      "Idempotency-Key": idempotencyKey(),
    },
  );
  let current = job;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (current.status === "complete" || current.status === "failed") break;
    await new Promise((resolve) => window.setTimeout(resolve, 2000));
    current = await api<BillingJob>(`${prefix}/billing/jobs/${job.id}/`);
  }
  if (current.status === "complete" && current.result.url)
    return current.result.url;
  const code = current.result.error || "timeout";
  throw new Error(
    BILLING_ERRORS[code] ||
      (code === "timeout"
        ? "Billing is taking longer than expected. Please try again."
        : "Unable to start billing. Please try again."),
  );
}
