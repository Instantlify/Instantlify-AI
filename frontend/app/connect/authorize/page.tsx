"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, message } from "@/lib/api";
import { Brand } from "@/components/shell";
import { ErrorNotice } from "@/components/ui";

type ConsentRequest = {
  client_name: string;
  redirect_host: string;
  scopes: string[];
  workspaces: { id: string; name: string }[];
};

/** OAuth consent for MCP clients such as the claude.ai connector. */
export default function ConnectAuthorizePage() {
  const router = useRouter();
  const [requestId, setRequestId] = useState("");
  const [consent, setConsent] = useState<ConsentRequest | null>(null);
  const [workspace, setWorkspace] = useState("");
  const [allowWrite, setAllowWrite] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("request") || "";
    queueMicrotask(() => setRequestId(id));
    if (!id) return;
    api<ConsentRequest>(`/api/oauth/requests/${id}/`)
      .then((data) => {
        setConsent(data);
        setWorkspace(data.workspaces[0]?.id || "");
        setAllowWrite(data.scopes.includes("write"));
      })
      .catch((err) => {
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.status === 403)
        ) {
          const next = `/connect/authorize/?request=${id}`;
          router.replace(`/auth/?next=${encodeURIComponent(next)}`);
          return;
        }
        setError(message(err));
      });
  }, [router]);

  async function decide(decision: "approve" | "deny") {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ redirect: string }>(
        `/api/oauth/requests/${requestId}/`,
        "POST",
        {
          decision,
          workspace_id: workspace,
          scopes: allowWrite ? ["read", "write"] : ["read"],
        },
      );
      // Back to the client that asked (an absolute, pre-registered redirect URI).
      window.location.href = result.redirect;
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  return (
    <main className="setup-screen">
      <div
        className="auth-card stack"
        style={{ maxWidth: 460, margin: "0 auto" }}
      >
        <Brand />
        {!consent ? (
          <>
            <h1>Connect an app</h1>
            <ErrorNotice
              error={
                error || (!requestId ? "This link is missing its request." : "")
              }
            />
            {!error && requestId && <p className="muted-text">Loading…</p>}
          </>
        ) : (
          <>
            <h1>Allow {consent.client_name} to use Nemio?</h1>
            <p className="muted-text">
              It will connect from <strong>{consent.redirect_host}</strong>.
              Only continue if you started this from that app.
            </p>
            <ErrorNotice error={error} />
            {consent.workspaces.length ? (
              <>
                <label>
                  Workspace
                  <select
                    aria-label="Workspace to connect"
                    value={workspace}
                    onChange={(event) => setWorkspace(event.target.value)}
                  >
                    {consent.workspaces.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <ul className="muted-text">
                  <li>Read conversations, contacts, automations and metrics</li>
                  {allowWrite && (
                    <li>
                      Reply to customers, start automations and update contacts,
                      tracking links and knowledge
                    </li>
                  )}
                </ul>
                {consent.scopes.includes("write") && (
                  <label className="inline">
                    <input
                      type="checkbox"
                      checked={allowWrite}
                      onChange={(event) => setAllowWrite(event.target.checked)}
                    />
                    Allow changes and replies (not just reading)
                  </label>
                )}
                <div className="row" style={{ gap: 8 }}>
                  <button
                    type="button"
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void decide("deny")}
                  >
                    Deny
                  </button>
                  <button
                    type="button"
                    className="button primary"
                    disabled={busy || !workspace}
                    onClick={() => void decide("approve")}
                  >
                    Allow
                  </button>
                </div>
                <p className="muted-text small">
                  You can disconnect it any time by revoking its key under
                  Integrations → Developer.
                </p>
              </>
            ) : (
              <p className="muted-text">
                You need to be an owner or admin of a workspace to connect apps.
              </p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
