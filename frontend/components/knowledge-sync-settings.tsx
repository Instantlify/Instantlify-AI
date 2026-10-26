"use client";

import { useEffect, useState } from "react";
import { api, message, when } from "@/lib/api";
import { ErrorNotice, SuccessNotice, useFeedback } from "@/components/ui";

type Schedule = {
  enabled: boolean;
  interval_minutes: number;
  status: string;
  next_run_at: string | null;
  last_success_at: string | null;
  error_code: string;
};

export function KnowledgeSyncSettings({
  prefix,
  integrationId,
  name,
}: {
  prefix: string;
  integrationId: string;
  name: string;
}) {
  const [open, setOpen] = useState(false);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [interval, setIntervalMinutes] = useState(60);
  const feedback = useFeedback();
  const url = `${prefix}/integrations/${integrationId}/knowledge/schedule/`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    api<Schedule>(url, "GET", undefined, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setSchedule(data);
        setEnabled(data.enabled);
        setIntervalMinutes(data.interval_minutes);
      })
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, url]);
  useEffect(() => {
    if (!open || !schedule?.enabled) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      api<Schedule>(url, "GET", undefined, controller.signal)
        .then(setSchedule)
        .catch(() => {});
    }, 30000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [open, schedule?.enabled, url]);
  return (
    <div style={{ width: "100%", marginTop: 8 }}>
      <button
        type="button"
        className="boosend-btn-what"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Automatic knowledge sync
      </button>
      {open && (
        <section
          aria-label={`${name} automatic knowledge sync`}
          className="form-grid"
          style={{ marginTop: 14 }}
        >
          <ErrorNotice error={feedback.error} />
          <SuccessNotice notice={feedback.notice} />
          {!schedule ? (
            <p>Loading sync settings…</p>
          ) : (
            <>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(event) => setEnabled(event.target.checked)}
                />{" "}
                Keep knowledge up to date automatically
              </label>
              <label>
                Refresh frequency
                <select
                  value={interval}
                  onChange={(event) =>
                    setIntervalMinutes(Number(event.target.value))
                  }
                >
                  <option value={60}>Every hour</option>
                  <option value={360}>Every six hours</option>
                  <option value={1440}>Every day</option>
                </select>
              </label>
              <small>
                Only changed source content is reindexed. Indexing uses your AI
                credits. Refreshes continue in the background after you close
                this page.
              </small>
              <p role="status">
                {schedule.status === "running"
                  ? "Refreshing source…"
                  : schedule.enabled
                    ? "Automatic sync enabled"
                    : "Automatic sync paused"}
                {schedule.last_success_at
                  ? ` · Last source refresh ${when(schedule.last_success_at)}`
                  : ""}
                {schedule.next_run_at
                  ? ` · Next refresh ${when(schedule.next_run_at)}`
                  : ""}
              </p>
              {schedule.error_code && (
                <p role="alert">
                  {schedule.error_code === "plan_limit"
                    ? "Your plan does not currently allow syncing. Upgrade or pause the schedule."
                    : "The last refresh could not finish. Check the integration and knowledge indexing status. Existing knowledge was preserved; the schedule will retry."}
                </p>
              )}
              <button
                type="button"
                className="button primary small"
                disabled={feedback.busy}
                onClick={() =>
                  void feedback.run(async () => {
                    const saved = await api<Schedule>(url, "PUT", {
                      enabled,
                      interval_minutes: interval,
                    });
                    setSchedule(saved);
                    setEnabled(saved.enabled);
                    setIntervalMinutes(saved.interval_minutes);
                  }, "Automatic sync settings saved.")
                }
              >
                {feedback.busy ? "Saving…" : "Save automatic sync"}
              </button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
