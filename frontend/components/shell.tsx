"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  BarChart3,
  ChevronDown,
  Contact,
  CreditCard,
  GitBranch,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Menu,
  MessageCircle,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Store,
  Users,
  Wrench,
  X,
  type LucideIcon,
  ChevronRight,
} from "lucide-react";
import { api, message, type Billing, type Workspace } from "@/lib/api";
import { appById } from "@/lib/apps";
import { Announcements } from "@/components/growth";
import { VerifyBanner } from "@/components/verify-banner";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice } from "./ui";
import { UpgradePrompt } from "./plans";
import { MetaAccountSwitcher } from "./meta-switcher";
import { BrandIcon, type BrandName } from "@/lib/brand-icons";

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
    <div className="brand-logo-container">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="brand-logo" />
      ) : (
        <span className="brand-icon-ghost">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M9 10h.01" />
            <path d="M15 10h.01" />
            <path d="M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8z" />
          </svg>
        </span>
      )}
      <span className="brand-title">{name}</span>
    </div>
  );
}

type NavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  color?: string;
  /** Shows the brand's real logo in place of `icon`. */
  brand?: BrandName;
};

/* Primary Navigation matching BooSend IA */
const PRIMARY_NAV: NavItem[] = [
  { id: "overview", label: "Home", icon: LayoutDashboard },
  { id: "automations", label: "Automation", icon: GitBranch },
  { id: "integrations", label: "Integrations", icon: LayoutGrid },
  { id: "inbox", label: "Conversations", icon: MessageCircle },
  { id: "crm", label: "CRM", icon: Contact },
];

/* Every other workspace section, grouped so the main list stays short. */
const TOOLS: NavItem[] = [
  { id: "agent", label: "AI agent", icon: Sparkles },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "templates", label: "Templates", icon: Store },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "team", label: "Team", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
];

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

export function Shell({ children }: { children: ReactNode }) {
  const { user, workspace, workspaces, manager, prefix, refresh } =
    useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const section = pathname.split("/")[3] || "overview";
  const [creating, setCreating] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [workspaceMenu, setWorkspaceMenu] = useState(false);
  const workspaceCard = useRef<HTMLDivElement>(null);
  const [appsOpen, setAppsOpen] = useState(true);
  const [plan, setPlan] = useState("Lifetime");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const branding = workspace.branding;
  const allowed = (id: string) => manager || AGENT_SECTIONS.includes(id);
  const tools = TOOLS.filter((item) => allowed(item.id));

  const docked = (workspace.pinned_apps || [])
    .map(appById)
    .filter((app) => app?.section && (manager || app.agents))
    .map((app) => ({
      id: app!.section!,
      label: app!.label,
      icon: app!.icon,
    }));

  useEffect(() => {
    if (!workspaceMenu) return;
    const close = (event: globalThis.MouseEvent | KeyboardEvent) => {
      if (
        event instanceof KeyboardEvent
          ? event.key === "Escape"
          : !workspaceCard.current?.contains(event.target as Node)
      )
        setWorkspaceMenu(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [workspaceMenu]);

  useEffect(() => {
    if (!manager) return;
    const controller = new AbortController();
    api<Billing>(`${prefix}/billing/`, "GET", undefined, controller.signal)
      .then((billing) => {
        const name =
          billing.catalog.find((card) => card.slug === billing.plan)?.name ||
          billing.plan;
        setPlan(
          billing.status === "trialing" ? `${name} trial` : name || "Lifetime",
        );
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix, manager]);

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
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
      setWorkspaceMenu(false);
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

  function closeOnNavigate(event: MouseEvent<HTMLElement>) {
    if ((event.target as HTMLElement).closest("a")) setDrawer(false);
  }

  const renderNavLink = (item: NavItem, isSub = false) => {
    const active = section === item.id;
    const Icon = item.icon;
    return (
      <Link
        key={item.id}
        href={`/w/${workspace.id}/${item.id}`}
        className={`boosend-nav-link ${active ? "active" : ""} ${isSub ? "sub-item" : ""}`}
        aria-current={active ? "page" : undefined}
        aria-label={item.label}
        title={item.label}
      >
        <span
          className="nav-icon-wrap"
          style={{ color: item.color || undefined }}
        >
          {item.brand ? (
            <BrandIcon name={item.brand} size={18} />
          ) : (
            <Icon size={18} />
          )}
        </span>
        <span className="nav-label-text">{item.label}</span>
        {item.badge && <span className="nav-badge-pill">{item.badge}</span>}
      </Link>
    );
  };

  return (
    <div className="app-shell-root">
      {/* Pitch-Black Modern Sidebar */}
      <aside
        className={`boosend-sidebar ${drawer ? "drawer-open" : ""}`}
        id="workspace-sidebar"
        onClick={closeOnNavigate}
      >
        {/* Top Brand */}
        <div className="sidebar-brand-row">
          <Link
            href={`/w/${workspace.id}/overview`}
            className="brand-link"
            aria-label={`${branding.brand_name || "Nemio"} Home`}
          >
            <Brand
              name={branding.brand_name || "Nemio"}
              logo={branding.logo_url}
            />
          </Link>
          <button
            className="icon-button mobile-close-btn"
            aria-label="Close navigation"
            onClick={() => setDrawer(false)}
          >
            <X size={18} />
          </button>
        </div>

        {/* 1. Workspace Card */}
        <div className="workspace-pill-card" ref={workspaceCard}>
          <button
            type="button"
            className="workspace-pill-header"
            aria-label={`Switch workspace, current workspace: ${workspace.name}`}
            aria-expanded={workspaceMenu}
            aria-controls="workspace-switch-menu"
            onClick={() => setWorkspaceMenu(!workspaceMenu)}
          >
            <div className="workspace-avatar-sq">
              {initials(workspace.name)}
            </div>
            <div className="workspace-pill-info">
              <div className="workspace-name-row">
                <span className="workspace-title">{workspace.name}</span>
                <span className="default-tag">Default</span>
              </div>
              <span className="workspace-role">
                <ShieldCheck size={12} /> {workspace.role || "Owner"}
              </span>
            </div>
            <ChevronDown
              size={14}
              className={`dropdown-arrow ${workspaceMenu ? "flip" : ""}`}
            />
          </button>

          {/* Workspace dropdown menu */}
          {workspaceMenu && (
            <div
              className="workspace-dropdown-popover"
              id="workspace-switch-menu"
            >
              <span className="popover-heading">WORKSPACES</span>
              <div className="workspace-items-list">
                {workspaces.map((item) => (
                  <button
                    key={item.id}
                    className={`workspace-select-item ${item.id === workspace.id ? "current" : ""}`}
                    onClick={() => {
                      setWorkspaceMenu(false);
                      setDrawer(false);
                      router.push(`/w/${item.id}/overview`);
                    }}
                  >
                    <span className="item-initials">{initials(item.name)}</span>
                    <span className="item-name">{item.name}</span>
                    {item.id === workspace.id && (
                      <span className="active-dot" />
                    )}
                  </button>
                ))}
              </div>
              <button
                className="add-workspace-btn"
                onClick={() => {
                  setWorkspaceMenu(false);
                  setCreating(true);
                }}
              >
                <Plus size={14} /> New workspace
              </button>
            </div>
          )}
        </div>

        {/* 2. Connected Meta Social Account Card */}
        <div className="social-account-switcher-wrap">
          <MetaAccountSwitcher />
        </div>

        {/* 3. Main Navigation List */}
        <nav className="boosend-nav-menu" aria-label="Workspace navigation">
          {PRIMARY_NAV.filter((item) => allowed(item.id)).map((item) =>
            renderNavLink(item),
          )}

          {/* Expandable Apps Accordion Group */}
          <div className="nav-accordion-group">
            <button
              type="button"
              className={`boosend-nav-link accordion-header ${appsOpen ? "open" : ""}`}
              aria-label="Apps"
              aria-expanded={appsOpen}
              onClick={() => setAppsOpen(!appsOpen)}
            >
              <span className="nav-icon-wrap">
                <Layers size={18} />
              </span>
              <span className="nav-label-text">Apps</span>
              <span className="accordion-arrow">
                <ChevronDown size={14} className={appsOpen ? "flip" : ""} />
              </span>
            </button>

            {appsOpen && (
              <div className="accordion-children">
                {docked.map((item) => renderNavLink(item, true))}
                <Link
                  href={`/w/${workspace.id}/app-store`}
                  className={`boosend-nav-link sub-item ${section === "app-store" ? "active" : ""}`}
                  aria-label="Browse all apps"
                >
                  <span className="nav-icon-wrap">
                    <LayoutGrid size={16} />
                  </span>
                  <span className="nav-label-text">Browse all apps</span>
                </Link>
              </div>
            )}
          </div>

          {tools.length > 0 && (
            <details
              className="nav-tools"
              open={tools.some((item) => item.id === section)}
            >
              <summary
                className="boosend-nav-link accordion-header"
                aria-label="Business tools"
              >
                <span className="nav-icon-wrap">
                  <Wrench size={18} />
                </span>
                <span className="nav-label-text">Business tools</span>
                <span className="accordion-arrow">
                  <ChevronDown size={14} />
                </span>
              </summary>
              <div className="accordion-children">
                {tools.map((item) => renderNavLink(item, true))}
              </div>
            </details>
          )}

          {/* Settings */}
          {renderNavLink({
            id: "settings",
            label: "Settings",
            icon: Settings,
          })}
        </nav>

        {/* 4. Bottom User Profile Card */}
        <div className="sidebar-bottom-user-wrap">
          <div className="user-profile-card">
            <div className="user-avatar-circle">
              {initials(user.name || user.email)}
            </div>
            <div className="user-info-text">
              <div className="user-name-row">
                <span className="user-name" title={user.name || user.email}>
                  {user.name || "My Account"}
                </span>
                <span className="lifetime-badge">{plan || "Lifetime"}</span>
              </div>
              <span className="user-email" title={user.email}>
                {user.email}
              </span>
            </div>
            <button
              className="icon-button logout-btn"
              aria-label="Sign out"
              onClick={signOut}
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile Drawer Backdrop */}
      {drawer && (
        <div
          className="drawer-backdrop"
          aria-hidden="true"
          onClick={() => setDrawer(false)}
        />
      )}

      {/* Main Canvas Shell */}
      <div className="main-content-canvas">
        {/* Top Header Bar */}
        <header className="canvas-topbar">
          <button
            className="icon-button mobile-drawer-toggle"
            aria-label="Open navigation"
            aria-expanded={drawer}
            aria-controls="workspace-sidebar"
            onClick={() => setDrawer(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb-nav">
            <span className="workspace-crumb">{workspace.name}</span>
            <ChevronRight size={14} className="crumb-separator" />
            <span className="section-crumb">
              {section.charAt(0).toUpperCase() + section.slice(1)}
            </span>
          </div>
          <div className="topbar-actions">
            {workspace.parent && (
              <span className="badge-agency">Agency Managed</span>
            )}
            <span className="badge-role">
              <ShieldCheck size={13} /> {workspace.role}
            </span>
          </div>
        </header>

        {/* Page Content Body */}
        <main className="canvas-body">
          <VerifyBanner user={user} />
          <Announcements workspaceId={workspace.id} page={section} />
          {children}
        </main>
        <UpgradePrompt
          prefix={`/api/workspaces/${workspace.id}`}
          agencyManaged={Boolean(workspace.parent)}
        />
      </div>

      {/* Create Workspace Modal */}
      {creating && (
        <div className="modal-backdrop" onClick={() => setCreating(false)}>
          <div
            className="modal-card-box"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header-row">
              <h3>Create new workspace</h3>
              <button
                className="icon-button"
                onClick={() => setCreating(false)}
              >
                <X size={18} />
              </button>
            </div>
            <ErrorNotice error={error} />
            <form onSubmit={createWorkspace} className="stacked-form">
              <label>
                <span>Workspace name</span>
                <input
                  type="text"
                  name="name"
                  placeholder="e.g. Acme Marketing"
                  required
                  autoFocus
                />
              </label>
              <div className="modal-actions-row">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setCreating(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button primary"
                  disabled={busy}
                >
                  {busy ? "Creating…" : "Create workspace"}
                </button>
              </div>
            </form>
          </div>
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
    <form onSubmit={create} className="stacked-form">
      <label>
        <span>Workspace name</span>
        <input
          name="name"
          maxLength={80}
          placeholder="e.g. Acme Marketing"
          required
          autoFocus
        />
      </label>
      <button className="button primary" disabled={busy}>
        {busy ? "Creating…" : "Create workspace"}
      </button>
    </form>
  );
}
