"use client";

import { useEffect, useState } from "react";
import { Download, ExternalLink, FileText, Plus, Trash2 } from "lucide-react";
import { api, message } from "@/lib/api";
import {
  defaultForm,
  type LeadForm,
  type FormResponse,
} from "@/lib/portal-tools";
import { useWorkspace } from "@/lib/workspace";
import { FormAutomationActions } from "@/components/form-automation-actions";
import {
  ErrorNotice,
  SuccessNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  useFeedback,
} from "@/components/ui";

export default function FormsPage() {
  const { prefix, manager } = useWorkspace();
  const [forms, setForms] = useState<LeadForm[]>([]);
  const [draft, setDraft] = useState<
    (ReturnType<typeof defaultForm> & { id?: string }) | null
  >(null);
  const [responses, setResponses] = useState<FormResponse[] | null>(null);
  const [active, setActive] = useState<LeadForm | null>(null);
  const [loaded, setLoaded] = useState(false);
  const feedback = useFeedback();
  useEffect(() => {
    const controller = new AbortController();
    api<LeadForm[]>(`${prefix}/forms/`, "GET", undefined, controller.signal)
      .then(setForms)
      .catch((e) => {
        if (!controller.signal.aborted) feedback.setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);
  const publicUrl = (slug: string) =>
    `${typeof window === "undefined" ? "" : window.location.origin}/f/${slug}`;
  function exportResponses() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(responses, null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${active?.slug || "form"}-responses.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHeading
        eyebrow="Apps / Forms"
        title="Turn enquiries into contacts"
        text="Create a form, publish a shareable page, or embed it on your website. Responses are saved alongside the contact in your CRM."
        action={
          manager ? (
            <button
              className="button primary"
              onClick={() => setDraft(defaultForm())}
            >
              <Plus size={15} /> Create form
            </button>
          ) : undefined
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {!loaded && <p>Loading forms…</p>}
      {loaded && !forms.length && (
        <Panel title="Your first form">
          <FileText size={28} />
          <p>
            Start with a contact form, then add the questions your team needs.
          </p>
        </Panel>
      )}
      <div className="stats-grid">
        {forms.map((form) => (
          <Panel
            key={form.id}
            title={form.title}
            aside={<Pill>{form.published ? "Published" : "Draft"}</Pill>}
          >
            <p>{form.description}</p>
            <p>{form.submissions ?? 0} responses</p>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button
                className="button secondary small"
                onClick={() => setDraft(structuredClone(form))}
              >
                Edit form
              </button>
              <button
                className="button secondary small"
                disabled={feedback.busy}
                onClick={() =>
                  void feedback.run(async () => {
                    const rows = await api<FormResponse[]>(
                      `${prefix}/forms/${form.id}/submissions/`,
                    );
                    setActive(form);
                    setResponses(rows);
                  })
                }
              >
                Responses
              </button>
              {form.published && (
                <a
                  className="text-button"
                  href={`/f/${form.slug}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={14} /> Open
                </a>
              )}
            </div>
          </Panel>
        ))}
      </div>
      {draft && (
        <Modal
          title={draft.id ? "Edit form" : "Create form"}
          onClose={() => setDraft(null)}
        >
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void feedback.run(async () => {
                const saved = await api<LeadForm>(
                  `${prefix}/forms/${draft.id ? `${draft.id}/` : ""}`,
                  draft.id ? "PATCH" : "POST",
                  draft,
                );
                setForms((rows) => [
                  saved,
                  ...rows.filter((row) => row.id !== saved.id),
                ]);
                setDraft(null);
              }, "Form saved.");
            }}
          >
            <ErrorNotice error={feedback.error} />
            <label>
              Title
              <input
                required
                maxLength={120}
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </label>
            <label>
              Public address
              <input
                required
                pattern="[a-z0-9_-]+"
                maxLength={80}
                placeholder="contact-us"
                value={draft.slug}
                onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
              />
            </label>
            <label>
              Description
              <textarea
                maxLength={1000}
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
              />
            </label>
            <strong>Questions</strong>
            {draft.fields.map((field, index) => (
              <fieldset
                key={index}
                className="form-grid"
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 10,
                  padding: 12,
                }}
              >
                <legend>Question {index + 1}</legend>
                <label>
                  Field ID
                  <input
                    required
                    pattern="[a-z][a-z0-9_]*"
                    maxLength={40}
                    value={field.id}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.map((item, i) =>
                          i === index ? { ...item, id: e.target.value } : item,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Label
                  <input
                    required
                    maxLength={120}
                    value={field.label}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.map((item, i) =>
                          i === index
                            ? { ...item, label: e.target.value }
                            : item,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Type
                  <select
                    value={field.type}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.map((item, i) =>
                          i === index
                            ? {
                                ...item,
                                type: e.target.value as typeof field.type,
                                ...(e.target.value === "select"
                                  ? { options: ["Option 1"] }
                                  : {}),
                              }
                            : item,
                        ),
                      })
                    }
                  >
                    {["text", "textarea", "email", "tel", "select"].map(
                      (type) => (
                        <option key={type}>{type}</option>
                      ),
                    )}
                  </select>
                </label>
                {field.type === "select" && (
                  <label>
                    Options, one per line
                    <textarea
                      value={field.options?.join("\n") || ""}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          fields: draft.fields.map((item, i) =>
                            i === index
                              ? { ...item, options: e.target.value.split("\n") }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                )}
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={field.required}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.map((item, i) =>
                          i === index
                            ? { ...item, required: e.target.checked }
                            : item,
                        ),
                      })
                    }
                  />{" "}
                  Required
                </label>
                <button
                  type="button"
                  className="text-button"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      fields: draft.fields.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={13} /> Remove question
                </button>
              </fieldset>
            ))}
            <small>
              Keep a required email field with ID email. Use name as the ID of
              your name field for CRM capture.
            </small>
            <button
              type="button"
              className="button secondary"
              disabled={draft.fields.length >= 20}
              onClick={() =>
                setDraft({
                  ...draft,
                  fields: [
                    ...draft.fields,
                    {
                      id: `question_${draft.fields.length + 1}`,
                      label: "New question",
                      type: "text",
                      required: false,
                    },
                  ],
                })
              }
            >
              Add question
            </button>
            <FormAutomationActions
              prefix={prefix}
              actions={draft.submission_actions || []}
              onChange={(submission_actions) =>
                setDraft({ ...draft, submission_actions })
              }
            />
            <label>
              Consent statement
              <textarea
                required
                maxLength={500}
                value={draft.consent_text}
                onChange={(e) =>
                  setDraft({ ...draft, consent_text: e.target.value })
                }
              />
            </label>
            <label>
              Thank-you message
              <textarea
                required
                maxLength={500}
                value={draft.success_text}
                onChange={(e) =>
                  setDraft({ ...draft, success_text: e.target.value })
                }
              />
            </label>
            <label className="inline">
              <input
                type="checkbox"
                checked={draft.published}
                onChange={(e) =>
                  setDraft({ ...draft, published: e.target.checked })
                }
              />{" "}
              Publish form
            </label>
            {draft.id && (
              <label>
                Embed on your website
                <textarea
                  readOnly
                  rows={2}
                  value={`<iframe src="${publicUrl(draft.slug)}" title="${draft.title.replace(/[<>"&]/g, "")}" style="width:100%;height:720px;border:0" loading="lazy"></iframe>`}
                />
              </label>
            )}
            <button className="button primary" disabled={feedback.busy}>
              Save form
            </button>
          </form>
        </Modal>
      )}
      {responses && (
        <Modal
          title={`${active?.title} responses`}
          onClose={() => setResponses(null)}
        >
          <button className="button secondary small" onClick={exportResponses}>
            <Download size={14} /> Export responses
          </button>
          <p>
            Latest {responses.length} responses (up to 500). Consent is recorded
            with each submission.
          </p>
          {!responses.length && <p>No submissions yet.</p>}
          {responses.map((row) => (
            <details
              key={row.id}
              className="card"
              style={{ padding: 12, marginTop: 10 }}
            >
              <summary>
                {row.answers.name || row.answers.email} ·{" "}
                {new Date(row.created_at).toLocaleString()}
              </summary>
              <dl>
                {Object.entries(row.answers).map(([key, value]) => (
                  <div key={key}>
                    <dt>
                      <strong>{key}</strong>
                    </dt>
                    <dd style={{ whiteSpace: "pre-wrap" }}>{value}</dd>
                  </div>
                ))}
              </dl>
              <small>Consent: {row.consent_text}</small>
              {row.actions?.map((action) => (
                <p key={action.id}>
                  {action.operation.replaceAll("_", " ")} ·{" "}
                  {action.status.replaceAll("_", " ")}
                  {action.error
                    ? ` · ${action.error.replaceAll("_", " ")}`
                    : ""}
                  {action.accepted === false
                    ? " · Provider suppressed this recipient"
                    : ""}
                </p>
              ))}
              {row.action_errors?.map((error, index) => (
                <p role="alert" key={index}>
                  Action {error.action}: {error.error.replaceAll("_", " ")}
                </p>
              ))}
            </details>
          ))}
        </Modal>
      )}
    </>
  );
}
