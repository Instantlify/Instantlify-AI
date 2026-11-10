"use client";

import { EMAIL_TYPES, NON_INPUT_TYPES } from "@/lib/form-path";
import type { LeadForm } from "@/lib/portal-tools";
import { ValidatedInput, ValidatedSelect } from "./validated-form";

export function FormBranchEditor({
  form,
  onChange,
}: {
  form: Pick<LeadForm, "fields" | "branching">;
  onChange: (rules: NonNullable<LeadForm["branching"]>) => void;
}) {
  const rules = form.branching || [];
  const emailIndex = form.fields.findIndex(
    (field) => EMAIL_TYPES.includes(field.type) && field.required,
  );
  return (
    <fieldset>
      <legend>Conditional questions</legend>
      <p>
        When an answer matches exactly, jump to a later question or finish.
        Other answers continue in order. The email question must always be
        answered.
      </p>
      {rules.map((rule, index) => {
        const position = form.fields.findIndex(
          (field) => field.id === rule.field_id,
        );
        function update(patch: Partial<typeof rule>) {
          onChange(
            rules.map((item, i) =>
              i === index ? { ...item, ...patch } : item,
            ),
          );
        }
        return (
          <fieldset key={index}>
            <legend>Rule {index + 1}</legend>
            <label>
              When question
              <ValidatedSelect
                aria-label={`Rule ${index + 1} question`}
                value={rule.field_id}
                required
                onChange={(event) =>
                  update({ field_id: event.target.value, next_id: null })
                }
              >
                <option value="">Choose a question</option>
                {form.fields
                  .filter(
                    (field) =>
                      !["checkboxes", "file_upload", "signature"].includes(
                        field.type,
                      ),
                  )
                  .map((field) => (
                    <option key={field.id} value={field.id}>
                      {field.label}
                    </option>
                  ))}
              </ValidatedSelect>
            </label>
            <label>
              Answer equals
              <ValidatedInput
                aria-label={`Rule ${index + 1} answer`}
                value={rule.answer}
                maxLength={2000}
                required
                onChange={(event) => update({ answer: event.target.value })}
              />
            </label>
            <label>
              Continue to
              <ValidatedSelect
                aria-label={`Rule ${index + 1} destination`}
                value={rule.next_id ?? ""}
                onChange={(event) =>
                  update({ next_id: event.target.value || null })
                }
              >
                <option value="" disabled={position < emailIndex}>
                  End form
                </option>
                {form.fields.map((field, i) =>
                  i > position && !(position < emailIndex && i > emailIndex) ? (
                    <option key={field.id} value={field.id}>
                      {field.label}
                    </option>
                  ) : null,
                )}
              </ValidatedSelect>
            </label>
            <button
              type="button"
              className="text-button"
              onClick={() => onChange(rules.filter((_, i) => i !== index))}
            >
              Remove rule
            </button>
          </fieldset>
        );
      })}
      <button
        type="button"
        className="button secondary"
        disabled={rules.length >= 100}
        onClick={() =>
          onChange([
            ...rules,
            {
              field_id:
                form.fields[emailIndex]?.id ||
                form.fields.find(
                  (field) =>
                    ![
                      "checkboxes",
                      "file_upload",
                      "signature",
                      "contact_block",
                      ...NON_INPUT_TYPES,
                    ].includes(field.type),
                )?.id ||
                "",
              answer: "",
              next_id: null,
            },
          ])
        }
      >
        Add branching rule
      </button>
    </fieldset>
  );
}
