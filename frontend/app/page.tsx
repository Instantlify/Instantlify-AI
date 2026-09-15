"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  Check,
  ChevronDown,
  CircleHelp,
  GitBranch,
  Instagram,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  type Audit,
  type Connection,
  type Invitation,
  type Member,
  type Page,
  type Status,
  type User,
  type Workspace,
} from "@/lib/api";

const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
const initials = (name: string) => name.trim().slice(0, 2).toUpperCase() || "N";

async function loadWorkspaces(signal?: AbortSignal) {
  const first = await api<Page<Workspace>>(
    "/api/workspaces/",
    "GET",
    undefined,
    signal,
  );
  const all = [...first.results];
  let next = first.next;
  while (next) {
    const url = new URL(next, window.location.origin);
    const page = await api<Page<Workspace>>(
      url.pathname + url.search,
      "GET",
      undefined,
      signal,
    );
    all.push(...page.results);
    next = page.next;
  }
  return all;
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-icon">
        <GitBranch size={22} strokeWidth={2.5} />
      </span>
      nemio<span className="brand-dot">.</span>
    </div>
  );
}

function ErrorNotice({ error }: { error: string }) {
  return error ? (
    <div role="alert" className="error-notice">
      {error}
    </div>
  ) : null;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<User>("/api/auth/me/", "GET", undefined, controller.signal)
      .then(setUser)
      .catch((err) => {
        if (
          !controller.signal.aborted &&
          !(err instanceof ApiError && [401, 403].includes(err.status))
        )
          setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  if (loading)
    return (
      <div className="loading-screen">
        <Brand />
        <p>Opening your workspace…</p>
      </div>
    );
  return user ? (
    <WorkspaceApp user={user} onLogout={() => setUser(null)} />
  ) : (
    <Auth onSuccess={setUser} initialError={error} />
  );
}

function Auth({
  onSuccess,
  initialError,
}: {
  onSuccess: (user: User) => void;
  initialError: string;
}) {
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      onSuccess(
        await api<User>(
          `/api/auth/${signup ? "signup" : "login"}/`,
          "POST",
          data,
        ),
      );
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="story-copy">
          <span className="eyebrow">
            A LITTLE LESS BUSYWORK. A LOT MORE CONNECTION.
          </span>
          <h1>
            Good conversations.
            <br />
            <em>Great possibilities.</em>
          </h1>
          <p>
            Give your team a home for every customer conversation. Build the
            relationships that move your business forward.
          </p>
          <div className="conversation-art" aria-hidden="true">
            <div className="art-orbit" />
            <div className="art-bubble first">
              <MessageCircle size={22} />
              <span>A conversation starts.</span>
              <span className="small-dot" />
            </div>
            <div className="art-line" />
            <div className="art-bubble second">
              <span className="mini-brand">
                <Sparkles size={20} />
              </span>
              <span>Make it a meaningful one.</span>
              <Check size={18} />
            </div>
            <div className="art-chip">
              <ShieldCheck size={15} /> Your business. Your workspace.
            </div>
          </div>
        </div>
        <div className="story-footer">
          Built for teams. Designed for connection.
          <span>© {new Date().getFullYear()} Nemio</span>
        </div>
      </section>
      <section className="auth-form-wrap">
        <div className="auth-top">
          {signup ? "Already have an account?" : "New to Nemio?"}
          <button
            className="text-button"
            onClick={() => {
              setSignup(!signup);
              setError("");
            }}
          >
            {signup ? "Sign in" : "Create an account"}
            <ArrowRight size={15} />
          </button>
        </div>
        <div className="auth-form">
          <span className="section-icon">
            <ArrowDownLeft size={23} />
          </span>
          <h2>{signup ? "Make room for what’s next." : "Welcome back."}</h2>
          <p>
            {signup
              ? "Start with your account. Your workspace comes next."
              : "Sign in and pick up the conversation."}
          </p>
          <form onSubmit={submit}>
            <ErrorNotice error={error} />
            {signup && (
              <label>
                Your name
                <input
                  name="name"
                  autoComplete="name"
                  placeholder="Alex Morgan"
                  maxLength={150}
                  required
                />
              </label>
            )}
            <label>
              Email address
              <input
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={signup ? 12 : 1}
                maxLength={128}
                placeholder={
                  signup ? "At least 12 characters" : "Enter your password"
                }
                required
              />
            </label>
            <button className="button primary full" disabled={busy}>
              {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </form>
          <div className="secure-note">
            <ShieldCheck size={15} /> A secure home for your team and
            conversations.
          </div>
        </div>
        <div className="auth-bottom">
          Your next great customer relationship starts here.
        </div>
      </section>
    </main>
  );
}

function WorkspaceApp({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const applyWorkspaces = useCallback((all: Workspace[]) => {
    setWorkspaces(all);
    setSelected((current) =>
      all.some((item) => item.id === current) ? current : all[0]?.id || "",
    );
  }, []);
  const refresh = useCallback(async () => {
    applyWorkspaces(await loadWorkspaces());
  }, [applyWorkspaces]);
  const inviteHandled = useRef(false);
  useEffect(() => {
    // An invite link lands here after sign-in; accept it once and drop the token from the URL.
    const token = new URLSearchParams(window.location.search).get("invite");
    if (!token || inviteHandled.current) return;
    inviteHandled.current = true;
    const url = new URL(window.location.href);
    url.searchParams.delete("invite");
    window.history.replaceState(null, "", url.toString());
    api<{ workspace_id: string }>("/api/invitations/accept/", "POST", {
      token,
    })
      .then(async (joined) => {
        applyWorkspaces(await loadWorkspaces());
        setSelected(joined.workspace_id);
        setTab("overview");
      })
      .catch((err) => setError(message(err)));
  }, [applyWorkspaces]);
  useEffect(() => {
    const controller = new AbortController();
    loadWorkspaces(controller.signal)
      .then(applyWorkspaces)
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [applyWorkspaces]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const workspace = await api<Workspace>(
        "/api/workspaces/",
        "POST",
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      await refresh();
      setSelected(workspace.id);
      setCreating(false);
      setTab("overview");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    try {
      await api("/api/auth/logout/", "POST");
      onLogout();
    } catch (err) {
      setError(message(err));
    }
  }
  const current = workspaces.find((item) => item.id === selected);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-select">
          <span className="workspace-avatar">
            {initials(current?.name || "Workspace")}
          </span>
          <div>
            <span className="tiny-label">WORKSPACE</span>
            <select
              aria-label="Current workspace"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
            >
              {!workspaces.length && <option value="">Get started</option>}
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {[
            { id: "overview", label: "Overview", icon: LayoutDashboard },
            { id: "team", label: "Team", icon: Users },
            { id: "activity", label: "Activity", icon: Activity },
            { id: "settings", label: "Settings", icon: Settings },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              onClick={() => setTab(id)}
            >
              <Icon size={18} />
              {label}
              {tab === id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="nav-label next-label">COMING NEXT</div>
        <div className="nav-item muted">
          <MessageCircle size={18} />
          Unified inbox<span className="soon">Soon</span>
        </div>
        <div className="nav-item muted">
          <GitBranch size={18} />
          Automations
        </div>
        <div className="nav-item muted">
          <Sparkles size={18} />
          AI agents
        </div>
        <div className="sidebar-bottom">
          <div className="foundation-card">
            <span className="foundation-icon">
              <Sparkles size={18} />
            </span>
            <strong>A strong start.</strong>
            <p>Your team’s next chapter begins with one workspace.</p>
            <button className="text-button" onClick={() => setCreating(true)}>
              New workspace
              <Plus size={15} />
            </button>
          </div>
          <button className="nav-item" onClick={() => setTab("help")}>
            <CircleHelp size={18} />
            Getting started
          </button>
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
            Workspace <span>/</span>{" "}
            <strong>
              {tab === "overview"
                ? "Overview"
                : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </strong>
          </div>
          <span className="private-badge">
            <ShieldCheck size={14} /> Private workspace
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
          <ErrorNotice error={error} />
          {loading ? (
            <p className="loading-text">Loading your workspaces…</p>
          ) : current ? (
            <WorkspacePanel
              key={`${current.id}:${tab}`}
              workspace={current}
              user={user}
              tab={tab}
              onRefresh={refresh}
            />
          ) : (
            <section className="setup-card">
              <span className="section-icon">
                <GitBranch size={26} />
              </span>
              <span className="eyebrow">LET’S MAKE IT YOURS</span>
              <h1>A home for your business.</h1>
              <p>
                Create a workspace to keep your team, connected accounts, and
                activity together.
              </p>
              <WorkspaceForm create={create} busy={busy} />
            </section>
          )}
        </main>
        <footer className="app-footer">
          <span>Made for more meaningful conversations.</span>
          <span>Nemio · Foundation release</span>
        </footer>
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

function WorkspaceForm({
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
        <ArrowRight size={16} />
      </button>
    </form>
  );
}

function WorkspacePanel({
  workspace,
  user,
  tab,
  onRefresh,
}: {
  workspace: Workspace;
  user: User;
  tab: string;
  onRefresh: () => Promise<void>;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteLink, setInviteLink] = useState("");
  const [memberCount, setMemberCount] = useState(0);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [events, setEvents] = useState<Audit[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const prefix = `/api/workspaces/${workspace.id}`;
  const manager = workspace.role !== "agent";
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [team, channels, health, audit, invites] = await Promise.all([
          api<Page<Member>>(
            `${prefix}/members/`,
            "GET",
            undefined,
            controller.signal,
          ),
          api<Page<Connection>>(
            `${prefix}/connections/`,
            "GET",
            undefined,
            controller.signal,
          ),
          api<Status>(`${prefix}/status/`, "GET", undefined, controller.signal),
          manager
            ? api<Page<Audit>>(
                `${prefix}/audit/`,
                "GET",
                undefined,
                controller.signal,
              )
            : Promise.resolve({ results: [] }),
          manager
            ? api<Page<Invitation>>(
                `${prefix}/invitations/`,
                "GET",
                undefined,
                controller.signal,
              )
            : Promise.resolve({ results: [] as Invitation[] }),
        ]);
        if (!controller.signal.aborted) {
          setMembers(team.results);
          setMemberCount(team.count);
          setConnections(channels.results);
          setStatus(health);
          setEvents(audit.results);
          setInvitations(invites.results);
          setError("");
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(message(err));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    const timer = window.setInterval(load, 15000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [prefix, manager]);
  async function connect() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }
  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await api(
        `${prefix}/`,
        "PATCH",
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      await onRefresh();
      setNotice("Workspace name updated.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function changeRole(member: Member, role: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await api<Member>(
        `${prefix}/members/${member.id}/`,
        "PATCH",
        { role },
      );
      setMembers((list) =>
        list.map((item) => (item.id === updated.id ? updated : item)),
      );
      setNotice("Team role updated.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function sendInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setNotice("");
    setInviteLink("");
    try {
      const created = await api<Invitation>(
        `${prefix}/invitations/`,
        "POST",
        Object.fromEntries(new FormData(form)),
      );
      setInvitations((list) => [
        created,
        ...list.filter((item) => item.email !== created.email),
      ]);
      setInviteLink(created.accept_url || "");
      form.reset();
      setNotice(
        `Invitation created for ${created.email}. Share the link below with them.`,
      );
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function revokeInvite(invitation: Invitation) {
    setBusy(true);
    setError("");
    try {
      await api(`${prefix}/invitations/${invitation.id}/`, "DELETE");
      setInvitations((list) =>
        list.filter((item) => item.id !== invitation.id),
      );
      setInviteLink("");
      setNotice("Invitation revoked.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function removeMember(member: Member) {
    const leaving = member.email === user.email;
    if (
      !window.confirm(
        leaving
          ? "Leave this workspace? You will lose access immediately."
          : `Remove ${member.email} from this workspace?`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await api(`${prefix}/members/${member.id}/`, "DELETE");
      if (leaving) {
        await onRefresh();
        return;
      }
      setMembers((list) => list.filter((item) => item.id !== member.id));
      setMemberCount((count) => count - 1);
      setNotice("Member removed. Their conversations returned to the queue.");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  const canRemove = (member: Member) =>
    member.role !== "owner" &&
    (member.email === user.email ||
      workspace.role === "owner" ||
      (workspace.role === "admin" && member.role === "agent"));
  const heading =
    tab === "overview"
      ? `A fresh start, ${user.name.split(" ")[0] || "welcome"}.`
      : {
          team: "Better, together.",
          activity: "Every change, accounted for.",
          settings: "Your workspace, your way.",
          help: "Start with the essentials.",
        }[tab];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{workspace.name.toUpperCase()}</span>
          <h1>{heading}</h1>
          <p>
            {tab === "overview"
              ? "Your business has a new home. Let’s get it ready for conversation."
              : "A little clarity goes a long way."}
          </p>
        </div>
        <span className="role-pill">{workspace.role}</span>
      </div>
      <ErrorNotice error={error} />
      {notice && (
        <p className="success-notice" role="status">
          {notice}
        </p>
      )}
      {loading ? (
        <p className="loading-text">Loading workspace details…</p>
      ) : (
        <>
          {tab === "overview" && (
            <>
              <section className="welcome-banner">
                <div>
                  <span className="banner-kicker">
                    <span className="small-dot" /> YOUR FOUNDATION IS READY
                  </span>
                  <h2>
                    Big things start with
                    <br />a simple hello.
                  </h2>
                  <p>
                    Your workspace is set up. Get to know your team’s new home,
                    then prepare your first channel.
                  </p>
                  <a href="#channels" className="button dark">
                    Explore your workspace
                    <ArrowRight size={16} />
                  </a>
                </div>
                <div className="banner-art" aria-hidden="true">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <span className="floating-icon ig">
                    <Instagram size={30} />
                  </span>
                  <span className="floating-icon msg">
                    <MessageCircle size={28} />
                  </span>
                  <span className="floating-icon sparkle">
                    <Sparkles size={34} />
                  </span>
                  <span className="hello-card">
                    <span className="hello-dot" />
                    <span>Hello, possibilities.</span>
                    <Check size={16} />
                  </span>
                  <span className="art-star">✳</span>
                </div>
              </section>
              <div className="stats-grid">
                <Stat
                  icon={<Users size={19} />}
                  value={String(memberCount)}
                  label="Workspace members"
                  detail="A shared home for your team"
                />
                <Stat
                  icon={<MessageCircle size={19} />}
                  value={String(
                    connections.filter((item) => !item.is_test).length,
                  )}
                  label="Live channels"
                  detail="Your next step in Phase 1"
                />
                <Stat
                  icon={<ShieldCheck size={19} />}
                  value="Private"
                  label="Workspace access"
                  detail="Only your members can enter"
                />
              </div>
              <div className="overview-grid">
                <section className="panel" id="channels">
                  <div className="panel-title">
                    <h2>Make yourself at home</h2>
                    <span className="subtle">Getting started</span>
                  </div>
                  <div className="checklist-row">
                    <span className="step-check">
                      <Check size={17} />
                    </span>
                    <div>
                      <strong>Create your workspace</strong>
                      <p>{workspace.name} is ready for your team.</p>
                    </div>
                    <span className="done-tag">Done</span>
                  </div>
                  <div className="checklist-row">
                    <span className="step-number">2</span>
                    <div>
                      <strong>Prepare your first channel</strong>
                      <p>Instagram messaging is the next release.</p>
                    </div>
                    <Instagram size={20} className="subtle" />
                  </div>
                  <div className="channel-box">
                    <div className="channel-logo">
                      <Instagram size={23} />
                    </div>
                    <div>
                      <strong>Instagram</strong>
                      <p>
                        {connections.length
                          ? "Local connection test completed"
                          : "Connect where conversations happen"}
                      </p>
                    </div>
                    <span className="outline-tag">Phase 1</span>
                  </div>
                  <div className="channel-note">
                    <p>
                      Live messaging needs Meta setup and review. You can
                      validate the local connection flow now.
                    </p>
                    {manager && (
                      <button
                        className="text-button"
                        onClick={connect}
                        disabled={busy}
                      >
                        {busy ? "Connecting…" : "Test connection setup"}
                        <ArrowRight size={15} />
                      </button>
                    )}
                  </div>
                </section>
                <section className="panel health-panel">
                  <div className="panel-title">
                    <h2>Workspace pulse</h2>
                    <span className="pulse-icon">
                      <Activity size={17} />
                    </span>
                  </div>
                  <p className="panel-subtitle">
                    A live check on the essentials.
                  </p>
                  {Object.entries(status?.checks || {}).map(([name, ok]) => (
                    <div className="health-row" key={name}>
                      <span>
                        {name === "database"
                          ? "Data storage"
                          : name === "redis"
                            ? "Queue connection"
                            : "Background worker"}
                      </span>
                      <span className={ok ? "health-ok" : "health-wait"}>
                        <i />
                        {ok ? "Connected" : "Waiting"}
                      </span>
                    </div>
                  ))}
                  <div className="health-foot">
                    {status?.pending_jobs
                      ? `${status.pending_jobs} background job(s) pending`
                      : "No pending setup jobs"}
                    <span>Refreshes every 15 seconds</span>
                  </div>
                </section>
              </div>
              <section className="panel activity-preview">
                <div className="panel-title">
                  <h2>Recent activity</h2>
                  <span className="subtle">
                    A little history, a clear picture
                  </span>
                </div>
                {manager ? (
                  <ActivityList events={events.slice(0, 3)} />
                ) : (
                  <p className="empty-copy">
                    Workspace activity is visible to owners and admins.
                  </p>
                )}
              </section>
            </>
          )}
          {tab === "team" && (
            <section className="panel">
              <div className="panel-title">
                <h2>
                  Your people <span className="count-badge">{memberCount}</span>
                </h2>
                <span className="subtle">
                  Roles keep responsibilities clear
                </span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Member</th>
                      <th>Email address</th>
                      <th>Role</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((member) => (
                      <tr key={member.id}>
                        <td>
                          <div className="table-member">
                            <span className="user-avatar">
                              {initials(member.name || member.email)}
                            </span>
                            {member.name || "Team member"}
                          </div>
                        </td>
                        <td>{member.email}</td>
                        <td>
                          {workspace.role === "owner" &&
                          member.role !== "owner" ? (
                            <select
                              aria-label={`Role for ${member.email}`}
                              value={member.role}
                              disabled={busy}
                              onChange={(event) =>
                                changeRole(member, event.target.value)
                              }
                            >
                              <option value="agent">Agent</option>
                              <option value="admin">Admin</option>
                            </select>
                          ) : (
                            <span className="role-pill">{member.role}</span>
                          )}
                        </td>
                        <td>
                          {canRemove(member) && (
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => removeMember(member)}
                            >
                              {member.email === user.email ? "Leave" : "Remove"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {manager && (
                <div className="invite-section">
                  <h3>Invite a teammate</h3>
                  <form className="invite-form" onSubmit={sendInvite}>
                    <label>
                      Email address
                      <input
                        name="email"
                        type="email"
                        maxLength={254}
                        required
                        placeholder="teammate@company.com"
                      />
                    </label>
                    <label>
                      Role
                      <select name="role" defaultValue="agent">
                        <option value="agent">Agent</option>
                        {workspace.role === "owner" && (
                          <option value="admin">Admin</option>
                        )}
                      </select>
                    </label>
                    <button className="button primary" disabled={busy}>
                      {busy ? "Inviting…" : "Create invite"}
                      <Plus size={16} />
                    </button>
                  </form>
                  {inviteLink && (
                    <label className="invite-link">
                      One-time invite link, valid for 7 days. It works only for
                      the invited email address and is not shown again.
                      <input
                        value={inviteLink}
                        readOnly
                        onFocus={(event) => event.currentTarget.select()}
                      />
                    </label>
                  )}
                  {invitations.length > 0 && (
                    <ul className="invite-list">
                      {invitations.map((invitation) => (
                        <li key={invitation.id}>
                          <span>{invitation.email}</span>
                          <span className="role-pill">{invitation.role}</span>
                          <span className="subtle">
                            Expires{" "}
                            {new Date(
                              invitation.expires_at,
                            ).toLocaleDateString()}
                          </span>
                          {(workspace.role === "owner" ||
                            invitation.role === "agent") && (
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => revokeInvite(invitation)}
                            >
                              Revoke
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <p className="panel-footnote">
                Owners manage roles and can invite admins. Admins invite agents
                and manage workspace settings. Pending invitations use a seat on
                your plan.
                {memberCount > members.length &&
                  " Showing the first 50 members."}
              </p>
            </section>
          )}
          {tab === "activity" && (
            <section className="panel">
              <div className="panel-title">
                <h2>Workspace audit log</h2>
                <span className="subtle">Latest 50 events</span>
              </div>
              {manager ? (
                <ActivityList events={events} />
              ) : (
                <p className="empty-copy">
                  Only owners and admins can view the workspace audit log.
                </p>
              )}
            </section>
          )}
          {tab === "settings" && (
            <section className="panel settings-panel">
              <h2>Workspace details</h2>
              <p className="panel-subtitle">
                A familiar name helps your team feel at home.
              </p>
              <form onSubmit={rename}>
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
                  <button className="button primary" disabled={busy}>
                    {busy ? "Saving…" : "Save changes"}
                    <Check size={16} />
                  </button>
                )}
              </form>
            </section>
          )}
          {tab === "help" && (
            <section className="panel help-panel">
              <h2>Your first steps with Nemio</h2>
              <p>
                Your account can belong to several workspaces. Use the switcher
                to move between them, or create a new workspace from the
                sidebar.
              </p>
              <h3>Keep your team in sync</h3>
              <p>
                Review members in Team, manage your workspace name in Settings,
                and follow changes in Activity. Workspace owners and admins can
                access the audit log.
              </p>
              <h3>Get ready for Instagram</h3>
              <p>
                The foundation release includes a local connection test. Real
                Instagram messaging, token refresh, and webhook processing
                arrive in Phase 1, after Meta account setup and integration
                validation.
              </p>
              <h3>What comes next</h3>
              <p>
                Visual automations, AI agents, the shared inbox, and billing
                follow as separate releases. Your workspace is the foundation
                for each one.
              </p>
            </section>
          )}
        </>
      )}
    </>
  );
}

function Stat({
  icon,
  value,
  label,
  detail,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  detail: string;
}) {
  return (
    <section className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </section>
  );
}

function ActivityList({ events }: { events: Audit[] }) {
  const names: Record<string, string> = {
    "workspace.created": "Workspace created",
    "workspace.provisioned": "Workspace setup processed",
    "workspace.updated": "Workspace details updated",
    "channel.test_connected": "Instagram test connection completed",
    "membership.role_changed": "A team member’s role changed",
  };
  if (!events.length)
    return (
      <p className="empty-copy">Your workspace activity will appear here.</p>
    );
  return (
    <div>
      {events.map((event) => (
        <div key={event.id} className="activity-row">
          <span className="activity-icon">
            <Check size={15} />
          </span>
          <div>
            <strong>{names[event.action] || event.action}</strong>
            <span>Workspace event</span>
          </div>
          <time dateTime={event.created_at}>
            {new Date(event.created_at).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "numeric",
              minute: "2-digit",
            })}
          </time>
        </div>
      ))}
    </div>
  );
}
