"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CreditCard, Plus, ShoppingBag } from "lucide-react";
import {
  api,
  idempotencyKey,
  money,
  when,
  type Billing,
  type BillingJob,
  type Offer,
  type Page,
  type Payment,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";

const CURRENCIES = [
  "usd",
  "eur",
  "gbp",
  "cad",
  "aud",
  "nzd",
  "chf",
  "sek",
  "nok",
  "dkk",
];

const BILLING_ERRORS: Record<string, string> = {
  stripe_not_configured: "Stripe is not configured for this deployment.",
  billing_provider_error:
    "The billing provider rejected the request. Please try again.",
  price_not_configured: "That plan has no price configured yet.",
};

export default function PaymentsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const owner = workspace.role === "owner";
  const [offers, setOffers] = useState<Offer[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [loading, setLoading] = useState(true);
  const [origin] = useState(() =>
    typeof window === "undefined" ? "" : window.location.origin,
  );
  const [pendingPlan, setPendingPlan] = useState("");
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [offerPage, paid] = await Promise.all([
        api<Page<Offer>>(`${prefix}/offers/`, "GET", undefined, signal),
        manager
          ? api<Payment[]>(`${prefix}/payments/`, "GET", undefined, signal)
          : Promise.resolve([] as Payment[]),
      ]);
      setOffers(offerPage.results);
      setPayments(paid);
      if (owner) {
        setBilling(
          await api<Billing>(`${prefix}/billing/`, "GET", undefined, signal),
        );
      }
    },
    [prefix, manager, owner],
  );

  useEffect(() => {
    const controller = new AbortController();
    // Deferred so state updates happen in response to the fetch, not the render.
    queueMicrotask(() => {
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError(String((err as Error).message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function createOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const amount = Math.round(Number(data.get("amount")) * 100);
    await feedback.run(async () => {
      const created = await api<Offer>(`${prefix}/offers/`, "POST", {
        name: data.get("name"),
        description: data.get("description"),
        amount_cents: amount,
        currency: data.get("currency"),
      });
      setOffers((list) => [...list, created]);
      form.reset();
    }, "Offer created.");
  }

  async function toggleOffer(offer: Offer) {
    await feedback.run(async () => {
      const updated = await api<Offer>(
        `${prefix}/offers/${offer.id}/`,
        "PATCH",
        {
          active: !offer.active,
        },
      );
      setOffers((list) =>
        list.map((item) => (item.id === updated.id ? updated : item)),
      );
    });
  }

  async function startBilling(kind: "checkout" | "portal", plan = "") {
    setPendingPlan(plan || kind);
    await feedback.run(async () => {
      const job = await api<BillingJob>(
        `${prefix}/billing/`,
        "POST",
        { kind, plan },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      );
      let current = job;
      for (let attempt = 0; attempt < 30; attempt += 1) {
        if (current.status === "complete" || current.status === "failed") break;
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        current = await api<BillingJob>(`${prefix}/billing/jobs/${job.id}/`);
      }
      if (current.status === "complete" && current.result.url) {
        window.location.assign(current.result.url);
        return;
      }
      const code = current.result.error || "timeout";
      throw new Error(
        BILLING_ERRORS[code] ||
          (code === "timeout"
            ? "Billing is taking longer than expected. Please try again."
            : "Unable to start billing. Please try again."),
      );
    });
    setPendingPlan("");
  }

  const offerName = (id: string) =>
    offers.find((item) => item.id === id)?.name || "Deleted offer";
  const usageShare = billing
    ? Math.min(
        100,
        Math.round((billing.used / (billing.usage_limit || 1)) * 100),
      )
    : 0;

  return (
    <>
      <PageHeading
        eyebrow="Payments"
        title="Close the loop in chat."
        text="Offers the AI agent and your team can sell inside a conversation, and your plan with Nemio."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading payments…</p>
      ) : (
        <div className="stack">
          <div className="two-col">
            <Panel title="Offers" aside={`${offers.length} configured`}>
              {offers.length ? (
                <Table head={["Offer", "Amount", "Status", ""]}>
                  {offers.map((offer) => (
                    <tr key={offer.id}>
                      <td>
                        <strong>{offer.name}</strong>
                        {offer.description && (
                          <div className="muted-text">{offer.description}</div>
                        )}
                      </td>
                      <td>{money(offer.amount_cents, offer.currency)}</td>
                      <td>
                        <Pill tone={offer.active ? "good" : "neutral"}>
                          {offer.active ? "active" : "inactive"}
                        </Pill>
                      </td>
                      <td>
                        {manager && (
                          <button
                            className="text-button"
                            disabled={feedback.busy}
                            onClick={() => toggleOffer(offer)}
                          >
                            {offer.active ? "Deactivate" : "Activate"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty>
                  No offers yet. Create one so the agent and your team can send
                  checkout links.
                </Empty>
              )}
              <p className="muted-text" style={{ marginTop: 14 }}>
                The agent&apos;s <code>create_payment_link</code> tool and the
                inbox &ldquo;Send payment link&rdquo; action only use these
                offers. Amounts are never taken from the model&apos;s output.
              </p>
            </Panel>
            {manager ? (
              <Panel title="New offer">
                <form className="form-grid" onSubmit={createOffer}>
                  <label>
                    Name
                    <input name="name" maxLength={100} required />
                  </label>
                  <label>
                    Description
                    <input name="description" maxLength={300} />
                  </label>
                  <label>
                    Amount
                    <input
                      name="amount"
                      type="number"
                      min="0.5"
                      step="0.01"
                      required
                    />
                    <span className="hint">
                      Minimum 0.50 in the selected currency.
                    </span>
                  </label>
                  <label>
                    Currency
                    <select name="currency" defaultValue="usd">
                      {CURRENCIES.map((code) => (
                        <option key={code} value={code}>
                          {code.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="form-actions">
                    <button className="button primary" disabled={feedback.busy}>
                      {feedback.busy ? "Saving…" : "Create offer"}
                      <Plus size={16} />
                    </button>
                  </div>
                </form>
              </Panel>
            ) : (
              <Panel title="Offers">
                <Empty>Owners and admins manage offers.</Empty>
              </Panel>
            )}
          </div>

          {manager && (
            <Panel title="Payments" aside={`${payments.length} recent`}>
              <p className="muted-text">
                Checkouts run on your own Stripe account. Connect Stripe under{" "}
                <Link href={`/w/${workspace.id}/integrations`}>
                  Integrations
                </Link>
                , then register this webhook URL in Stripe for the{" "}
                <code>checkout.session.completed</code> event.
              </p>
              <CopyField
                label="Stripe webhook URL (your account)"
                value={`${origin}/webhooks/stripe/${workspace.id}/`}
              />
              {payments.length ? (
                <div style={{ marginTop: 16 }}>
                  <Table
                    head={["Created", "Offer", "Amount", "Status", "Paid"]}
                  >
                    {payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>{when(payment.created_at)}</td>
                        <td>{offerName(payment.offer_id)}</td>
                        <td>{money(payment.amount_cents, payment.currency)}</td>
                        <td>
                          <Pill tone={statusTone(payment.status)}>
                            {payment.status}
                          </Pill>
                        </td>
                        <td>{when(payment.paid_at)}</td>
                      </tr>
                    ))}
                  </Table>
                </div>
              ) : (
                <Empty>No checkouts have been sent yet.</Empty>
              )}
            </Panel>
          )}

          {owner && billing && (
            <Panel
              title="Your plan"
              aside={
                <Pill tone={statusTone(billing.status)}>{billing.status}</Pill>
              }
            >
              <div className="three-col">
                <div className="card">
                  <span className="muted-text">Plan</span>
                  <h3 style={{ textTransform: "capitalize" }}>
                    {billing.plan}
                  </h3>
                  <span className="muted-text">
                    Period started {when(billing.period_start)}
                  </span>
                </div>
                <div className="card">
                  <span className="muted-text">AI messages this period</span>
                  <h3>
                    {billing.used} / {billing.usage_limit}
                  </h3>
                  <div className="funnel-bar" aria-hidden="true">
                    <i style={{ width: `${usageShare}%` }} />
                  </div>
                </div>
                <div className="card">
                  <span className="muted-text">Limits</span>
                  <h3>
                    {billing.seat_limit} seats · {billing.channel_limit}{" "}
                    channels
                  </h3>
                  <span className="muted-text">
                    Pending invitations hold a seat.
                  </span>
                </div>
              </div>
              {billing.stripe_configured ? (
                <>
                  <div className="card-grid" style={{ marginTop: 18 }}>
                    {Object.entries(billing.plans).map(([plan, limits]) => (
                      <div className="card" key={plan}>
                        <h3 style={{ textTransform: "capitalize" }}>{plan}</h3>
                        <span className="small">
                          {limits.seats} seats · {limits.channels} channels
                        </span>
                        <span className="small">
                          {limits.messages.toLocaleString()} AI messages /
                          period
                        </span>
                        <div className="form-actions">
                          <button
                            className={`button small ${
                              billing.plan === plan ? "secondary" : "primary"
                            }`}
                            disabled={feedback.busy || billing.plan === plan}
                            onClick={() => startBilling("checkout", plan)}
                          >
                            {billing.plan === plan
                              ? "Current plan"
                              : pendingPlan === plan
                                ? "Opening checkout…"
                                : "Choose plan"}
                            <CreditCard size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="form-actions" style={{ marginTop: 16 }}>
                    <button
                      className="button secondary"
                      disabled={feedback.busy}
                      onClick={() => startBilling("portal")}
                    >
                      {pendingPlan === "portal" ? "Opening…" : "Manage billing"}
                      <ShoppingBag size={16} />
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted-text" style={{ marginTop: 16 }}>
                  Stripe is not configured for this deployment, so plans cannot
                  be changed here.
                </p>
              )}
            </Panel>
          )}
        </div>
      )}
    </>
  );
}
