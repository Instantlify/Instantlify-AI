"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import {
  api,
  message,
  UPGRADE_EVENT,
  type Billing,
  type PlanCard,
  type PlanLimits,
} from "@/lib/api";
import { startCheckout } from "@/lib/billing";
import { ErrorNotice, Modal } from "./ui";

export type Interval = "monthly" | "annual";

/** One ordered list drives every card. Adding a gated feature is one row here. */
export const FEATURE_ROWS: {
  key: keyof PlanLimits;
  label: string;
  kind: "count" | "flag";
}[] = [
  { key: "max_instagram_accounts", label: "Connected accounts", kind: "count" },
  { key: "team_seats", label: "Team seats", kind: "count" },
  { key: "max_contacts", label: "Contacts", kind: "count" },
  { key: "max_ai_messages", label: "AI messages per period", kind: "count" },
  { key: "ai_agent_enabled", label: "AI sales agent", kind: "flag" },
  {
    key: "integrations_unlocked",
    label: "Calendar & CRM integrations",
    kind: "flag",
  },
  {
    key: "content_scheduling_enabled",
    label: "Content scheduling",
    kind: "flag",
  },
  { key: "voice_notes_enabled", label: "AI voice notes", kind: "flag" },
];

export const LIMIT_LABELS: Record<string, string> = {
  max_instagram_accounts: "connected accounts",
  max_contacts: "contacts",
  team_seats: "team seats",
  max_ai_messages: "AI messages",
  ai_agent_enabled: "the AI agent",
  integrations_unlocked: "integrations",
  content_scheduling_enabled: "content scheduling",
  voice_notes_enabled: "voice notes",
};

export function priceCents(plan: PlanCard, interval: Interval) {
  return plan.prices.find((p) => p.interval === interval)?.price_cents ?? null;
}

/** Percent saved by paying annually, computed from the real prices, never typed in. */
export function savingsPercent(plan: PlanCard) {
  const monthly = priceCents(plan, "monthly");
  const annual = priceCents(plan, "annual");
  if (!monthly || annual === null) return null;
  const full = monthly * 12;
  return full > annual ? Math.round(((full - annual) / full) * 100) : null;
}

const dollars = (cents: number) =>
  (cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: cents % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  });

export function IntervalToggle({
  interval,
  onInterval,
  plans,
}: {
  interval: Interval;
  onInterval: (value: Interval) => void;
  plans: PlanCard[];
}) {
  const best = Math.max(0, ...plans.map((p) => savingsPercent(p) ?? 0));
  return (
    <div className="interval-toggle" role="group" aria-label="Billing interval">
      <button
        type="button"
        className={interval === "monthly" ? "active" : ""}
        aria-pressed={interval === "monthly"}
        onClick={() => onInterval("monthly")}
      >
        Monthly
      </button>
      <button
        type="button"
        className={interval === "annual" ? "active" : ""}
        aria-pressed={interval === "annual"}
        onClick={() => onInterval("annual")}
      >
        Annual
      </button>
      {best > 0 && <span className="save">Save up to {best}%</span>}
    </div>
  );
}

export function PlanCards({
  plans,
  interval,
  onInterval,
  onChoose,
  currentPlan,
  currentInterval,
  busySlug = "",
  cta = "Choose plan",
  trialDays = 0,
}: {
  plans: PlanCard[];
  interval: Interval;
  onInterval: (value: Interval) => void;
  onChoose: (slug: string, interval: Interval) => void;
  currentPlan?: string;
  currentInterval?: string;
  busySlug?: string;
  cta?: string;
  trialDays?: number;
}) {
  return (
    <div>
      <IntervalToggle
        interval={interval}
        onInterval={onInterval}
        plans={plans}
      />
      <div className="plan-grid">
        {plans.map((plan) => {
          const cents = priceCents(plan, interval);
          const saving = savingsPercent(plan);
          const current =
            currentPlan === plan.slug &&
            (!currentInterval || currentInterval === interval);
          return (
            <article
              key={plan.slug}
              className={`plan-card${plan.is_featured ? " featured" : ""}`}
            >
              {plan.is_featured && (
                <span className="plan-badge">Most popular</span>
              )}
              <h3>{plan.name}</h3>
              <div className="plan-price">
                {cents === null ? (
                  <strong>—</strong>
                ) : (
                  <>
                    <strong>${dollars(cents)}</strong>
                    <span>/ {interval === "monthly" ? "month" : "year"}</span>
                  </>
                )}
              </div>
              <div className="plan-note">
                {interval === "annual" && cents !== null && saving ? (
                  <>
                    ≈ ${dollars(Math.round(cents / 12))} / month ·{" "}
                    <b>Save {saving}%</b>
                  </>
                ) : interval === "monthly" && saving ? (
                  <>Save {saving}% with annual billing</>
                ) : null}
              </div>
              <ul className="plan-features">
                {FEATURE_ROWS.map((row) => {
                  const value = plan.limits[row.key];
                  const on = row.kind === "flag" ? Boolean(value) : true;
                  return (
                    <li key={row.key} className={on ? "" : "off"}>
                      {on ? (
                        <Check size={15} className="ok" />
                      ) : (
                        <X size={15} className="no" />
                      )}
                      {row.kind === "count"
                        ? `${value === null ? "Unlimited" : (value as number).toLocaleString()} ${row.label.toLowerCase()}`
                        : row.label}
                    </li>
                  );
                })}
              </ul>
              <button
                type="button"
                className={`button ${current ? "secondary" : "primary"}`}
                disabled={current || Boolean(busySlug) || cents === null}
                onClick={() => onChoose(plan.slug, interval)}
              >
                {cents === null
                  ? "Unavailable for this interval"
                  : current
                    ? "Current plan"
                    : busySlug === plan.slug
                      ? "Opening checkout…"
                      : cta}
              </button>
              {trialDays > 0 && !current && (
                <span className="plan-trial">{trialDays}-day free trial</span>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

/** Opens whenever any API call is refused on plan grounds (402 with
 * `upgrade_required`). Same cards as the pricing page: one source of truth. */
export function UpgradePrompt({
  prefix,
  agencyManaged,
}: {
  prefix: string;
  agencyManaged?: boolean;
}) {
  const [limitName, setLimitName] = useState("");
  const [billing, setBilling] = useState<Billing | null>(null);
  const [interval, setInterval] = useState<Interval>("monthly");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const open = (event: Event) => {
      setLimitName(String((event as CustomEvent<string>).detail || ""));
      setError("");
    };
    window.addEventListener(UPGRADE_EVENT, open);
    return () => window.removeEventListener(UPGRADE_EVENT, open);
  }, []);

  useEffect(() => {
    if (!limitName || agencyManaged) return;
    const controller = new AbortController();
    api<Billing>(`${prefix}/billing/`, "GET", undefined, controller.signal)
      .then((data) => {
        setBilling(data);
        if (data.interval === "annual") setInterval("annual");
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, [limitName, prefix, agencyManaged]);

  if (!limitName) return null;
  const what = LIMIT_LABELS[limitName] || "this feature";
  if (agencyManaged) {
    return (
      <Modal title="Plan limit reached" onClose={() => setLimitName("")}>
        <p>Your workspace has reached the limit for {what}.</p>
        <p style={{ marginTop: 12, color: "var(--muted)" }}>
          This workspace is managed by your agency. Please contact your agency
          administrator to adjust your plan limits or increase allocation.
        </p>
      </Modal>
    );
  }
  return (
    <Modal title="Upgrade your plan" onClose={() => setLimitName("")}>
      <p>
        Your current plan does not include {what}. Pick a plan below; the change
        applies as soon as checkout completes.
      </p>
      <ErrorNotice error={error} />
      {billing ? (
        <PlanCards
          plans={billing.catalog.filter((p) => p.slug !== "free")}
          interval={interval}
          onInterval={setInterval}
          currentPlan={billing.plan}
          currentInterval={billing.interval}
          busySlug={busy}
          trialDays={billing.trial_days}
          cta="Upgrade"
          onChoose={async (slug, chosen) => {
            setBusy(slug);
            setError("");
            try {
              window.location.assign(
                await startCheckout(prefix, {
                  kind: "checkout",
                  plan: slug,
                  interval: chosen,
                }),
              );
            } catch (err) {
              setError(message(err));
              setBusy("");
            }
          }}
        />
      ) : (
        !error && <p className="loading-text">Loading plans…</p>
      )}
    </Modal>
  );
}
