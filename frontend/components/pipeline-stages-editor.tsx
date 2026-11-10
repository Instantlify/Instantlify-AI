"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import {
  SYSTEM_STAGES,
  setPipelineStages,
  type PipelineStage,
} from "@/lib/stages";
import { ErrorNotice, Modal, useFeedback } from "@/components/ui";

function slug(label: string, taken: Set<string>) {
  const base =
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .replace(/^[^a-z]+/, "")
      .slice(0, 16) || "stage";
  let id = base;
  for (let n = 2; taken.has(id); n += 1) id = `${base}_${n}`.slice(0, 20);
  return id;
}

/** Rename, recolour, reorder, add and remove the workspace's pipeline stages. */
export function PipelineStagesEditor({
  prefix,
  stages,
  onClose,
  onSaved,
}: {
  prefix: string;
  stages: PipelineStage[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<PipelineStage[]>(stages);
  const [newLabel, setNewLabel] = useState("");
  const feedback = useFeedback();

  const update = (index: number, patch: Partial<PipelineStage>) =>
    setDraft((list) =>
      list.map((stage, i) => (i === index ? { ...stage, ...patch } : stage)),
    );
  const move = (index: number, by: number) =>
    setDraft((list) => {
      const next = [...list];
      const [item] = next.splice(index, 1);
      next.splice(index + by, 0, item);
      return next;
    });

  async function save() {
    const result = await feedback.run(() =>
      api<{ stages: PipelineStage[]; moved_contacts: number }>(
        `${prefix}/pipeline-stages/`,
        "PUT",
        { stages: draft },
      ),
    );
    if (!result) return;
    setPipelineStages(prefix, result.stages);
    onSaved();
    onClose();
  }

  return (
    <Modal title="Pipeline stages" onClose={onClose}>
      <ErrorNotice error={feedback.error} />
      <div className="stack" style={{ gap: 8 }}>
        {draft.map((stage, index) => (
          <div
            key={stage.id}
            className="row"
            style={{ gap: 6, flexWrap: "nowrap", alignItems: "center" }}
          >
            <input
              type="color"
              aria-label={`Colour for ${stage.label}`}
              value={stage.color}
              onChange={(event) => update(index, { color: event.target.value })}
              style={{ width: 36, padding: 0 }}
            />
            <input
              aria-label={`Name for stage ${index + 1}`}
              maxLength={40}
              value={stage.label}
              onChange={(event) => update(index, { label: event.target.value })}
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="icon-button"
              aria-label={`Move ${stage.label} up`}
              disabled={index === 0}
              onClick={() => move(index, -1)}
            >
              <ArrowUp size={14} />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label={`Move ${stage.label} down`}
              disabled={index === draft.length - 1}
              onClick={() => move(index, 1)}
            >
              <ArrowDown size={14} />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label={`Remove ${stage.label}`}
              title={
                SYSTEM_STAGES.has(stage.id)
                  ? "Used by bookings and payments; rename it instead"
                  : "Remove stage (its contacts move to No stage)"
              }
              disabled={SYSTEM_STAGES.has(stage.id)}
              onClick={() =>
                setDraft((list) => list.filter((_, i) => i !== index))
              }
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {draft.length < 20 && (
          <form
            className="row"
            style={{ gap: 6, flexWrap: "nowrap" }}
            onSubmit={(event) => {
              event.preventDefault();
              const label = newLabel.trim();
              if (!label) return;
              const id = slug(label, new Set(draft.map((stage) => stage.id)));
              setDraft((list) => [...list, { id, label, color: "#64748b" }]);
              setNewLabel("");
            }}
          >
            <input
              aria-label="New stage name"
              placeholder="New stage, e.g. Demo booked"
              maxLength={40}
              value={newLabel}
              onChange={(event) => setNewLabel(event.target.value)}
              style={{ flex: 1 }}
            />
            <button type="submit" className="button small secondary">
              <Plus size={14} /> Add
            </button>
          </form>
        )}
        <p className="muted-text small">
          No stage, Booked, Won and Lost are set automatically by bookings and
          payments, so they can be renamed but not removed.
        </p>
        <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="button primary"
            disabled={feedback.busy}
            onClick={save}
          >
            Save stages
          </button>
        </div>
      </div>
    </Modal>
  );
}
