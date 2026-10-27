"use client";

import { useEffect, useRef, useState } from "react";
import { FileCheck2, RefreshCw } from "lucide-react";
import { api, idempotencyKey, message, type Conversation } from "@/lib/api";
import { Empty, ErrorNotice, Modal, useFeedback } from "@/components/ui";
import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

type ApprovedTemplate = {
  id: string;
  name: string;
  language: string;
  category: string;
  text: string;
  signature: string;
  supported: boolean;
  reason: string;
  buttons: string[];
  fields: {
    key: string;
    label: string;
    type: "text" | "url";
    max_length: number;
  }[];
  preview_parts?: { kind: string; text: string }[];
};

export function WhatsAppTemplateComposer({
  prefix,
  conversation,
  onSent,
}: {
  prefix: string;
  conversation: Conversation;
  onSent: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="button small secondary"
        onClick={() => setOpen(true)}
      >
        <FileCheck2 size={15} /> Send approved message
      </button>
      {open && (
        <TemplateDialog
          prefix={prefix}
          conversation={conversation}
          onSent={onSent}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function TemplateDialog({
  prefix,
  conversation,
  onSent,
  onClose,
}: {
  prefix: string;
  conversation: Conversation;
  onSent: () => Promise<void>;
  onClose: () => void;
}) {
  const [templates, setTemplates] = useState<ApprovedTemplate[]>([]);
  const [selected, setSelected] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [queued, setQueued] = useState(false);
  const feedback = useFeedback();
  const key = useRef(idempotencyKey());
  const path = `${prefix}/conversations/${conversation.id}/whatsapp-templates/`;
  useEffect(() => {
    const controller = new AbortController();
    api<{ results: ApprovedTemplate[] }>(
      path,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => {
        setTemplates(page.results);
        setSelected("");
        setValues({});
      })
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, revision]);
  const template = templates.find((item) => item.id === selected);
  const preview =
    template?.preview_parts
      ?.map((part) =>
        part.text.replace(
          /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g,
          (placeholder, name: string) =>
            values[`${part.kind}_${name}`] || placeholder,
        ),
      )
      .join("\n\n") ??
    template?.text.replace(
      /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g,
      (placeholder, name: string) =>
        values[`body_${name}`] || values[`header_${name}`] || placeholder,
    );
  return (
    <Modal title="Send approved WhatsApp message" onClose={onClose}>
      <p>
        Send to{" "}
        <strong>
          {conversation.lead.name ||
            conversation.lead.handle ||
            "this customer"}
        </strong>
        . Approved messages can be sent after the 24-hour reply window closes.
        Meta messaging charges may apply.
      </p>
      <ErrorNotice error={feedback.error} />
      <button
        type="button"
        className="button small secondary"
        disabled={loading || feedback.busy || queued}
        onClick={() => {
          setLoading(true);
          feedback.setError("");
          key.current = idempotencyKey();
          setRevision((value) => value + 1);
        }}
      >
        <RefreshCw size={14} /> Refresh approved messages
      </button>
      {loading ? (
        <p role="status">Loading approved messages…</p>
      ) : !templates.length ? (
        <Empty>
          No approved messages available. Create and approve a message in
          WhatsApp Manager, then refresh.
        </Empty>
      ) : (
        <ValidatedForm
          className="stack"
          fieldErrors={feedback.fieldErrors}
          validationTarget={feedback.validationTarget}
          onEdit={() => {
            feedback.setError("");
            key.current = idempotencyKey();
          }}
          onSubmit={async (event) => {
            event.preventDefault();
            if (!template?.supported || queued) return;
            const form = new FormData(event.currentTarget);
            await feedback.run(async () => {
              await api(
                path,
                "POST",
                {
                  name: template.name,
                  language: template.language,
                  signature: template.signature,
                  values,
                  consent_confirmed: form.get("consent_confirmed") === "on",
                },
                undefined,
                { "Idempotency-Key": key.current },
              );
              setQueued(true);
              await onSent();
              onClose();
            });
          }}
        >
          <label>
            Approved message
            <ValidatedSelect
              name="template"
              aria-label="Approved message"
              required
              value={selected}
              disabled={feedback.busy || queued}
              onChange={(event) => {
                setSelected(event.target.value);
                setValues({});
              }}
            >
              <option value="">Choose a message</option>
              {templates.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name.replace(/_/g, " ")} · {item.language}
                  {!item.supported ? " · unavailable" : ""}
                </option>
              ))}
            </ValidatedSelect>
          </label>
          {template && (
            <>
              {!template.supported && <p role="status">{template.reason}</p>}
              {template.supported &&
                template.fields.map((field) => (
                  <label key={field.key}>
                    {field.label}
                    <ValidatedInput
                      name={field.key}
                      aria-label={field.label}
                      type={field.type}
                      required
                      maxLength={field.max_length}
                      disabled={feedback.busy || queued}
                      value={values[field.key] || ""}
                      onChange={(event) =>
                        setValues((current) => ({
                          ...current,
                          [field.key]: event.target.value,
                        }))
                      }
                    />
                  </label>
                ))}
              <div className="card" aria-label="Message preview">
                <strong>Message preview</strong>
                <p style={{ whiteSpace: "pre-wrap" }}>{preview}</p>
                {template.buttons?.map((label, index) => (
                  <span key={index} className="pill">
                    {label}
                  </span>
                ))}
              </div>
              {template.supported && (
                <label className="inline">
                  <ValidatedInput
                    type="checkbox"
                    name="consent_confirmed"
                    required
                    disabled={feedback.busy || queued}
                  />{" "}
                  I confirm this customer agreed to receive these WhatsApp
                  messages.
                </label>
              )}
            </>
          )}
          <button
            className="button primary"
            disabled={
              feedback.busy ||
              queued ||
              Boolean(template && !template.supported)
            }
          >
            {queued
              ? "Message queued"
              : feedback.busy
                ? "Queuing message…"
                : "Send approved message"}
          </button>
        </ValidatedForm>
      )}
    </Modal>
  );
}
