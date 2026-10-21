"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useState,
  type FormEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  BarChart3,
  ChevronDown,
  CircleHelp,
  Contact,
  CreditCard,
  GitBranch,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Menu,
  MessageCircle,
  Plug,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Store,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { api, message, type Billing, type Workspace } from "@/lib/api";
import { APPS, appById } from "@/lib/apps";
import { Announcements } from "@/components/growth";
import { VerifyBanner } from "@/components/verify-banner";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice } from "./ui";
import { UpgradePrompt } from "./plans";
import { MetaAccountSwitcher } from "./meta-switcher";

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

type NavItem = { id: string; label: string; icon: LucideIcon };

const PRIMARY: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "automations", label: "Automations", icon: GitBranch },
  { id: "crm", label: "CRM & contacts", icon: Contact },
  { id: "agent", label: "AI agent", icon: Sparkles },
];
const TOOLS: NavItem[] = [
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "templates", label: "Templates", icon: Store },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "team", label: "Team", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
];
const APP_STORE: NavItem = {
  id: "app-store",
  label: "App store",
  icon: LayoutGrid,
};
/** Sections an agent can open; owners and admins see everything. */
const AGENT_SECTIONS = [
  "overview",
  "inbox",
  "crm",
  "calendar",
  "app-store",
  "team",
  "settings",
];

function sectionLabel(section: string) {
  return (
    [...PRIMARY, ...TOOLS, APP_STORE].find((item) => item.id === section)
      ?.label ||
    APPS.find((app) => app.section === section)?.label ||
    section.charAt(0).toUpperCase() + section.slice(1)
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, workspace, workspaces, manager, prefix, refresh } =
    useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const section = pathname.split("/")[3] || "overview";
  const [creating, setCreating] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [plan, setPlan] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const branding = workspace.branding;
  const allowed = (id: string) => manager || AGENT_SECTIONS.includes(id);
  const docked = (workspace.pinned_apps || [])
    .map(appById)
    .filter((app) => app?.section && (manager || app.agents))
    .map((app) => ({ id: app!.section!, label: app!.label, icon: app!.icon }));

  useEffect(() => {
    // Billing is an owner/admin view; agents simply see no tier badge.
    if (!manager) return;
    const controller = new AbortController();
    api<Billing>(`${prefix}/billing/`, "GET", undefined, controller.signal)
      .then((billing) => {
        const name =
          billing.catalog.find((card) => card.slug === billing.plan)?.name ||
          billing.plan;
        setPlan(billing.status === "trialing" ? `${name} trial` : name);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix, manager]);
  useEffect(() => {
    if (!drawer) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawer(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [drawer]);

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
  // Following any link inside the drawer closes it on small screens.
  function closeOnNavigate(event: MouseEvent<HTMLElement>) {
    if ((event.target as HTMLElement).closest("a")) setDrawer(false);
  }
  const link = ({ id, label, icon: Icon }: NavItem) => (
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
  );
  const tools = TOOLS.filter((item) => allowed(item.id));
  return (
    <div
      className="app-shell"
      style={{
        ["--green" as string]:
          !branding.primary_color || branding.primary_color === "#347359"
            ? "var(--brand-action)"
            : branding.primary_color,
      }}
    >
      <aside
        className={`sidebar ${drawer ? "open" : ""}`}
        id="workspace-sidebar"
        onClick={closeOnNavigate}
      >
        <div className="sidebar-head">
          <Brand name={branding.brand_name} logo={branding.logo_url} />
          <button
            className="icon-button drawer-close"
            aria-label="Close navigation"
            onClick={() => setDrawer(false)}
          >
            <X size={18} />
          </button>
        </div>
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
        <MetaAccountSwitcher />
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {PRIMARY.filter((item) => allowed(item.id)).map(link)}
          {/* Open by default so pinned apps are one click away; members may collapse it. */}
          <details className="nav-apps" open>
            <summary className="nav-item">
              Apps
              {docked.length > 0 && (
                <span className="nav-count">{docked.length}</span>
              )}
              <ChevronDown size={15} />
            </summary>
            {docked.map(link)}
            {link(APP_STORE)}
          </details>
          {tools.length > 0 && (
            <details
              className="nav-tools"
              open={tools.some((item) => item.id === section)}
            >
              <summary className="nav-item">
                Business tools <ChevronDown size={15} />
              </summary>
              {tools.map(link)}
            </details>
          )}
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
              <span className="user-badges">
                <span className="role-badge">{workspace.role}</span>
                {plan && <span className="tier-badge">{plan}</span>}
              </span>
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
      {drawer && (
        <div
          className="drawer-backdrop"
          aria-hidden="true"
          onClick={() => setDrawer(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button drawer-toggle"
            aria-label="Open navigation"
            aria-expanded={drawer}
            aria-controls="workspace-sidebar"
            onClick={() => setDrawer(true)}
          >
            <Menu size={18} />
          </button>
          <div>
            {workspace.name} <span>/</span>{" "}
            <strong>{sectionLabel(section)}</strong>
          </div>
          {workspace.parent && (
            <span
              className="private-badge"
              style={{
                borderColor: "rgba(59, 130, 246, 0.35)",
                color: "#93c5fd",
                backgroundColor: "rgba(59, 130, 246, 0.08)",
              }}
            >
              Agency Managed
            </span>
          )}
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
          <VerifyBanner user={user} />
          <Announcements workspaceId={workspace.id} page={section} />
          <ErrorNotice error={error} />
          {children}
        </main>
        <UpgradePrompt
          prefix={`/api/workspaces/${workspace.id}`}
          agencyManaged={Boolean(workspace.parent)}
        />
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
