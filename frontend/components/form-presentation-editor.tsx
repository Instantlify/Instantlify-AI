"use client";

import type { LeadForm } from "@/lib/portal-tools";
import { ValidatedInput, ValidatedSelect } from "./validated-form";

export function FormPresentationEditor({
  form,
  onChange,
}: {
  form: Omit<LeadForm, "id">;
  onChange: (patch: Partial<LeadForm>) => void;
}) {
  return (
    <fieldset>
      <legend>Appearance and completion</legend>
      {(["primary", "background", "text"] as const).map((key) => (
        <label key={key}>
          {key === "primary"
            ? "Button color"
            : key === "background"
              ? "Form background"
              : "Text color"}
          <ValidatedInput
            type="color"
            value={
              form.theme?.[key] ||
              { primary: "#10244a", background: "#ffffff", text: "#0c1b3a" }[
                key
              ]
            }
            onChange={(event) =>
              onChange({ theme: { ...form.theme, [key]: event.target.value } })
            }
          />
        </label>
      ))}
      <label>
        Button alignment
        <ValidatedSelect
          value={form.button_align || "left"}
          onChange={(event) =>
            onChange({
              button_align: event.target.value as LeadForm["button_align"],
            })
          }
        >
          <option value="left">Left</option>
          <option value="center">Center</option>
          <option value="right">Right</option>
        </ValidatedSelect>
      </label>
      <label>
        Redirect after submission
        <ValidatedInput
          name="redirect_url"
          type="url"
          placeholder="https://example.com/thank-you"
          value={form.redirect_url || ""}
          onChange={(event) => onChange({ redirect_url: event.target.value })}
        />
      </label>
      <label>
        Contact tags, separated by commas
        <ValidatedInput
          name="submission_tags"
          value={form.submission_tags?.join(", ") || ""}
          onChange={(event) =>
            onChange({
              submission_tags: event.target.value
                .split(",")
                .map((tag) => tag.trim()),
            })
          }
        />
      </label>
      <label className="inline">
        <ValidatedInput
          type="checkbox"
          checked={form.closed || false}
          onChange={(event) => onChange({ closed: event.target.checked })}
        />
        Close form to new responses
      </label>
    </fieldset>
  );
}
