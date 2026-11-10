"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import {
  FIELD_TYPES,
  setCustomFields,
  type CustomFieldDef,
  type CustomFieldType,
} from "@/lib/custom-fields";
import { ErrorNotice, Modal, useFeedback } from "@/components/ui";

function keyFor(label: string, taken: Set<string>) {
  const base =
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .replace(/^[^a-z]+/, "")
      .slice(0, 36) || "field";
  let key = base;
  for (let n = 2; taken.has(key); n += 1) key = `${base}_${n}`;
  return key;
}

/** Define the workspace's typed contact fields. */
export function CustomFieldsEditor({
  prefix,
  fields,
  onClose,
  onSaved,
}: {
  prefix: string;
  fields: CustomFieldDef[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<CustomFieldDef[]>(fields);
  const [label, setLabel] = useState("");
  const [type, setType] = useState<CustomFieldType>("text");
  const feedback = useFeedback();

  const update = (index: number, patch: Partial<CustomFieldDef>) =>
    setDraft((list) =>
      list.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );

  async function save() {
    const result = await feedback.run(() =>
      api<{ fields: CustomFieldDef[] }>(`${prefix}/custom-fields/`, "PUT", {
        fields: draft,
      }),
    );
    if (!result) return;
    setCustomFields(prefix, result.fields);
    onSaved();
    onClose();
  }

  return (
    <Modal title="Contact fields" onClose={onClose}>
      <ErrorNotice error={feedback.error} />
      <div className="stack" style={{ gap: 8 }}>
        {!draft.length && (
          <p className="muted-text">
            No fields yet. Typed fields keep contact data clean and can be used
            in automation conditions.
          </p>
        )}
        {draft.map((item, index) => (
          <div
            key={item.key}
            className="card stack"
            style={{ padding: 8, gap: 6 }}
          >
            <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
              <input
                aria-label={`Label for ${item.key}`}
                maxLength={60}
                value={item.label}
                onChange={(event) =>
                  update(index, { label: event.target.value })
                }
                style={{ flex: 1 }}
              />
              <select
                aria-label={`Type for ${item.label}`}
                value={item.type}
                onChange={(event) =>
                  update(index, {
                    type: event.target.value as CustomFieldType,
                    options:
                      event.target.value === "select"
                        ? item.options?.length
                          ? item.options
                          : ["Option 1"]
                        : undefined,
                  })
                }
              >
                {FIELD_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove ${item.label}`}
                onClick={() =>
                  setDraft((list) => list.filter((_, i) => i !== index))
                }
              >
                <Trash2 size={14} />
              </button>
            </div>
            {item.type === "select" && (
              <input
                aria-label={`Options for ${item.label}`}
                placeholder="Options, separated by commas"
                value={(item.options || []).join(", ")}
                onChange={(event) =>
                  update(index, {
                    options: event.target.value
                      .split(",")
                      .map((option) => option.trim())
                      .filter(Boolean),
                  })
                }
              />
            )}
            <small className="muted-text">
              Key in automations: <span className="mono">{item.key}</span>
            </small>
          </div>
        ))}
        {draft.length < 30 && (
          <form
            className="row"
            style={{ gap: 6, flexWrap: "nowrap" }}
            onSubmit={(event) => {
              event.preventDefault();
              const name = label.trim();
              if (!name) return;
              const key = keyFor(name, new Set(draft.map((item) => item.key)));
              setDraft((list) => [
                ...list,
                {
                  key,
                  label: name,
                  type,
                  ...(type === "select" ? { options: ["Option 1"] } : {}),
                },
              ]);
              setLabel("");
            }}
          >
            <input
              aria-label="New field label"
              placeholder="New field, e.g. Budget"
              maxLength={60}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              style={{ flex: 1 }}
            />
            <select
              aria-label="New field type"
              value={type}
              onChange={(event) =>
                setType(event.target.value as CustomFieldType)
              }
            >
              {FIELD_TYPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button type="submit" className="button small secondary">
              <Plus size={14} /> Add
            </button>
          </form>
        )}
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
            Save fields
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** One typed input for a defined field; saves when the value is committed. */
export function CustomFieldInput({
  definition,
  value,
  disabled,
  onSave,
}: {
  definition: CustomFieldDef;
  value: string;
  disabled?: boolean;
  onSave: (value: string) => void;
}) {
  if (definition.type === "select") {
    return (
      <select
        aria-label={definition.label}
        value={value}
        disabled={disabled}
        onChange={(event) => onSave(event.target.value)}
      >
        <option value="">—</option>
        {(definition.options || []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      key={value}
      aria-label={definition.label}
      type={
        definition.type === "number"
          ? "number"
          : definition.type === "date"
            ? "date"
            : definition.type === "email"
              ? "email"
              : definition.type === "url"
                ? "url"
                : "text"
      }
      defaultValue={value}
      disabled={disabled}
      maxLength={500}
      onBlur={(event) => {
        if (event.target.value.trim() !== value)
          onSave(event.target.value.trim());
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") (event.target as HTMLInputElement).blur();
      }}
    />
  );
}
