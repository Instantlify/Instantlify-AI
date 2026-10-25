"use client";

import { useState } from "react";
import Link from "next/link";
import { Download, History, Play } from "lucide-react";
import { api, type AutomationRun, type FlowGraph } from "@/lib/api";
import { ErrorNotice, Modal, Pill, useFeedback } from "@/components/ui";

type Trace = { node_id: string; kind: string; detail: string; status: string };

export function FlowTools({
  prefix,
  workspaceId,
  automationId,
  graph,
  name,
}: {
  prefix: string;
  workspaceId: string;
  automationId: string;
  graph: FlowGraph;
  name: string;
}) {
  const [panel, setPanel] = useState<"test" | "history" | null>(null);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [replies, setReplies] = useState("");
  const [samples, setSamples] = useState("{}");
  const [trace, setTrace] = useState<Trace[]>([]);
  const feedback = useFeedback();
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
                For AI conditions, follow verification and random branches, use
                true or false. For reminders, true means the resource was
                clicked. For extraction, use an object. The walkthrough pauses
                when a required sample is missing.
              </small>
              <button
                className="button primary"
                disabled={feedback.busy}
                onClick={() =>
                  void feedback.run(async () => {
                    const response = await api<{ trace: Trace[] }>(
                      `${prefix}/automations/preview/`,
                      "POST",
                      {
                        graph,
                        replies: replies ? replies.split("\n") : [],
                        samples: JSON.parse(samples),
                      },
                    );
                    setTrace(response.trace);
                  })
                }
              >
                Run walkthrough
              </button>
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
