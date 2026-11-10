"use client";

import { Plus, Trash2 } from "lucide-react";
import type { ConditionRule, FlowNodeData } from "@/lib/api";

/** What a condition rule can look at; mirrors backend automations/conditions.py. */
const SUBJECTS: { value: ConditionRule["subject"]; label: string }[] = [
  { value: "variable", label: "Flow variable" },
  { value: "field", label: "Contact field" },
  { value: "tag", label: "Contact tags" },
  { value: "stage", label: "Contact stage" },
  { value: "email", label: "Contact email" },
  { value: "channel", label: "Channel" },
];
const OPERATORS: { value: ConditionRule["operator"]; label: string }[] = [
  { value: "equals", label: "is" },
  { value: "not_equals", label: "is not" },
  { value: "contains", label: "contains" },
  { value: "not_contains", label: "does not contain" },
  { value: "starts_with", label: "starts with" },
  { value: "ends_with", label: "ends with" },
  { value: "is_set", label: "is set" },
  { value: "is_not_set", label: "is empty" },
  { value: "greater_than", label: "is greater than" },
  { value: "less_than", label: "is less than" },
];
const TAG_OPERATORS: { value: ConditionRule["operator"]; label: string }[] = [
  { value: "contains", label: "has tag" },
  { value: "not_contains", label: "does not have tag" },
  { value: "is_set", label: "has any tag" },
  { value: "is_not_set", label: "has no tags" },
];
const UNARY = new Set(["is_set", "is_not_set"]);

/** The condition's rules, reading flows saved before rules existed as one rule. */
export function conditionRules(data: FlowNodeData): ConditionRule[] {
  if (data.rules?.length) return data.rules;
  return [
    {
      subject: "variable",
      name: data.variable || "last_text",
      operator: "equals",
      value: data.equals ?? "",
    },
  ];
}

export function describeCondition(data: FlowNodeData) {
  const parts = conditionRules(data).map((rule) => {
    if (rule.subject === "tag") {
      return (
        (
          {
            contains: `has tag “${rule.value ?? ""}”`,
            not_contains: `lacks tag “${rule.value ?? ""}”`,
            is_set: "has any tag",
            is_not_set: "has no tags",
          } as Record<string, string>
        )[rule.operator] ?? "tag rule"
      );
    }
    const subject =
      rule.subject === "variable"
        ? `{{${rule.name || "last_text"}}}`
        : rule.subject === "field"
          ? rule.name || "field"
          : rule.subject;
    const op = OPERATORS.find((item) => item.value === rule.operator)?.label;
    return UNARY.has(rule.operator)
      ? `${subject} ${op}`
      : `${subject} ${op} “${rule.value ?? ""}”`;
  });
  return parts.join(data.match === "any" ? " or " : " and ");
}

export function ConditionRulesEditor({
  data,
  onChange,
}: {
  data: FlowNodeData;
  onChange: (patch: Partial<FlowNodeData>) => void;
}) {
  const rules = conditionRules(data);
  // Saving rules replaces the legacy variable/equals pair.
  const save = (next: ConditionRule[]) =>
    onChange({ rules: next, variable: undefined, equals: undefined });
  const update = (index: number, patch: Partial<ConditionRule>) =>
    save(rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));

  return (
    <div className="field">
      {rules.length > 1 && (
        <label className="field">
          Match
          <select
            value={data.match || "all"}
            onChange={(event) =>
              onChange({ match: event.target.value as "all" | "any" })
            }
          >
            <option value="all">All rules (and)</option>
            <option value="any">Any rule (or)</option>
          </select>
        </label>
      )}
      {rules.map((rule, index) => {
        const operators = rule.subject === "tag" ? TAG_OPERATORS : OPERATORS;
        return (
          <div
            className="card stack"
            key={index}
            style={{ padding: 8, gap: 6 }}
          >
            <div className="row between">
              <strong className="small">Rule {index + 1}</strong>
              {rules.length > 1 && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove rule ${index + 1}`}
                  onClick={() => save(rules.filter((_, i) => i !== index))}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
            <select
              aria-label="Check"
              value={rule.subject}
              onChange={(event) => {
                const subject = event.target.value as ConditionRule["subject"];
                update(index, {
                  subject,
                  operator: subject === "tag" ? "contains" : "equals",
                  name:
                    subject === "variable"
                      ? rule.name || "last_text"
                      : subject === "field"
                        ? rule.name || ""
                        : undefined,
                });
              }}
            >
              {SUBJECTS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            {(rule.subject === "variable" || rule.subject === "field") && (
              <input
                aria-label={
                  rule.subject === "variable" ? "Variable name" : "Field name"
                }
                placeholder={
                  rule.subject === "variable"
                    ? "e.g. reply or last_text"
                    : "e.g. budget"
                }
                maxLength={40}
                value={rule.name || ""}
                onChange={(event) =>
                  update(index, { name: event.target.value })
                }
              />
            )}
            <select
              aria-label="Comparison"
              value={rule.operator}
              onChange={(event) =>
                update(index, {
                  operator: event.target.value as ConditionRule["operator"],
                })
              }
            >
              {operators.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            {!UNARY.has(rule.operator) && (
              <input
                aria-label="Value"
                placeholder={rule.subject === "tag" ? "tag name" : "value"}
                maxLength={200}
                value={String(rule.value ?? "")}
                onChange={(event) =>
                  update(index, { value: event.target.value })
                }
              />
            )}
          </div>
        );
      })}
      {rules.length < 10 && (
        <button
          type="button"
          className="text-button"
          onClick={() =>
            save([
              ...rules,
              {
                subject: "variable",
                name: "last_text",
                operator: "contains",
                value: "",
              },
            ])
          }
        >
          <Plus size={14} /> Add rule
        </button>
      )}
      <span className="hint">
        Text comparisons ignore case. The “yes” path runs when the rules match.
      </span>
    </div>
  );
}

const UNITS = [
  { value: 1, label: "seconds" },
  { value: 60, label: "minutes" },
  { value: 3600, label: "hours" },
  { value: 86400, label: "days" },
];
export const MAX_WAIT_SECONDS = 30 * 86400;

function bestUnit(seconds: number) {
  return (
    [...UNITS]
      .reverse()
      .find((unit) => seconds % unit.value === 0 && seconds >= unit.value)
      ?.value ?? 1
  );
}

/** A number + unit input that stores whole seconds. */
export function DurationInput({
  label,
  seconds,
  min = 1,
  onChange,
}: {
  label: string;
  seconds: number;
  min?: number;
  onChange: (seconds: number) => void;
}) {
  const unit = bestUnit(seconds || min);
  return (
    <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
      <input
        type="number"
        aria-label={`${label} amount`}
        min={1}
        value={Math.max(1, Math.round((seconds || min) / unit))}
        onChange={(event) =>
          onChange(
            Math.min(
              MAX_WAIT_SECONDS,
              Math.max(1, Number(event.target.value) || 1) * unit,
            ),
          )
        }
        style={{ width: "50%" }}
      />
      <select
        aria-label={`${label} unit`}
        value={unit}
        onChange={(event) => {
          const next = Number(event.target.value);
          onChange(
            Math.min(
              MAX_WAIT_SECONDS,
              Math.max(1, Math.round((seconds || min) / unit)) * next,
            ),
          );
        }}
        style={{ width: "50%" }}
      >
        {UNITS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function formatDuration(seconds: number) {
  const unit = bestUnit(seconds);
  const label = UNITS.find((item) => item.value === unit)!.label;
  const amount = seconds / unit;
  return `${amount} ${amount === 1 ? label.slice(0, -1) : label}`;
}
