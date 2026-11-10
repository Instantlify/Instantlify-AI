"use client";

import {
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "@/components/validated-form";

import { useEffect, useState } from "react";
import { apiPages, message, type Integration } from "@/lib/api";
import type { FormAction } from "@/lib/portal-tools";
import { ErrorNotice } from "@/components/ui";

const providers = {
  send_email: ["gmail", "outlook", "zorromail"],
  sync_lead: [
    "airtable",
    "notion",
    "gohighlevel",
    "attio",
    "google_sheets",
    "mailerlite",
    "klaviyo",
    "systeme_io",
    "mailchimp",
    "beehiiv",
    "kit",
  ],
  notify: ["slack"],
  webhook: ["n8n", "make", "webhook"],
};
const labels = {
  send_email: "Send email confirmation",
  sync_lead: "Sync CRM contact",
  notify: "Send team notification",
  webhook: "Trigger webhook automation",
};
export function FormAutomationActions({
  prefix,
  actions,
  onChange,
}: {
  prefix: string;
  actions: FormAction[];
  onChange: (rows: FormAction[]) => void;
}) {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    apiPages<Integration>(`${prefix}/integrations/`, controller.signal)
      .then(setIntegrations)
      .catch((reason) => {
        if (!controller.signal.aborted) setError(message(reason));
      });
    return () => controller.abort();
  }, [prefix]);
  const active = integrations.filter(
    (item) => item.enabled && item.status === "active" && item.configured,
  );
  const patch = (index: number, value: Partial<FormAction>) =>
    onChange(
      actions.map((item, i) => (i === index ? { ...item, ...value } : item)),
    );
  const availableOperation = (
    Object.keys(providers) as FormAction["operation"][]
  ).find((operation) =>
    active.some((item) => providers[operation].includes(item.provider)),
  );
  return (
    <section className="form-grid" aria-label="Form submission automations">
      <h3>When this form is submitted</h3>
      <p>
        Run up to five actions for each new consented response. Use {"{{name}}"}
        , {"{{email}}"} or other field IDs in message text. Existing contact
        opt-outs are respected.
      </p>
      <ErrorNotice error={error} />
      {actions.map((action, index) => (
        <fieldset
          key={index}
          className="form-grid"
          style={{
            padding: 14,
            border: "1px solid var(--border-light)",
            borderRadius: 10,
          }}
        >
          <legend>Action {index + 1}</legend>
          <label>
            Action type
            <ValidatedSelect
              value={action.operation}
              aria-label={`Action ${index + 1} type`}
              onChange={(event) => {
                const operation = event.target.value as FormAction["operation"];
                patch(index, {
                  operation,
                  integration_id:
                    active.find((item) =>
                      providers[operation].includes(item.provider),
                    )?.id || "",
                });
              }}
            >
              {(Object.keys(labels) as FormAction["operation"][]).map(
                (operation) => (
                  <option value={operation} key={operation}>
                    {labels[operation]}
                  </option>
                ),
              )}
            </ValidatedSelect>
          </label>
          <label>
            Connected integration
            <ValidatedSelect
              required
              value={action.integration_id}
              aria-label={`Action ${index + 1} integration`}
              onChange={(event) =>
                patch(index, { integration_id: event.target.value })
              }
            >
              <option value="">Choose an integration</option>
              {active
                .filter((item) =>
                  providers[action.operation].includes(item.provider),
                )
                .map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.provider.replaceAll("_", " ")}
                  </option>
                ))}
            </ValidatedSelect>
          </label>
          {action.operation === "send_email" && (
            <>
              <p>
                The confirmation is sent to the email address supplied in this
                form.
              </p>
              <label>
                Email subject
                <ValidatedInput
                  required
                  maxLength={200}
                  value={action.subject || ""}
                  onChange={(event) =>
                    patch(index, { subject: event.target.value })
                  }
                />
              </label>
            </>
          )}
          {["send_email", "notify"].includes(action.operation) && (
            <label>
              Message text
              <ValidatedTextarea
                required
                rows={4}
                maxLength={2000}
                value={action.text || ""}
                onChange={(event) => patch(index, { text: event.target.value })}
              />
            </label>
          )}
          {action.operation === "webhook" && (
            <small>
              The webhook receives the form ID, submission ID, lead ID, answers
              and recorded consent statement.
            </small>
          )}
          <button
            type="button"
            className="text-button"
            onClick={() => onChange(actions.filter((_, i) => i !== index))}
          >
            Remove action {index + 1}
          </button>
        </fieldset>
      ))}
      {!availableOperation && (
        <small>
          Connect an email, CRM, Slack or webhook integration to enable
          submission actions.
        </small>
      )}
      <button
        type="button"
        className="button secondary small"
        disabled={actions.length >= 5 || !availableOperation}
        onClick={() => {
          if (availableOperation)
            onChange([
              ...actions,
              {
                operation: availableOperation,
                integration_id: active.find((item) =>
                  providers[availableOperation].includes(item.provider),
                )!.id,
                subject: "",
                text: "",
              },
            ]);
        }}
      >
        Add submission action
      </button>
    </section>
  );
}
