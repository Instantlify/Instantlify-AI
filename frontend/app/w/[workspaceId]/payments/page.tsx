"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Plus, ShoppingBag } from "lucide-react";
import {
  api,
  limit,
  money,
  when,
  type Billing,
  type Credits,
  type Offer,
  type Page,
  type Payment,
} from "@/lib/api";
import { startCheckout } from "@/lib/billing";
import { PlanCards, type Interval } from "@/components/plans";
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
import { PromoGift } from "@/components/growth";

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

export default function PaymentsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const owner = workspace.role === "owner";
  const [offers, setOffers] = useState<Offer[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [credits, setCredits] = useState<Credits | null>(null);
  const [loading, setLoading] = useState(true);
  const [origin] = useState(() =>
    typeof window === "undefined" ? "" : window.location.origin,
  );
  const [pendingPlan, setPendingPlan] = useState("");
  const [interval, setInterval] = useState<Interval>("monthly");
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
        const [plan, credit] = await Promise.all([
          api<Billing>(`${prefix}/billing/`, "GET", undefined, signal),
          api<Credits>(`${prefix}/billing/credits/`, "GET", undefined, signal),
        ]);
        setBilling(plan);
        setCredits(credit);
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

  async function startBilling(
    kind: "checkout" | "portal",
    plan = "",
    interval: Interval = "monthly",
  ) {
    setPendingPlan(plan || kind);
    await feedback.run(async () => {
      window.location.assign(
        await startCheckout(prefix, { kind, plan, interval }),
      );
    });
    setPendingPlan("");
  }

  async function buyCredits(amountCents: number) {
    setPendingPlan(`credits-${amountCents}`);
    await feedback.run(async () => {
      window.location.assign(
        await startCheckout(prefix, {
          kind: "credits",
          amount_cents: amountCents,
        }),
      );
    });
    setPendingPlan("");
  }

  async function saveAutoTopup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await feedback.run(async () => {
      setCredits(
        await api<Credits>(`${prefix}/billing/credits/`, "PATCH", {
          auto_topup_enabled: data.get("enabled") === "on",
          auto_topup_threshold_cents: Math.round(
            Number(data.get("threshold")) * 100,
          ),
          auto_topup_amount_cents: Math.round(Number(data.get("amount")) * 100),
        }),
      );
    }, "Auto top-up settings saved.");
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
      <PromoGift workspaceId={workspace.id} />
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
                    {billing.used} / {limit(billing.usage_limit)}
                  </h3>
                  <div className="funnel-bar" aria-hidden="true">
                    <i style={{ width: `${usageShare}%` }} />
                  </div>
                </div>
                <div className="card">
                  <span className="muted-text">Limits</span>
                  <h3>
                    {limit(billing.seat_limit)} seats ·{" "}
                    {limit(billing.channel_limit)} channels
                  </h3>
                  <span className="muted-text">
                    Pending invitations hold a seat.
                  </span>
                </div>
              </div>
              {billing.stripe_configured ? (
                <>
                  <div style={{ marginTop: 18 }}>
                    <PlanCards
                      plans={billing.catalog.filter((p) => p.slug !== "free")}
                      interval={interval}
                      onInterval={setInterval}
                      currentPlan={billing.plan}
                      currentInterval={billing.interval}
                      busySlug={pendingPlan}
                      trialDays={billing.trial_days}
                      onChoose={(slug, chosen) =>
                        startBilling("checkout", slug, chosen)
                      }
                    />
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
          {owner && credits && (
            <Panel
              title="AI credits"
              aside={
                credits.billing_mode === "byo_key"
                  ? "Using your own API key"
                  : "Prepaid, debited per model call"
              }
            >
              {credits.billing_mode === "byo_key" ? (
                <Empty>
                  This workspace uses its own provider key, so no credits are
                  debited. Switch the AI agent to platform credits to use
                  Nemio&apos;s key and prepaid balance instead.
                </Empty>
              ) : (
                <div className="stack">
                  <div className="three-col">
                    <div className="card">
                      <span className="muted-text">Balance</span>
                      <h3>
                        {money(Math.round(Number(credits.balance_cents)))}
                      </h3>
                      {credits.rate && (
                        <span className="small muted-text">
                          {credits.rate.model}:{" "}
                          {money(
                            Math.round(
                              Number(credits.rate.input_per_million_cents),
                            ),
                          )}{" "}
                          in ·{" "}
                          {money(
                            Math.round(
                              Number(credits.rate.output_per_million_cents),
                            ),
                          )}{" "}
                          out, per million tokens
                        </span>
                      )}
                    </div>
                    <div className="card">
                      <span className="muted-text">Buy credits</span>
                      <div className="form-actions">
                        {credits.topup_options.map((cents) => (
                          <button
                            key={cents}
                            className="button small primary"
                            disabled={
                              feedback.busy || !credits.stripe_configured
                            }
                            onClick={() => buyCredits(cents)}
                          >
                            {pendingPlan === `credits-${cents}`
                              ? "Opening…"
                              : money(cents)}
                          </button>
                        ))}
                      </div>
                      {!credits.stripe_configured && (
                        <span className="small muted-text">
                          Stripe is not configured for this deployment.
                        </span>
                      )}
                    </div>
                    <div className="card">
                      <span className="muted-text">Auto top-up</span>
                      <form className="form-grid" onSubmit={saveAutoTopup}>
                        <label className="inline">
                          <input
                            type="checkbox"
                            name="enabled"
                            defaultChecked={credits.auto_topup_enabled}
                            disabled={!credits.has_payment_method}
                          />
                          Enabled{" "}
                          {!credits.has_payment_method &&
                            "(make one top-up first to save a card)"}
                        </label>
                        <label>
                          When balance drops below ($)
                          <input
                            name="threshold"
                            type="number"
                            min={0}
                            step="1"
                            defaultValue={
                              credits.auto_topup_threshold_cents / 100
                            }
                          />
                        </label>
                        <label>
                          Top up by ($)
                          <input
                            name="amount"
                            type="number"
                            min={5}
                            step="1"
                            defaultValue={credits.auto_topup_amount_cents / 100}
                          />
                        </label>
                        {credits.auto_topup_failed_at && (
                          <span className="small muted-text">
                            The last automatic top-up failed on{" "}
                            {when(credits.auto_topup_failed_at)} and was
                            switched off.
                          </span>
                        )}
                        <div className="form-actions">
                          <button
                            className="button small secondary"
                            disabled={feedback.busy}
                          >
                            Save
                          </button>
                        </div>
                      </form>
                    </div>
                  </div>
                  {credits.transactions.length ? (
                    <Table
                      head={["When", "Type", "Detail", "Amount", "Balance"]}
                    >
                      {credits.transactions.slice(0, 20).map((row) => (
                        <tr key={row.id}>
                          <td>{when(row.created_at)}</td>
                          <td>
                            <Pill tone={statusTone(row.status)}>
                              {row.type.replace("_", " ")}
                            </Pill>
                          </td>
                          <td>
                            {row.model
                              ? `${row.model} · ${row.tokens_in} in / ${row.tokens_out} out`
                              : row.description}
                          </td>
                          <td>
                            {(Number(row.amount_cents) / 100).toLocaleString(
                              undefined,
                              {
                                style: "currency",
                                currency: "USD",
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 4,
                              },
                            )}
                          </td>
                          <td>
                            {money(
                              Math.round(Number(row.remaining_balance_cents)),
                            )}
                          </td>
                        </tr>
                      ))}
                    </Table>
                  ) : (
                    <Empty>No credit activity yet.</Empty>
                  )}
                </div>
              )}
            </Panel>
          )}
        </div>
      )}
    </>
  );
}
