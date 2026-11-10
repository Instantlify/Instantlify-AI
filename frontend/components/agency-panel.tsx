"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, message, when } from "@/lib/api";
import {
  CopyField,
  ErrorNotice,
  Pill,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";
import { asList } from "@/lib/as-list";

type OwnBranding = {
  custom_domain: string;
  custom_domain_status?: "pending" | "active" | "failed";
  verification_token?: string;
  verified_at?: string | null;
};
type ClientWorkspace = {
  id: string;
  name: string;
  created_at: string;
  members: number;
};

/** Custom domain (owner) and agency client workspaces (owner/admin). */
export function AgencyPanel({
  prefix,
  isOwner,
  isClient,
}: {
  prefix: string;
  isOwner: boolean;
  isClient: boolean;
}) {
  const [branding, setBranding] = useState<OwnBranding | null>(null);
  const [domain, setDomain] = useState("");
  const [clients, setClients] = useState<ClientWorkspace[]>([]);
  const [clientName, setClientName] = useState("");
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const result = await api<{ own: OwnBranding | null }>(
        `${prefix}/branding/`,
        "GET",
        undefined,
        signal,
      );
      setBranding(result.own);
      setDomain(result.own?.custom_domain || "");
      if (!isClient) {
        setClients(
          asList(
            await api<ClientWorkspace[]>(
              `${prefix}/clients/`,
              "GET",
              undefined,
              signal,
            ),
          ),
        );
      }
    },
    [prefix, isClient],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      load(controller.signal).catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function saveDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await feedback.run(async () => {
      await api(`${prefix}/branding/`, "PUT", {
        custom_domain: domain.trim().toLowerCase(),
      });
      await load();
    }, "Domain saved. Add the DNS records below, then verify.");
  }

  async function verify() {
    await feedback.run(async () => {
      try {
        const result = await api<{ verified: boolean; message: string }>(
          `${prefix}/branding/verify-domain/`,
          "POST",
          {},
        );
        feedback.setNotice(result.message || "Domain verified.");
      } finally {
        await load();
      }
    });
  }

  async function createClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = clientName.trim();
    if (!name) return;
    await feedback.run(async () => {
      await api(`${prefix}/clients/`, "POST", { name });
      setClientName("");
      await load();
    }, "Client workspace created. Switch to it from the workspace menu.");
  }

  const savedDomain = branding?.custom_domain || "";
  const status = branding?.custom_domain_status || "pending";
  const appHost =
    typeof window === "undefined"
      ? "your Nemio app domain"
      : window.location.hostname;

  return (
    <div className="settings-tab-content stack-cards">
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <section className="card stack">
        <h3>Custom domain</h3>
        <p className="muted-text">
          Serve your workspace&rsquo;s pages and app under your own domain, such
          as app.youragency.com.
        </p>
        {isOwner ? (
          <form className="row wrap" style={{ gap: 8 }} onSubmit={saveDomain}>
            <input
              aria-label="Custom domain"
              placeholder="app.youragency.com"
              maxLength={253}
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
            />
            <button className="button primary small" disabled={feedback.busy}>
              Save domain
            </button>
          </form>
        ) : (
          <p className="muted-text">
            Only the workspace owner can change the domain.
          </p>
        )}
        {savedDomain && (
          <div className="stack" style={{ gap: 8 }}>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <strong>{savedDomain}</strong>
              <Pill
                tone={
                  status === "active"
                    ? "good"
                    : status === "failed"
                      ? "bad"
                      : "warn"
                }
              >
                {status === "active"
                  ? "Verified"
                  : status === "failed"
                    ? "Check failed"
                    : "Pending"}
              </Pill>
              {branding?.verified_at && (
                <span className="muted-text">
                  since {when(branding.verified_at)}
                </span>
              )}
            </div>
            {status !== "active" && (
              <>
                <p className="muted-text">
                  Add these two DNS records at your domain provider:
                </p>
                <CopyField
                  label="TXT record name"
                  value={`_nemio-challenge.${savedDomain}`}
                />
                <CopyField
                  label="TXT record value"
                  value={`nemio-verify=${branding?.verification_token || ""}`}
                />
                <CopyField label={`CNAME for ${savedDomain}`} value={appHost} />
                <button
                  type="button"
                  className="button secondary small"
                  style={{ alignSelf: "flex-start" }}
                  disabled={feedback.busy}
                  onClick={() => void verify()}
                >
                  Verify domain
                </button>
                <small className="muted-text">
                  DNS changes can take a few minutes to an hour to appear.
                </small>
              </>
            )}
          </div>
        )}
      </section>

      {!isClient && (
        <section className="card stack">
          <h3>Client workspaces</h3>
          <p className="muted-text">
            Agencies can run a separate workspace for each client. Client
            workspaces use your branding unless they set their own.
          </p>
          <form className="row wrap" style={{ gap: 8 }} onSubmit={createClient}>
            <input
              aria-label="Client workspace name"
              placeholder="Client name"
              maxLength={100}
              value={clientName}
              onChange={(event) => setClientName(event.target.value)}
            />
            <button className="button primary small" disabled={feedback.busy}>
              Create client workspace
            </button>
          </form>
          {clients.length ? (
            <ul
              className="stack"
              style={{ listStyle: "none", padding: 0, gap: 6 }}
            >
              {clients.map((client) => (
                <li key={client.id} className="row" style={{ gap: 8 }}>
                  <strong>{client.name}</strong>
                  <span className="muted-text">
                    {client.members} member{client.members === 1 ? "" : "s"} ·
                    created {when(client.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted-text">No client workspaces yet.</p>
          )}
        </section>
      )}
    </div>
  );
}
