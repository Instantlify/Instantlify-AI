"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import {
  api,
  money,
  when,
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
  const [loading, setLoading] = useState(true);
  const [origin] = useState(() =>
    typeof window === "undefined" ? "" : window.location.origin,
  );
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
    },
    [prefix, manager],
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

  const offerName = (id: string) =>
    offers.find((item) => item.id === id)?.name || "Deleted offer";

  return (
    <>
      <PromoGift workspaceId={workspace.id} />
      <PageHeading
        eyebrow="Payments"
        title="Close the loop in chat."
        text="Offers the AI agent and your team can sell inside a conversation."
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

          {owner && (
            <p className="muted-text">
              Your Nemio plan and AI credits are under{" "}
              <Link href={`/w/${workspace.id}/settings?tab=subscription`}>
                Settings → Subscription
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </>
  );
}
