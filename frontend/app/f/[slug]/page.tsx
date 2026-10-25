"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, message } from "@/lib/api";
import type { LeadForm } from "@/lib/portal-tools";

export default function PublicFormPage() {
  const { slug } = useParams<{ slug: string }>();
  const [form, setForm] = useState<LeadForm | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const requestId = useRef<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api<LeadForm>(
      `/api/public/forms/${slug}/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setForm)
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [slug]);
  return (
    <main style={{ maxWidth: 620, margin: "48px auto", padding: "0 24px" }}>
      {loading ? (
        <p>Loading form…</p>
      ) : !form ? (
        <p role="alert">This form is unavailable.</p>
      ) : (
        <section className="card" style={{ padding: 28 }}>
          <span className="eyebrow">Get in touch</span>
          <h1>{form.title}</h1>
          <p style={{ whiteSpace: "pre-wrap" }}>{form.description}</p>
          {success ? (
            <p role="status">{success}</p>
          ) : (
            <form
              className="form-grid"
              onSubmit={async (event) => {
                event.preventDefault();
                if (busy) return;
                const values = new FormData(event.currentTarget);
                requestId.current ||= crypto.randomUUID();
                setBusy(true);
                setError("");
                try {
                  const response = await api<{ message: string }>(
                    `/api/public/forms/${slug}/`,
                    "POST",
                    {
                      request_id: requestId.current,
                      answers: Object.fromEntries(
                        form.fields.map((field) => [
                          field.id,
                          values.get(`answer:${field.id}`) || "",
                        ]),
                      ),
                      consent: values.get("consent") === "on",
                      website: values.get("website"),
                      ref:
                        new URLSearchParams(window.location.search).get(
                          "ref",
                        ) || "",
                    },
                  );
                  setSuccess(response.message);
                } catch (err) {
                  setError(message(err));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {form.fields.map((field) => (
                <label key={field.id}>
                  {field.label}
                  {field.required ? " *" : ""}
                  {field.type === "textarea" ? (
                    <textarea
                      name={`answer:${field.id}`}
                      required={field.required}
                      maxLength={2000}
                      rows={4}
                    />
                  ) : field.type === "select" ? (
                    <select
                      name={`answer:${field.id}`}
                      required={field.required}
                    >
                      <option value="">Choose an option</option>
                      {field.options?.map((option) => (
                        <option key={option}>{option}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      name={`answer:${field.id}`}
                      type={field.type}
                      required={field.required}
                      maxLength={field.type === "email" ? 254 : 2000}
                    />
                  )}
                </label>
              ))}
              <div
                style={{
                  position: "absolute",
                  left: -10000,
                  width: 1,
                  height: 1,
                  overflow: "hidden",
                }}
                aria-hidden="true"
              >
                <label>
                  Website
                  <input name="website" tabIndex={-1} autoComplete="off" />
                </label>
              </div>
              <label className="inline" style={{ alignItems: "flex-start" }}>
                <input
                  name="consent"
                  type="checkbox"
                  required
                  style={{ width: "auto", marginTop: 4 }}
                />
                {form.consent_text}
              </label>
              {error && <p role="alert">{error}</p>}
              <button className="button primary" disabled={busy}>
                {busy ? "Submitting…" : "Send response"}
              </button>
            </form>
          )}
        </section>
      )}
    </main>
  );
}
