"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  CalendarDays,
  ChevronDown,
  CircleHelp,
  CreditCard,
  GitBranch,
  Inbox,
  LayoutDashboard,
  Link2,
  LogOut,
  MessageCircle,
  Plug,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Store,
  Users,
  X,
} from "lucide-react";
import { api, message, type Workspace } from "@/lib/api";
import { Announcements } from "@/components/growth";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice } from "./ui";
import { UpgradePrompt } from "./plans";

export const initials = (name: string) =>
  name.trim().slice(0, 2).toUpperCase() || "N";

export function Brand({
  name = "Nemio",
  logo = "",
}: {
  name?: string;
  logo?: string;
}) {
  return (
    <div className="brand">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="brand-logo" />
      ) : (
        <span className="brand-icon">
          <MessageCircle size={17} />
        </span>
      )}
      {name}
      {!logo && <span className="brand-dot">.</span>}
    </div>
  );
}

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "automations", label: "Automations", icon: GitBranch },
  { id: "agent", label: "AI agent", icon: Sparkles },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "calendar", label: "Content", icon: CalendarDays },
  { id: "bio", label: "Link in bio", icon: Link2 },
  { id: "templates", label: "Templates", icon: Store },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "team", label: "Team", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const { user, workspace, workspaces, refresh } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const section = pathname.split("/")[3] || "overview";
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const branding = workspace.branding;
  const agentOnly = workspace.role === "agent";
  const items = NAV.filter(
    (item) =>
      !agentOnly ||
      ["overview", "inbox", "calendar", "team", "settings"].includes(item.id),
  );
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<Workspace>(
        "/api/workspaces/",
        "POST",
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      await refresh();
      setCreating(false);
      router.push(`/w/${created.id}/overview`);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    try {
      await api("/api/auth/logout/", "POST");
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(message(err));
    }
  }
  const active = items.find((item) => item.id === section);
  return (
    <div
      className="app-shell"
      style={{ ["--green" as string]: branding.primary_color }}
    >
      <aside className="sidebar">
        <Brand name={branding.brand_name} logo={branding.logo_url} />
        <div className="workspace-select">
          <span className="workspace-avatar">{initials(workspace.name)}</span>
          <div>
            <span className="tiny-label">WORKSPACE</span>
            <select
              aria-label="Current workspace"
              value={workspace.id}
              onChange={(event) =>
                router.push(`/w/${event.target.value}/${section}`)
              }
            >
              {workspaces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {items.map(({ id, label, icon: Icon }) => (
            <Link
              key={id}
              href={`/w/${workspace.id}/${id}`}
              className={`nav-item ${section === id ? "active" : ""}`}
              aria-current={section === id ? "page" : undefined}
            >
              <Icon size={18} />
              {label}
              {section === id && <span className="nav-dot" />}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="foundation-card">
            <span className="foundation-icon">
              <Sparkles size={18} />
            </span>
            <strong>Need another home?</strong>
            <p>Every workspace keeps its own team, channels and data.</p>
            <button className="text-button" onClick={() => setCreating(true)}>
              New workspace
              <Plus size={15} />
            </button>
          </div>
          <Link href={`/w/${workspace.id}/help`} className="nav-item">
            <CircleHelp size={18} />
            Getting started
          </Link>
          <div className="user-card">
            <span className="user-avatar">
              {initials(user.name || user.email)}
            </span>
            <div>
              <strong>{user.name || "Your account"}</strong>
              <span title={user.email}>{user.email}</span>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={signOut}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            {workspace.name} <span>/</span>{" "}
            <strong>
              {active?.label ||
                section.charAt(0).toUpperCase() + section.slice(1)}
            </strong>
          </div>
          <span className="private-badge">
            <ShieldCheck size={14} /> {workspace.role}
          </span>
          <button
            className="icon-button mobile-signout"
            aria-label="Sign out on mobile"
            onClick={signOut}
          >
            <LogOut size={17} />
          </button>
        </header>
        <main className="main-content">
          <Announcements workspaceId={workspace.id} page={section} />
          <ErrorNotice error={error} />
          {children}
        </main>
        <UpgradePrompt prefix={`/api/workspaces/${workspace.id}`} />
        {!branding.hide_platform_branding && (
          <footer className="app-footer">
            <span>Made for more meaningful conversations.</span>
            <span>Nemio</span>
          </footer>
        )}
      </div>
      {creating && (
        <div className="modal-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-workspace-title"
            className="modal"
          >
            <button
              className="icon-button close-modal"
              aria-label="Close dialog"
              onClick={() => setCreating(false)}
            >
              <X size={20} />
            </button>
            <h2 id="new-workspace-title">Create a workspace</h2>
            <p>Each workspace keeps its team and data separate.</p>
            <ErrorNotice error={error} />
            <WorkspaceForm create={create} busy={busy} />
          </section>
        </div>
      )}
    </div>
  );
}

export function WorkspaceForm({
  create,
  busy,
}: {
  create: (event: FormEvent<HTMLFormElement>) => void;
  busy: boolean;
}) {
  return (
    <form onSubmit={create}>
      <label>
        Workspace name
        <input
          name="name"
          placeholder="e.g. Acme Studio"
          maxLength={100}
          required
          autoFocus
        />
      </label>
      <button className="button primary" disabled={busy}>
        {busy ? "Creating…" : "Create workspace"}
        <Plus size={16} />
      </button>
    </form>
  );
}
