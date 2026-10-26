"use client";

import { useEffect, useRef, useState } from "react";
import { api, message } from "@/lib/api";
import { ErrorNotice, SuccessNotice, useFeedback } from "@/components/ui";

type Creation = {
  id: string;
  name: string;
  status: string;
  agent_id: string;
  llm_id: string;
  error: string;
  is_test: boolean;
};
export function CallAgentManager({
  prefix,
  integrationId,
  provider,
}: {
  prefix: string;
  integrationId: string;
  provider: "vapi" | "retell";
}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Creation[]>([]);
  const [createdId, setCreatedId] = useState("");
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [greeting, setGreeting] = useState("");
  const [model, setModel] = useState("");
  const [voice, setVoice] = useState("");
  const [duration, setDuration] = useState(600);
  const requestId = useRef("");
  const feedback = useFeedback();
  const url = `${prefix}/integrations/${integrationId}/call-agents/`;
  const pending = rows.some((row) =>
    ["pending", "executing"].includes(row.status),
  );
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    api<Creation[]>(url, "GET", undefined, controller.signal)
      .then(setRows)
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, url]);
  useEffect(() => {
    if (!open || !pending) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      api<Creation[]>(url, "GET", undefined, controller.signal)
        .then(setRows)
        .catch(() => {});
    }, 4000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [open, pending, url]);
  return (
    <div style={{ width: "100%", marginTop: 8 }}>
      <button
        type="button"
        className="boosend-btn-what"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Create AI call agent
      </button>
      {open && (
        <section
          className="form-grid"
          aria-label={`${provider === "vapi" ? "Vapi" : "Retell"} call agents`}
          style={{ marginTop: 14 }}
        >
          <ErrorNotice error={feedback.error} />
          <SuccessNotice notice={feedback.notice} />
          <p>
            Create and publish a reusable agent in your connected provider
            account. This does not place a call. Provider charges apply when the
            agent is used.
          </p>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              if (createdId) return;
              requestId.current ||= crypto.randomUUID();
              void feedback.run(async () => {
                const row = await api<Creation>(url, "POST", {
                  request_id: requestId.current,
                  name,
                  instructions,
                  first_message: greeting,
                  model,
                  voice_id: voice,
                  max_duration_seconds: duration,
                });
                setRows((current) => [
                  row,
                  ...current.filter((item) => item.id !== row.id),
                ]);
                setCreatedId(row.id);
              });
            }}
          >
            <fieldset
              disabled={Boolean(createdId) || feedback.busy}
              className="form-grid"
              style={{ border: 0, padding: 0, margin: 0 }}
            >
              <label>
                Agent name
                <input
                  required
                  maxLength={40}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                Agent instructions
                <textarea
                  required
                  maxLength={8000}
                  rows={5}
                  value={instructions}
                  onChange={(event) => setInstructions(event.target.value)}
                />
              </label>
              <label>
                First message
                <textarea
                  required
                  maxLength={1000}
                  rows={2}
                  value={greeting}
                  onChange={(event) => setGreeting(event.target.value)}
                />
              </label>
              <label>
                {provider === "vapi"
                  ? "Vapi OpenAI model ID"
                  : "Retell model ID"}
                <input
                  required
                  maxLength={100}
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                />
              </label>
              <label>
                {provider === "vapi"
                  ? "ElevenLabs voice ID"
                  : "Retell voice ID"}
                <input
                  required
                  maxLength={150}
                  value={voice}
                  onChange={(event) => setVoice(event.target.value)}
                />
              </label>
              <small>
                Use model and voice IDs supported by your provider account.
              </small>
              <label>
                Maximum call length (seconds)
                <input
                  required
                  type="number"
                  min={30}
                  max={1800}
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                />
              </label>
              <button type="submit" className="button primary small">
                {feedback.busy ? "Requesting…" : "Create and publish agent"}
              </button>
            </fieldset>
          </form>
          {createdId && !pending && (
            <button
              type="button"
              className="button secondary small"
              onClick={() => {
                setCreatedId("");
                requestId.current = "";
              }}
            >
              Start a new agent
            </button>
          )}
          <div aria-label="Agent creation history" className="form-grid">
            {rows.map((row) => (
              <article
                key={row.id}
                style={{
                  borderTop: "1px solid var(--border-light)",
                  paddingTop: 12,
                }}
              >
                <strong>{row.name}</strong>
                <p role="status">
                  {row.is_test
                    ? "Local test agent · no provider agent was created"
                    : row.status === "complete"
                      ? "Agent ready"
                      : row.status === "needs_review"
                        ? "Creation needs review"
                        : "Creating agent…"}
                </p>
                {row.agent_id && (
                  <p>
                    Agent ID:{" "}
                    <code style={{ overflowWrap: "anywhere" }}>
                      {row.agent_id}
                    </code>
                  </p>
                )}
                {row.status === "needs_review" && (
                  <p role="alert">
                    Check your provider dashboard before creating another agent.
                    A prior step may already have succeeded.
                    {row.llm_id ? ` Response engine: ${row.llm_id}.` : ""}
                  </p>
                )}
                {row.status === "complete" && (
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={feedback.busy}
                    onClick={() =>
                      void feedback.run(async () => {
                        await api(`${prefix}/integrations/`, "POST", {
                          provider,
                          options: { agent_id: row.agent_id },
                        });
                      }, "Default call agent updated. Call steps with an explicit agent ID keep their own selection.")
                    }
                  >
                    Use as default call agent
                  </button>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
