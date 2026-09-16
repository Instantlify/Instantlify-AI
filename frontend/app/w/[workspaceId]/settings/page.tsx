"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Check, Plus } from "lucide-react";
import {
  api,
  type Branding,
  type ClientWorkspace,
  type DataOperation,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

type BrandingResponse = {
  own: (Omit<Branding, "custom_domain"> & { custom_domain: string }) | null;
  effective: Branding;
  inherited_from: string | null;
};

export default function SettingsPage() {
  const { workspace, prefix, manager, refresh } = useWorkspace();
  const owner = workspace.role === "owner";
  const feedback = useFeedback();
  const [branding, setBranding] = useState<BrandingResponse | null>(null);
  const [clients, setClients] = useState<ClientWorkspace[]>([]);
  const [operations, setOperations] = useState<DataOperation[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    api<BrandingResponse>(
      `${prefix}/branding/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setBranding)
      .catch(() => undefined);
    if (manager && !workspace.parent)
      api<ClientWorkspace[]>(
        `${prefix}/clients/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then(setClients)
        .catch(() => undefined);
    if (owner)
      api<DataOperation[]>(
        `${prefix}/data-operations/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then(setOperations)
        .catch(() => undefined);
    return () => controller.abort();
  }, [prefix, manager, owner, workspace.parent]);

  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    await feedback.run(async () => {
      await api(`${prefix}/`, "PATCH", data);
      await refresh();
    }, "Workspace name updated.");
  }
  async function saveBranding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const data = {
      brand_name: form.get("brand_name"),
      logo_url: form.get("logo_url"),
      primary_color: form.get("primary_color"),
      support_email: form.get("support_email"),
      custom_domain: form.get("custom_domain"),
      hide_platform_branding: form.get("hide_platform_branding") === "on",
    };
    await feedback.run(async () => {
      await api(`${prefix}/branding/`, "PUT", data);
      setBranding(await api<BrandingResponse>(`${prefix}/branding/`));
      await refresh();
    }, "Branding saved. Reload to see it applied everywhere.");
  }
  async function resetBranding() {
    if (!window.confirm("Remove this workspace's branding?")) return;
    await feedback.run(async () => {
      await api(`${prefix}/branding/`, "DELETE");
      setBranding(await api<BrandingResponse>(`${prefix}/branding/`));
      await refresh();
    }, "Branding reset.");
  }
  async function createClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    await feedback.run(async () => {
      const created = await api<ClientWorkspace>(
        `${prefix}/clients/`,
        "POST",
        Object.fromEntries(new FormData(form)),
      );
      setClients((list) => [...list, created]);
      form.reset();
      await refresh();
    }, "Client workspace created. Switch to it from the workspace menu.");
  }
  async function requestData(
    kind: "export" | "delete",
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const data = {
      kind,
      ...Object.fromEntries(new FormData(event.currentTarget)),
    };
    if (
      kind === "delete" &&
      !window.confirm("Permanently delete this workspace and all its data?")
    )
      return;
    await feedback.run(
      async () => {
        await api(`${prefix}/data-operations/`, "POST", data);
        setOperations(await api<DataOperation[]>(`${prefix}/data-operations/`));
      },
      kind === "export"
        ? "Export requested. It appears below when ready."
        : "Deletion requested.",
    );
  }
  const own = branding?.own;
  return (
    <>
      <PageHeading eyebrow="Settings" title="Your workspace, your way." />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="stack">
        <Panel title="Workspace details" className="settings-panel">
          <p className="panel-subtitle">
            A familiar name helps your team feel at home.
          </p>
          <form onSubmit={rename} className="form-grid">
            <label>
              Workspace name
              <input
                name="name"
                defaultValue={workspace.name}
                maxLength={100}
                required
                disabled={!manager}
              />
            </label>
            <label>
              Workspace ID
              <input value={workspace.id} readOnly />
            </label>
            {manager && (
              <div className="form-actions">
                <button className="button primary" disabled={feedback.busy}>
                  {feedback.busy ? "Saving…" : "Save changes"}
                  <Check size={16} />
                </button>
              </div>
            )}
          </form>
          <p className="panel-footnote">
            Channels, API keys and webhooks live under{" "}
            <Link href={`/w/${workspace.id}/integrations`}>Integrations</Link>;
            plans and usage under{" "}
            <Link href={`/w/${workspace.id}/payments`}>Payments</Link>.
          </p>
        </Panel>

        <Panel
          title="Branding"
          aside={
            branding?.inherited_from
              ? "Inherited from your agency"
              : "White-label"
          }
          className="settings-panel"
        >
          {!owner ? (
            <Empty>
              This workspace appears as{" "}
              <strong>{branding?.effective.brand_name}</strong>. Only the owner
              can change branding.
            </Empty>
          ) : (
            <form
              onSubmit={saveBranding}
              className="form-grid"
              key={own?.brand_name || "new"}
            >
              <label>
                Brand name
                <input
                  name="brand_name"
                  defaultValue={own?.brand_name || ""}
                  maxLength={60}
                  required
                />
              </label>
              <label>
                Logo URL{" "}
                <span className="hint">
                  HTTPS image, shown instead of the icon
                </span>
                <input
                  name="logo_url"
                  type="url"
                  defaultValue={own?.logo_url || ""}
                />
              </label>
              <label>
                Primary colour
                <input
                  name="primary_color"
                  type="color"
                  defaultValue={own?.primary_color || "#347359"}
                />
              </label>
              <label>
                Support email
                <input
                  name="support_email"
                  type="email"
                  defaultValue={own?.support_email || ""}
                />
              </label>
              <label>
                Custom domain{" "}
                <span className="hint">
                  e.g. app.youragency.com — point it at this deployment;
                  branding resolves by host
                </span>
                <input
                  name="custom_domain"
                  defaultValue={own?.custom_domain || ""}
                  maxLength={253}
                />
              </label>
              <label className="inline">
                <input
                  name="hide_platform_branding"
                  type="checkbox"
                  defaultChecked={own?.hide_platform_branding || false}
                />
                Hide “Nemio” from the footer and sign-in page
              </label>
              <div className="form-actions">
                <button className="button primary" disabled={feedback.busy}>
                  Save branding
                </button>
                {own && (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={resetBranding}
                  >
                    Reset to default
                  </button>
                )}
              </div>
            </form>
          )}
        </Panel>

        {!workspace.parent && manager && (
          <Panel
            title="Client workspaces"
            aside="Agency mode"
            className="settings-panel"
          >
            <p className="panel-subtitle">
              Manage several businesses under your brand. Each client workspace
              keeps its own channels, leads and billing; you become its owner.
            </p>
            {clients.length ? (
              <div className="card-list" style={{ marginTop: 14 }}>
                {clients.map((client) => (
                  <div className="list-row" key={client.id}>
                    <strong>{client.name}</strong>
                    <span className="muted-text">
                      {client.members} member(s)
                    </span>
                    <span className="spacer" />
                    <Link
                      href={`/w/${client.id}/overview`}
                      className="text-button"
                    >
                      Open
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>No client workspaces yet.</Empty>
            )}
            <form
              onSubmit={createClient}
              className="invite-form"
              style={{ marginTop: 14 }}
            >
              <label>
                Client name
                <input
                  name="name"
                  maxLength={100}
                  required
                  placeholder="e.g. Bloom Bakery"
                />
              </label>
              <button className="button primary" disabled={feedback.busy}>
                Add client
                <Plus size={16} />
              </button>
            </form>
          </Panel>
        )}

        {owner && (
          <Panel
            title="Your data"
            aside="Export and deletion"
            className="settings-panel"
          >
            <p className="panel-subtitle">
              Export everything this workspace holds as JSON, or delete the
              workspace and all its data. Both require your password.
            </p>
            {operations.length > 0 && (
              <div className="card-list" style={{ marginTop: 14 }}>
                {operations.map((op) => (
                  <div className="list-row" key={op.id}>
                    <strong>{op.kind}</strong>
                    <Pill tone={statusTone(op.status)}>{op.status}</Pill>
                    {op.error_code && (
                      <span className="muted-text">{op.error_code}</span>
                    )}
                    <span className="spacer" />
                    <span className="muted-text">
                      {new Date(op.created_at).toLocaleString()}
                    </span>
                    {op.kind === "export" && op.status === "complete" && (
                      <a
                        className="text-button"
                        href={`${prefix}/data-operations/${op.id}/download/`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="two-col" style={{ marginTop: 16 }}>
              <form
                onSubmit={(event) => requestData("export", event)}
                className="form-grid"
              >
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </label>
                <div className="form-actions">
                  <button className="button secondary" disabled={feedback.busy}>
                    Request export
                  </button>
                </div>
              </form>
              <form
                onSubmit={(event) => requestData("delete", event)}
                className="form-grid"
              >
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </label>
                <label>
                  Type the workspace name to confirm
                  <input
                    name="confirmation"
                    placeholder={workspace.name}
                    required
                  />
                </label>
                <div className="form-actions">
                  <button className="button danger" disabled={feedback.busy}>
                    Delete workspace
                  </button>
                </div>
              </form>
            </div>
            <CopyField
              label="Workspace ID (for support)"
              value={workspace.id}
            />
          </Panel>
        )}
      </div>
    </>
  );
}
