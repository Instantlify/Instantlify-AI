"use client";

import { ValidatedForm, ValidatedInput } from "@/components/validated-form";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import "@/components/public-form.css";
import { colorContrast } from "@/lib/workspace-theme";
import { api, message } from "@/lib/api";
import { PublicFormFields } from "@/components/public-form-fields";
import { visibleFormFields, NON_INPUT_TYPES } from "@/lib/form-path";
import type { FormAnswer, LeadForm } from "@/lib/portal-tools";
import { useT } from "@/lib/i18n";

export default function PublicFormPage() {
  const t = useT();
  const { slug } = useParams<{ slug: string }>();
  const [form, setForm] = useState<LeadForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, FormAnswer>>({});
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
        <p>{t("form.loading")}</p>
      ) : !form ? (
        <p role="alert">{t("form.unavailable")}</p>
      ) : (
        <section
          className="card public-lead-form"
          style={
            {
              padding: 28,
              "--form-background": form.theme?.background || "#ffffff",
              "--form-text": form.theme?.text || "#0c1b3a",
              "--form-primary": form.theme?.primary || "#10244a",
              "--form-button-text":
                colorContrast(form.theme?.primary || "#10244a", "#0c1b3a") >=
                4.5
                  ? "#0c1b3a"
                  : colorContrast(
                        form.theme?.primary || "#10244a",
                        "#ffffff",
                      ) >= 4.5
                    ? "#ffffff"
                    : "#000000",
            } as CSSProperties
          }
        >
          <span className="eyebrow">Get in touch</span>
          <h1>{form.title}</h1>
          <p style={{ whiteSpace: "pre-wrap" }}>{form.description}</p>
          {success ? (
            <p role="status">{success}</p>
          ) : (
            <ValidatedForm
              className="form-grid"
              onSubmit={async (event) => {
                event.preventDefault();
                if (busy) return;
                const values = new FormData(event.currentTarget);
                requestId.current ||= crypto.randomUUID();
                setBusy(true);
                setError("");
                try {
                  const response = await api<{
                    message: string;
                    redirect_url?: string;
                  }>(`/api/public/forms/${slug}/`, "POST", {
                    request_id: requestId.current,
                    answers: Object.fromEntries(
                      visibleFormFields(form, answers)
                        .filter(
                          (field) => !NON_INPUT_TYPES.includes(field.type),
                        )
                        .map((field) => [field.id, answers[field.id] ?? ""]),
                    ),
                    consent: values.get("consent") === "on",
                    website: values.get("website"),
                    ref:
                      new URLSearchParams(window.location.search).get("ref") ||
                      "",
                  });
                  setSuccess(response.message);
                  if (response.redirect_url?.startsWith("https://"))
                    window.location.assign(response.redirect_url);
                } catch (err) {
                  setError(message(err));
                } finally {
                  setBusy(false);
                }
              }}
            >
              <PublicFormFields
                fields={visibleFormFields(form, answers)}
                answers={answers}
                onChange={(id, value) =>
                  setAnswers((current) => {
                    const next = { ...current, [id]: value };
                    const visible = new Set(
                      visibleFormFields(form, next).map((field) => field.id),
                    );
                    return Object.fromEntries(
                      Object.entries(next).filter(([key]) => visible.has(key)),
                    );
                  })
                }
              />
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
                  <ValidatedInput
                    name="website"
                    tabIndex={-1}
                    autoComplete="off"
                  />
                </label>
              </div>
              <label className="inline" style={{ alignItems: "flex-start" }}>
                <ValidatedInput
                  name="consent"
                  type="checkbox"
                  required
                  style={{ width: "auto", marginTop: 4 }}
                />
                {form.consent_text}
              </label>
              {error && <p role="alert">{error}</p>}
              <button
                className="button primary"
                disabled={busy}
                style={{
                  background: form.theme?.primary,
                  justifySelf:
                    form.button_align === "right"
                      ? "end"
                      : form.button_align === "center"
                        ? "center"
                        : "start",
                }}
              >
                {busy ? t("form.submitting") : t("form.submit")}
              </button>
            </ValidatedForm>
          )}
        </section>
      )}
    </main>
  );
}
