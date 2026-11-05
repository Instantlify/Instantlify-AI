"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
  ValidationError,
} from "@/components/validated-form";

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
  const requiredEmailIndex =
    draft?.fields.findIndex(
      (field) =>
        field.id === "email" && field.type === "email" && field.required,
    ) ?? -1;
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
              onClick={() => {
                const form = defaultForm();
                let slug = "contact-us";
                let suffix = 2;
                while (forms.some((item) => item.slug === slug))
                  slug = `contact-us-${suffix++}`;
                feedback.setError("");
                setDraft({ ...form, slug });
              }}
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
            <p>
              {form.submissions ?? 0}{" "}
              {form.submissions === 1 ? "response" : "responses"}
            </p>
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
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            className="form-grid"
            validate={() => {
              const errors: Record<string, string> = {};
              const names = new Set<string>();
              if (!draft.fields.length)
                errors.fields =
                  "Add at least an Email address question before saving.";
              draft.fields.forEach((field, index) => {
                if (names.has(field.id))
                  errors[`fields.${index}.id`] =
                    "This answer name is already used by another question. Choose a different name.";
                names.add(field.id);
                if (field.type === "select") {
                  const options = (field.options || [])
                    .map((option) => option.trim())
                    .filter(Boolean);
                  if (!options.length)
                    errors[`fields.${index}.options`] =
                      "Add at least one choice, with each choice on its own line.";
                  else if (
                    options.length > 30 ||
                    options.some((option) => option.length > 120)
                  )
                    errors[`fields.${index}.options`] =
                      "Use up to 30 choices, with no more than 120 characters each.";
                }
              });
              if (
                !draft.fields.some(
                  (field) =>
                    field.id === "email" &&
                    field.type === "email" &&
                    field.required,
                )
              )
                errors.fields =
                  "Keep an Email address question marked as required so responses can be saved to your contacts.";
              return errors;
            }}
            onSubmit={(event) => {
              event.preventDefault();
              void feedback.run(async () => {
                const saved = await api<LeadForm>(
                  `${prefix}/forms/${draft.id ? `${draft.id}/` : ""}`,
                  draft.id ? "PATCH" : "POST",
                  {
                    ...draft,
                    fields: draft.fields.map((field) =>
                      field.type === "select"
                        ? {
                            ...field,
                            options: field.options
                              ?.map((option) => option.trim())
                              .filter(Boolean),
                          }
                        : field,
                    ),
                  },
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
              <ValidatedInput
                name="title"
                required
                maxLength={120}
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </label>
            <label>
              Public address
              <ValidatedInput
                name="slug"
                aria-label="Public address"
                aria-describedby="form-address-help"
                data-validation-hint="Use lowercase letters, numbers and hyphens, such as contact-us."
                required
                pattern="[a-z0-9_\-]+"
                maxLength={80}
                placeholder="contact-us"
                value={draft.slug}
                onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
              />
              <small id="form-address-help" className="field-hint">
                This is the last part of your form’s web address. Example: /f/
                {draft.slug || "contact-us"}
              </small>
            </label>
            <label>
              Description
              <ValidatedTextarea
                name="description"
                maxLength={1000}
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
              />
            </label>
            <strong>Questions</strong>
            <ValidationError name="fields" />
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
                <details>
                  <summary>Advanced answer settings</summary>
                  <label>
                    Answer name
                    <ValidatedInput
                      name={`fields.${index}.id`}
                      disabled={index === requiredEmailIndex}
                      data-validation-hint="Start with a lowercase letter, then use lowercase letters, numbers or underscores. Each question needs a different name."
                      required
                      pattern="[a-z][a-z0-9_]*"
                      maxLength={40}
                      value={field.id}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          fields: draft.fields.map((item, i) =>
                            i === index
                              ? { ...item, id: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                    <small className="field-hint">
                      Used to match this answer in your saved contacts and
                      follow-up actions. You can usually keep the suggested
                      name.
                    </small>
                  </label>
                </details>
                <label>
                  Question text
                  <ValidatedInput
                    name={`fields.${index}.label`}
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
                  <ValidatedSelect
                    name="type"
                    disabled={index === requiredEmailIndex}
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
                        <option key={type} value={type}>
                          {
                            (
                              {
                                text: "Short answer",
                                textarea: "Long answer",
                                email: "Email address",
                                tel: "Phone number",
                                select: "Dropdown choices",
                              } as Record<string, string>
                            )[type]
                          }
                        </option>
                      ),
                    )}
                  </ValidatedSelect>
                </label>
                {field.type === "select" && (
                  <label>
                    Options, one per line
                    <ValidatedTextarea
                      name={`fields.${index}.options`}
                      required
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
                  <ValidatedInput
                    type="checkbox"
                    disabled={index === requiredEmailIndex}
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
                  disabled={index === requiredEmailIndex}
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
              An email address is required so each response can be saved to your
              contacts. Answer names are managed for you under Advanced answer
              settings.
            </small>
            <button
              type="button"
              className="button secondary"
              disabled={draft.fields.length >= 20}
              onClick={() => {
                let number = draft.fields.length + 1;
                while (
                  draft.fields.some(
                    (field) => field.id === `question_${number}`,
                  )
                )
                  number += 1;
                setDraft({
                  ...draft,
                  fields: [
                    ...draft.fields,
                    {
                      id: `question_${number}`,
                      label: "New question",
                      type: "text",
                      required: false,
                    },
                  ],
                });
              }}
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
              <span className="field-label-inline">
                Consent statement
                <span className="field-required" aria-hidden="true" />
              </span>
              <ValidatedTextarea
                name="consent_text"
                required
                maxLength={500}
                value={draft.consent_text}
                onChange={(e) =>
                  setDraft({ ...draft, consent_text: e.target.value })
                }
              />
            </label>
            <label>
              <span className="field-label-inline">
                Thank-you message
                <span className="field-required" aria-hidden="true" />
              </span>
              <ValidatedTextarea
                name="success_text"
                required
                maxLength={500}
                value={draft.success_text}
                onChange={(e) =>
                  setDraft({ ...draft, success_text: e.target.value })
                }
              />
            </label>
            <label className="inline">
              <ValidatedInput
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
                <ValidatedTextarea
                  readOnly
                  rows={2}
                  value={`<iframe src="${publicUrl(draft.slug)}" title="${draft.title.replace(/[<>"&]/g, "")}" style="width:100%;height:720px;border:0" loading="lazy"></iframe>`}
                />
              </label>
            )}
            <button className="button primary" disabled={feedback.busy}>
              Save form
            </button>
          </ValidatedForm>
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
            Latest {responses.length}{" "}
            {responses.length === 1 ? "response" : "responses"} (up to 500).
            Consent is recorded with each submission.
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
