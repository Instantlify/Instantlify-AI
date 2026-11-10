"use client";

import type {
  FormAnswer,
  FormContactAnswer,
  FormField,
} from "@/lib/portal-tools";
import { ValidatedInput } from "./validated-form";

export function FormContactQuestion({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value?: FormAnswer;
  onChange: (value: FormContactAnswer) => void;
}) {
  const contact: FormContactAnswer =
    value && typeof value === "object" && "first_name" in value
      ? value
      : { first_name: "", last_name: "", email: "", phone: "" };
  return (
    <fieldset>
      <legend>
        {field.label}
        {field.required ? " *" : ""}
      </legend>
      {(["first_name", "last_name", "email", "phone"] as const)
        .filter((key) => key !== "phone" || field.include_phone)
        .map((key) => (
          <label key={key}>
            {
              {
                first_name: "First name",
                last_name: "Last name",
                email: "Email address",
                phone: "Phone number",
              }[key]
            }
            <ValidatedInput
              name={`answer:${field.id}.${key}`}
              type={
                key === "email" ? "email" : key === "phone" ? "tel" : "text"
              }
              required={field.required && key !== "phone"}
              maxLength={key === "email" ? 254 : 150}
              value={contact[key]}
              onChange={(event) =>
                onChange({ ...contact, [key]: event.target.value })
              }
            />
          </label>
        ))}
    </fieldset>
  );
}
