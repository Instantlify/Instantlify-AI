"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type PlanCard } from "@/lib/api";
import { PlanCards, type Interval } from "@/components/plans";

export function PublicPricing() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<{
    plans: PlanCard[];
    trial_days: number;
  } | null>(null);
  const [interval, setInterval] = useState<Interval>("monthly");
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<{ plans: PlanCard[]; trial_days: number }>(
      "/api/public/plans/",
      "GET",
      undefined,
      controller.signal,
    )
      .then(setCatalog)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [attempt]);
  if (error)
    return (
      <div className="pricing-unavailable" role="status">
        <h3>We couldn’t load the current plans.</h3>
        <p>Please try again to see the latest pricing.</p>
        <button
          className="button primary"
          onClick={() => {
            setError(false);
            setAttempt(attempt + 1);
          }}
        >
          Try again
        </button>
      </div>
    );
  if (!catalog)
    return (
      <p className="pricing-unavailable" role="status">
        Loading current plans…
      </p>
    );
  if (!catalog.plans.length)
    return (
      <p className="pricing-unavailable">
        Plans are being updated. Please check back soon.
      </p>
    );
  return (
    <>
      <PlanCards
        plans={catalog.plans.filter((plan) => plan.slug !== "free")}
        interval={interval}
        onInterval={setInterval}
        trialDays={catalog.trial_days}
        cta="Get started"
        onChoose={(plan, chosen) =>
          router.push(
            `/auth?mode=signup&plan=${encodeURIComponent(plan)}&interval=${chosen}`,
          )
        }
      />
      <p className="pricing-foot">
        Prices in USD, excluding tax. Annual plans are billed once per year.
        Review your plan before checkout.
      </p>
    </>
  );
}
