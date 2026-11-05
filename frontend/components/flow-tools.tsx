"use client";

import { useState } from "react";
import Link from "next/link";
import { Download, History, Play } from "lucide-react";
import { api, type AutomationRun, type FlowGraph } from "@/lib/api";
import { ErrorNotice, Modal, Pill, useFeedback } from "@/components/ui";
import { channelLabel } from "@/lib/channels";
import { firstReplyStep } from "@/lib/growth";
import { KIND_CHANNELS, TRIGGER_LABELS } from "@/lib/meta-templates";

type Trace = { node_id: string; kind: string; detail: string; status: string };

export function FlowTools({
  prefix,
  workspaceId,
  automationId,
  graph,
  name,
  boundProvider,
}: {
  prefix: string;
  workspaceId: string;
  automationId: string;
  graph: FlowGraph;
  name: string;
  boundProvider?: string;
}) {
  const [panel, setPanel] = useState<"test" | "history" | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [replies, setReplies] = useState("");
  const [samples, setSamples] = useState("{}");
  const [trace, setTrace] = useState<Trace[]>([]);
  const [sampleText, setSampleText] = useState("");
  const [eventKey, setEventKey] = useState("");
  const [matched, setMatched] = useState<boolean>();
  const eventOptions = Object.entries(KIND_CHANNELS).flatMap(
    ([kind, channels]) =>
      channels
        .filter((channel) => !boundProvider || channel === boundProvider)
        .map((channel) => ({ kind, channel, key: `${kind}:${channel}` })),
  );
  const sampleEvent =
    eventOptions.find((option) => option.key === eventKey) ??
    eventOptions.find(({ kind, channel }) =>
      graph.triggers.some(
        (trigger) =>
          trigger.kind === kind &&
          (!trigger.channel || trigger.channel === channel),
      ),
    ) ??
    eventOptions[0];
  const feedback = useFeedback();
  const lastCompleted = runs.find((run) => run.status === "completed");
  const lastFailure = runs.find((run) => run.status === "failed");
  function download() {
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            { format: "nemio.automation", version: 1, name, graph },
            null,
            2,
          ),
        ],
        { type: "application/json" },
      ),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${name.replace(/[^a-z0-9_-]/gi, "-") || "automation"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <button
        className="button secondary small"
        onClick={() => setPanel("test")}
      >
        <Play size={14} /> Test flow
      </button>
      <button className="button secondary small" onClick={download}>
        <Download size={14} /> Export template
      </button>
      <button
        className="button secondary small"
        disabled={automationId === "new" || feedback.busy}
        onClick={() => {
          setPanel("history");
          void feedback.run(async () =>
            setRuns(
              await api<AutomationRun[]>(
                `${prefix}/automation-runs/?automation=${automationId}`,
              ),
            ),
          );
        }}
      >
        <History size={14} /> Execution history
      </button>
      {panel && (
        <Modal
          title={panel === "test" ? "Test flow" : "Execution history"}
          onClose={() => setPanel(null)}
        >
          <ErrorNotice error={feedback.error} />
          {panel === "test" ? (
            <div className="form-grid">
              <p className="muted-text">
                Walk through your current draft. Messages, CRM changes, delays
                and external actions are simulated. This does not call a
                provider or change customer data.
              </p>
              {sampleEvent && (
                <>
                  <label>
                    Sample event
                    <select
                      value={sampleEvent.key}
                      onChange={(event) => setEventKey(event.target.value)}
                    >
                      {eventOptions.map(({ kind, channel, key }) => (
                        <option key={key} value={key}>
                          {channelLabel(channel)} ·{" "}
                          {TRIGGER_LABELS[kind] ?? kind}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Sample incoming text (optional)
                    <input
                      value={sampleText}
                      maxLength={2000}
                      onChange={(event) => setSampleText(event.target.value)}
                    />
                    <small>
                      Checks event type, channel and keyword. Account delivery,
                      post targeting and cooldown are checked on live runs.
                    </small>
                  </label>
                </>
              )}
              <details>
                <summary>Optional replies and external results</summary>
                <label>
                  Sample replies, one per line
                  <textarea
                    rows={3}
                    value={replies}
                    onChange={(e) => setReplies(e.target.value)}
                  />
                </label>
                <label>
                  Sample external results by node ID (JSON)
                  <textarea
                    rows={3}
                    value={samples}
                    onChange={(e) => setSamples(e.target.value)}
                  />
                </label>
                <small>
                  For AI conditions, follow verification and random branches,
                  use true or false. For reminders, true means the resource was
                  clicked. For extraction, use an object. The walkthrough pauses
                  when a required sample is missing.
                </small>
              </details>
              <button
                className="button primary"
                disabled={feedback.busy}
                onClick={() =>
                  void feedback.run(async () => {
                    setMatched(undefined);
                    setTrace([]);
                    const response = await api<{
                      trace: Trace[];
                      trigger_matched?: boolean;
                    }>(`${prefix}/automations/preview/`, "POST", {
                      graph,
                      replies: replies ? replies.split("\n") : [],
                      samples: JSON.parse(samples),
                      trigger_event:
                        sampleText.trim() && sampleEvent
                          ? {
                              kind: sampleEvent.kind,
                              channel: sampleEvent.channel,
                              text: sampleText,
                            }
                          : undefined,
                    });
                    setTrace(response.trace);
                    setMatched(response.trigger_matched);
                    if (response.trigger_matched && response.trace.some(
                      (row) => ["send_message", "send_buttons", "send_media"].includes(row.kind),
                    )) {
                      firstReplyStep(workspaceId, "tested", true);
                    }
                  })
                }
              >
                Run walkthrough
              </button>
              {matched !== undefined && (
                <p role="status">
                  {matched
                    ? "The sample matches a draft trigger. See the simulated steps below."
                    : "The sample did not match. Check the event type, channel and keyword."}
                </p>
              )}
              <ol>
                {trace.map((row, index) => (
                  <li key={index} style={{ marginBottom: 12 }}>
                    <strong>
                      {row.node_id} · {row.kind}
                    </strong>{" "}
                    <Pill>{row.status}</Pill>
                    <p style={{ whiteSpace: "pre-wrap" }}>{row.detail}</p>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="stack">
              {feedback.busy && <p>Loading runs…</p>}
              {!feedback.busy && !runs.length && (
                <p>
                  No executions recorded yet. New runs appear here when this
                  flow receives a matching trigger.
                </p>
              )}
              {!feedback.busy && runs.length > 0 && (
                <p className="muted-text">
                  Last completed run:{" "}
                  {lastCompleted?.finished_at
                    ? new Date(lastCompleted.finished_at).toLocaleString()
                    : "No completion time in recent history"}
                  {lastFailure && (
                    <> · Latest failure: {lastFailure.error_code || lastFailure.node_id}</>
                  )}
                </p>
              )}
              {runs.map((run) => (
                <details key={run.id} className="card" style={{ padding: 14 }}>
                  <summary>
                    <Pill>{run.status}</Pill> · {run.steps} steps ·{" "}
                    {run.created_at
                      ? new Date(run.created_at).toLocaleString()
                      : "Earlier run"}
                  </summary>
                  <p>
                    Revision {run.revision ?? "—"} · Last node: {run.node_id}
                    {run.error_code ? ` · ${run.error_code}` : ""}
                  </p>
                  <Link
                    className="text-button"
                    href={`/w/${workspaceId}/inbox?conversation=${run.conversation_id}`}
                  >
                    Open conversation
                  </Link>
                  <ol>
                    {run.trace?.map((entry, index) => (
                      <li key={index}>
                        {entry.node_id} · {entry.status} · step {entry.steps}
                      </li>
                    ))}
                  </ol>
                </details>
              ))}
            </div>
          )}
        </Modal>
      )}
    </>
  );
}
