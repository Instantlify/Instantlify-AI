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
import { FORM_TYPES, EMAIL_TYPES, NON_INPUT_TYPES } from "@/lib/form-path";
import { FormPresentationEditor } from "@/components/form-presentation-editor";
import { FormBranchEditor } from "@/components/form-branch-editor";
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
    draft?.capture_contacts === false
      ? -1
      : (draft?.fields.findIndex(
          (field) => EMAIL_TYPES.includes(field.type) && field.required,
        ) ?? -1);
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
            aside={
              <Pill>
                {form.closed
                  ? "Closed"
                  : form.published
                    ? "Published"
                    : "Draft"}
              </Pill>
            }
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
              {form.published && !form.closed && (
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
                if (["select", "checkboxes"].includes(field.type)) {
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
                draft.capture_contacts !== false &&
                !draft.fields.some(
                  (field) => EMAIL_TYPES.includes(field.type) && field.required,
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
                    submission_tags: draft.submission_tags
                      ?.map((tag) => tag.trim())
                      .filter(Boolean),
                    fields: draft.fields.map((field) =>
                      ["select", "checkboxes"].includes(field.type)
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
                                required: NON_INPUT_TYPES.includes(
                                  e.target.value,
                                )
                                  ? false
                                  : item.required,
                                ...(["select", "checkboxes"].includes(
                                  e.target.value,
                                )
                                  ? { options: ["Option 1"] }
                                  : {}),
                              }
                            : item,
                        ),
                      })
                    }
                  >
                    {Object.entries(FORM_TYPES).map(([type, label]) => (
                      <option key={type} value={type}>
                        {label}
                      </option>
                    ))}
                  </ValidatedSelect>
                </label>
                {field.type === "contact_block" && (
                  <label className="inline">
                    <ValidatedInput
                      type="checkbox"
                      checked={field.include_phone || false}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          fields: draft.fields.map((item, i) =>
                            i === index
                              ? { ...item, include_phone: event.target.checked }
                              : item,
                          ),
                        })
                      }
                    />
                    Include phone number
                  </label>
                )}
                {field.type === "cover_card" && (
                  <label>
                    Welcome text
                    <ValidatedTextarea
                      value={field.description || ""}
                      maxLength={1000}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          fields: draft.fields.map((item, i) =>
                            i === index
                              ? { ...item, description: event.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                )}
                {["calendly", "calcom", "tidycal"].includes(field.type) && (
                  <label>
                    Public booking address
                    <ValidatedInput
                      type="url"
                      required
                      value={field.booking_url || ""}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          fields: draft.fields.map((item, i) =>
                            i === index
                              ? { ...item, booking_url: event.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                )}
                {["number", "rating", "opinion_scale"].includes(field.type) && (
                  <div className="row">
                    {(["min", "max"] as const).map((bound) => (
                      <label key={bound}>
                        {bound === "min" ? "Minimum" : "Maximum"}
                        <ValidatedInput
                          type="number"
                          name={`fields.${index}.${bound}`}
                          step={field.type === "number" ? "any" : "1"}
                          value={field[bound] ?? ""}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              fields: draft.fields.map((item, i) =>
                                i === index
                                  ? {
                                      ...item,
                                      [bound]:
                                        event.target.value === ""
                                          ? undefined
                                          : Number(event.target.value),
                                    }
                                  : item,
                              ),
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                )}
                {["select", "checkboxes"].includes(field.type) && (
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
                    disabled={
                      index === requiredEmailIndex ||
                      NON_INPUT_TYPES.includes(field.type)
                    }
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
            <label className="inline">
              <ValidatedInput
                type="checkbox"
                checked={draft.capture_contacts !== false}
                onChange={(event) =>
                  setDraft({ ...draft, capture_contacts: event.target.checked })
                }
              />
              Save respondents as CRM contacts
            </label>
            <small>
              CRM capture requires an email or contact-details question marked
              as required. Turn it off for a survey without contact details.
            </small>
            <button
              type="button"
              className="button secondary"
              disabled={draft.fields.length >= 100}
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
            <FormPresentationEditor
              form={draft}
              onChange={(patch) => setDraft({ ...draft, ...patch })}
            />
            <FormBranchEditor
              form={draft}
              onChange={(branching) => setDraft({ ...draft, branching })}
            />
            <FormAutomationActions
              prefix={prefix}
              actions={draft.submission_actions || []}
              automationId={draft.automation_id}
              onAutomationChange={(automation_id) =>
                setDraft({ ...draft, automation_id })
              }
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
          <div className="row">
            <a
              className="button secondary small"
              href={`${prefix}/forms/${active?.id}/submissions/export/`}
            >
              <Download size={14} /> Export all responses (JSON)
            </a>
            <a
              className="button secondary small"
              href={`${prefix}/forms/${active?.id}/submissions/export/?file_type=csv`}
            >
              <Download size={14} /> Export all responses (CSV)
            </a>
          </div>
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
                {String(row.answers.name || row.answers.email || "Response")} ·{" "}
                {new Date(row.created_at).toLocaleString()}
              </summary>
              <dl>
                {Object.entries(row.answers).map(([key, value]) => (
                  <div key={key}>
                    <dt>
                      <strong>{key}</strong>
                    </dt>
                    <dd style={{ whiteSpace: "pre-wrap" }}>
                      {Array.isArray(value) ? (
                        value.join(", ")
                      ) : typeof value === "object" ? (
                        "name" in value ? (
                          value.download_url ? (
                            <a href={value.download_url}>{value.name}</a>
                          ) : (
                            value.name
                          )
                        ) : (
                          Object.entries(value)
                            .filter(([, item]) => item)
                            .map(([key, item]) => (
                              <div key={key}>
                                {key.replaceAll("_", " ")}: {item}
                              </div>
                            ))
                        )
                      ) : (
                        value
                      )}
                    </dd>
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
              {row.workflow_status && (
                <p>
                  Workflow: {row.workflow_status.replaceAll("_", " ")}
                  {row.workflow_error ? ` — ${row.workflow_error}` : ""}
                </p>
              )}
              {!!row.workflow_trace?.length && (
                <details>
                  <summary>Workflow history</summary>
                  <ol>
                    {row.workflow_trace.map((entry, index) => (
                      <li key={index}>
                        {entry.node_id} · {entry.kind.replaceAll("_", " ")} ·
                        step {entry.step} ·{" "}
                        {new Date(entry.at).toLocaleString()}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
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
