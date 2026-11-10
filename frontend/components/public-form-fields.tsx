"use client";

import type { FormAnswer, FormField } from "@/lib/portal-tools";
import { FormFileQuestion } from "./form-file-question";
import { FormContactQuestion } from "./form-contact-question";
import {
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "./validated-form";

export function PublicFormFields({
  fields,
  answers,
  onChange,
}: {
  fields: FormField[];
  answers: Record<string, FormAnswer>;
  onChange: (id: string, value: FormAnswer) => void;
}) {
  return fields.map((field) => {
    const name = `answer:${field.id}`;
    const raw = answers[field.id];
    const value = typeof raw === "string" ? raw : "";
    if (field.type === "contact_block")
      return (
        <FormContactQuestion
          key={field.id}
          field={field}
          value={raw}
          onChange={(value) => onChange(field.id, value)}
        />
      );
    if (field.type === "cover_card")
      return (
        <section key={field.id}>
          <h2>{field.label}</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{field.description}</p>
        </section>
      );
    if (["calendly", "calcom", "tidycal"].includes(field.type))
      return (
        <section key={field.id}>
          <h2>{field.label}</h2>
          <iframe
            title={field.label}
            src={field.booking_url}
            width="100%"
            height={400}
            style={{ border: 0 }}
            loading="lazy"
          />
          <p>
            Booking is completed with the calendar provider. Submitting this
            form does not confirm an appointment.
          </p>
          <a href={field.booking_url} target="_blank" rel="noreferrer">
            Open booking page
          </a>
        </section>
      );
    if (field.type === "file_upload" || field.type === "signature")
      return (
        <FormFileQuestion
          key={field.id}
          field={field}
          value={raw}
          onChange={(value) => onChange(field.id, value)}
        />
      );
    if (field.type === "checkboxes") {
      const selected = Array.isArray(raw) ? raw : [];
      return (
        <fieldset key={field.id}>
          <legend>
            {field.label}
            {field.required ? " *" : ""}
          </legend>
          {field.options?.map((option, index) => (
            <label className="inline" key={option}>
              <ValidatedInput
                name={name}
                type="checkbox"
                value={option}
                checked={selected.includes(option)}
                required={
                  field.required && selected.length === 0 && index === 0
                }
                onChange={(event) =>
                  onChange(
                    field.id,
                    event.target.checked
                      ? [...selected, option]
                      : selected.filter((v) => v !== option),
                  )
                }
              />
              {option}
            </label>
          ))}
        </fieldset>
      );
    }
    const choices =
      field.type === "yes_no"
        ? [
            { value: "yes", label: "Yes" },
            { value: "no", label: "No" },
          ]
        : field.type === "rating" || field.type === "opinion_scale"
          ? Array.from(
              {
                length:
                  (field.max ?? (field.type === "rating" ? 5 : 10)) -
                  (field.min ?? (field.type === "rating" ? 1 : 0)) +
                  1,
              },
              (_, i) => {
                const v = String(
                  i + (field.min ?? (field.type === "rating" ? 1 : 0)),
                );
                return {
                  value: v,
                  label: field.type === "rating" ? `${v} ★` : v,
                };
              },
            )
          : field.options?.map((v) => ({ value: v, label: v }));
    return (
      <label key={field.id}>
        {field.label}
        {field.required ? " *" : ""}
        {field.type === "textarea" ? (
          <ValidatedTextarea
            name={name}
            required={field.required}
            maxLength={2000}
            rows={4}
            value={value}
            onChange={(e) => onChange(field.id, e.target.value)}
          />
        ) : ["select", "yes_no", "rating", "opinion_scale"].includes(
            field.type,
          ) ? (
          <ValidatedSelect
            name={name}
            required={field.required}
            value={value}
            onChange={(e) => onChange(field.id, e.target.value)}
          >
            <option value="">Choose an option</option>
            {choices?.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </ValidatedSelect>
        ) : (
          <ValidatedInput
            name={name}
            type={
              field.type === "contact_email"
                ? "email"
                : field.type === "contact_phone"
                  ? "tel"
                  : field.type.startsWith("contact_")
                    ? "text"
                    : field.type
            }
            required={field.required}
            maxLength={field.type === "email" ? 254 : 2000}
            min={field.min}
            max={field.max}
            step={field.type === "number" ? "any" : undefined}
            value={value}
            onChange={(e) => onChange(field.id, e.target.value)}
          />
        )}
      </label>
    );
  });
}
