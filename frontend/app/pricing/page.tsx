"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { message, type PlanCard } from "@/lib/api";
import { PlanCards, type Interval } from "@/components/plans";
import { Brand } from "@/components/shell";
import { ErrorNotice } from "@/components/ui";
import { TrackVisit } from "@/components/growth";

type Catalog = { plans: PlanCard[]; trial_days: number };

export default function PricingPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [interval, setInterval] = useState<Interval>("annual");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/public/plans/", {
      signal: controller.signal,
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error("The pricing catalog is unavailable.");
        setCatalog((await response.json()) as Catalog);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="pricing-page">
      <TrackVisit page="/pricing" />
      <Link href="/" aria-label="Instantlify home">
        <Brand />
      </Link>
      <div className="pricing-head">
        <span className="eyebrow">PRICING</span>
        <h1>Simple plans that grow with your DMs.</h1>
        <p>
          Compare the current features and limits, then choose the plan that
          fits your business.
        </p>
      </div>
      <ErrorNotice error={error} />
      {catalog ? (
        <PlanCards
          plans={catalog.plans.filter((plan) => plan.slug !== "free")}
          interval={interval}
          onInterval={setInterval}
          trialDays={catalog.trial_days}
          cta="Get started"
          onChoose={(slug, chosen) =>
            router.push(
              `/auth?mode=signup&plan=${encodeURIComponent(slug)}&interval=${chosen}`,
            )
          }
        />
      ) : (
        !error && <p className="loading-text">Loading plans…</p>
      )}
      <p className="pricing-foot muted-text">
        Prices exclude tax. Annual plans are billed once per year. You can
        change or cancel from the Payments page at any time.
      </p>
    </main>
  );
}
