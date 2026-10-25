"use client";

import { useEffect, useState } from "react";
import { api, message } from "@/lib/api";
import {
  ErrorNotice,
  Modal,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

type Segment = { id: string; name: string; prompt: string; enabled: boolean };
export function SegmentationDialog({
  prefix,
  onClose,
}: {
  prefix: string;
  onClose: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [editing, setEditing] = useState<Partial<Segment> | null>(null);
  const feedback = useFeedback();
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<{
        segmentation_prompt?: string;
        segmentation_enabled?: boolean;
        enabled?: boolean;
      }>(`${prefix}/agent/`, "GET", undefined, controller.signal),
      api<Segment[]>(
        `${prefix}/segments/`,
        "GET",
        undefined,
        controller.signal,
      ),
    ])
      .then(([data, rows]) => {
        setPrompt(data.segmentation_prompt || "");
        setEnabled(data.segmentation_enabled ?? true);
        setAgentEnabled(Boolean(data.enabled));
        setSegments(rows);
        setLoaded(true);
      })
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);
  return (
    <Modal title="AI contact segmentation" onClose={onClose}>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {!loaded ? (
        <p>Loading classification settings...</p>
      ) : (
        <div className="form-grid">
          <p>
            Create named groups with your own criteria. Your assistant checks
            conversations against each prompt and applies matching segment tags.
            Classification uses AI credits.
          </p>
          {!agentEnabled && (
            <p>
              Enable your AI assistant in AI settings for automatic
              classification to run.
            </p>
          )}
          {!enabled && (
            <p>
              Automatic classification is currently paused. Enable it in
              classification settings below.
            </p>
          )}
          {editing ? (
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                void feedback.run(async () => {
                  const saved = await api<Segment>(
                    `${prefix}/segments/${editing.id ? `${editing.id}/` : ""}`,
                    editing.id ? "PATCH" : "POST",
                    {
                      name: editing.name,
                      prompt: editing.prompt,
                      enabled: editing.enabled ?? true,
                    },
                  );
                  setSegments((rows) => [
                    ...rows.filter((row) => row.id !== saved.id),
                    saved,
                  ]);
                  setEditing(null);
                }, "Segment saved. Existing contacts will be checked automatically.");
              }}
            >
              <label>
                Segment name
                <input
                  required
                  maxLength={32}
                  value={editing.name || ""}
                  onChange={(event) =>
                    setEditing({ ...editing, name: event.target.value })
                  }
                />
              </label>
              <label>
                Segment prompt
                <textarea
                  required
                  rows={6}
                  maxLength={4000}
                  value={editing.prompt || ""}
                  onChange={(event) =>
                    setEditing({ ...editing, prompt: event.target.value })
                  }
                  placeholder="People interested in our enterprise plan who have asked for a team demo."
                />
              </label>
              <div className="row">
                <button
                  className="button primary small"
                  disabled={feedback.busy}
                >
                  {editing.id ? "Save segment" : "Create segment"}
                </button>
                <button
                  type="button"
                  className="button secondary small"
                  onClick={() => setEditing(null)}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button
              className="button primary small"
              disabled={segments.length >= 20}
              onClick={() =>
                setEditing({ name: "", prompt: "", enabled: true })
              }
            >
              New segment
            </button>
          )}
          {segments.map((segment) => (
            <article className="card" key={segment.id} style={{ padding: 16 }}>
              <strong>{segment.name}</strong>
              <p>{segment.prompt}</p>
              <small>
                Contact tag: segment:{segment.name} -{" "}
                {segment.enabled ? "Enabled" : "Paused"}
              </small>
              <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
                <button
                  className="button secondary small"
                  onClick={() => setEditing(segment)}
                >
                  Edit {segment.name}
                </button>
                <button
                  className="button secondary small"
                  disabled={feedback.busy}
                  onClick={() =>
                    void feedback.run(async () => {
                      const updated = await api<Segment>(
                        `${prefix}/segments/${segment.id}/`,
                        "PATCH",
                        { enabled: !segment.enabled },
                      );
                      setSegments((rows) =>
                        rows.map((row) =>
                          row.id === updated.id ? updated : row,
                        ),
                      );
                    })
                  }
                >
                  {segment.enabled ? "Pause" : "Enable"} {segment.name}
                </button>
                <button
                  className="text-button"
                  disabled={feedback.busy}
                  onClick={() =>
                    void feedback.run(async () => {
                      await api(`${prefix}/segments/${segment.id}/`, "DELETE");
                      setSegments((rows) =>
                        rows.filter((row) => row.id !== segment.id),
                      );
                    }, "Segment and its automatic contact tags removed.")
                  }
                >
                  Delete {segment.name}
                </button>
              </div>
            </article>
          ))}
          <details>
            <summary>Classification settings</summary>
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                void feedback.run(async () => {
                  await api(`${prefix}/agent/`, "PUT", {
                    segmentation_enabled: enabled,
                    segmentation_prompt: prompt,
                  });
                }, "Classification settings saved.");
              }}
            >
              <label className="inline">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(event) => setEnabled(event.target.checked)}
                />{" "}
                Automatically classify contacts
              </label>
              <label>
                Standard cold, warm and hot criteria
                <textarea
                  rows={5}
                  maxLength={6000}
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                />
                <small>
                  Optional rules for the standard sales-intent tags, in addition
                  to your custom segments.
                </small>
              </label>
              <button className="button primary small" disabled={feedback.busy}>
                Save classification settings
              </button>
            </form>
          </details>
        </div>
      )}
    </Modal>
  );
}
