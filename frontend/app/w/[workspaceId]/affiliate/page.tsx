"use client";

import { useCallback, useEffect, useState } from "react";
import { api, message } from "@/lib/api";
import {
  CopyField,
  ErrorNotice,
  SuccessNotice,
  PageHeading,
  Panel,
  Stat,
  Pill,
  useFeedback,
} from "@/components/ui";

type Affiliate = {
  configured: boolean;
  status: string;
  stats?: Record<string, number>;
  revenue?: string | null;
  currency?: string;
  is_confirmed?: boolean;
  campaigns?: {
    name: string;
    state: string;
    ref_link: string;
    coupon: string;
  }[];
};

function revenue(amount: string | null | undefined, currency = "USD") {
  if (amount == null) return "Unavailable";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(Number(amount));
  } catch {
    return `${currency} ${amount}`;
  }
}

export default function AffiliatePage() {
  const feedback = useFeedback();
  const [data, setData] = useState<Affiliate | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(
    (signal?: AbortSignal) =>
      api<Affiliate>("/api/affiliate/", "GET", undefined, signal).then(setData),
    [],
  );
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);
  return (
    <>
      <PageHeading
        eyebrow="Account / Referrals"
        title="Your referral program"
        text="Your own referral links and results, supplied by the affiliate program."
        action={
          <button
            className="button secondary"
            disabled={feedback.busy}
            onClick={() => void feedback.run(() => load())}
          >
            Refresh referral details
          </button>
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading && <p role="status">Loading referral details…</p>}
      {data?.configured === false && (
        <Panel title="Referral program unavailable">
          <p>The platform has not enabled the referral program yet.</p>
        </Panel>
      )}
      {data?.status === "verify_email" && (
        <Panel title="Verify your email first">
          <p>Confirm your email address before joining the referral program.</p>
        </Panel>
      )}
      {data?.status === "not_enrolled" && (
        <Panel title="Join the referral program">
          <p>
            Joining sends your profile name and verified email address to the
            referral program. Campaign approval and rewards are managed by the
            program.
          </p>
          <button
            className="button primary"
            disabled={feedback.busy}
            onClick={() =>
              void feedback
                .run(
                  async () =>
                    setData(
                      await api<Affiliate>("/api/affiliate/", "POST", {}),
                    ),
                  "Referral account created.",
                )
                .then(() => load().catch(() => undefined))
            }
          >
            Join referral program
          </button>
        </Panel>
      )}
      {data?.status === "needs_review" && (
        <Panel title="Enrollment needs review">
          <p>
            Your earlier enrollment could not be confirmed. Refresh your details
            or contact support before trying again.
          </p>
        </Panel>
      )}
      {data?.status === "active" && (
        <>
          <div className="stats-grid">
            <Stat
              label="Clicks"
              value={String(data.stats?.clicks_count ?? 0)}
            />
            <Stat
              label="Referrals"
              value={String(data.stats?.referrals_count ?? 0)}
            />
            <Stat label="Sales" value={String(data.stats?.sales_count ?? 0)} />
            <Stat
              label="Customers"
              value={String(data.stats?.customers_count ?? 0)}
            />
            <Stat
              label="Active customers"
              value={String(data.stats?.active_customers_count ?? 0)}
            />
            <Stat
              label="Reported revenue"
              value={revenue(data.revenue, data.currency)}
            />
          </div>
          {!data.is_confirmed && (
            <p>
              Your referral account is awaiting confirmation from the program.
            </p>
          )}
          {data.campaigns?.map((campaign, index) => (
            <Panel
              key={index}
              title={campaign.name}
              aside={<Pill>{campaign.state}</Pill>}
            >
              {campaign.ref_link ? (
                <CopyField
                  label={`${campaign.name} referral link`}
                  value={campaign.ref_link}
                />
              ) : (
                <p>No referral link has been issued for this campaign.</p>
              )}
              {campaign.coupon && (
                <CopyField
                  label={`${campaign.name} promo code`}
                  value={campaign.coupon}
                />
              )}
            </Panel>
          ))}
          {!data.campaigns?.length && (
            <p>You have not been assigned a referral campaign yet.</p>
          )}
        </>
      )}
    </>
  );
}
