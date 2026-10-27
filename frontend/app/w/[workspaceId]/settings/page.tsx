"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Briefcase,
  Check,
  ChevronDown,
  Clock,
  Copy,
  CreditCard,
  Crown,
  Eye,
  EyeOff,
  FileText,
  HelpCircle,
  History,
  Image as ImageIcon,
  Infinity as InfinityIcon,
  Key,
  Layers,
  Lock,
  Mail,
  MoreVertical,
  Pencil,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  Shield,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  User,
  UserCheck,
  Users,
} from "lucide-react";
import {
  api,
  limit,
  money,
  type Billing,
  type BillingJob,
  type Branding,
  type Connection,
  type Credits,
  type Invitation,
  type Member,
  type Page,
  type User as ApiUser,
  type Workspace,
  when,
} from "@/lib/api";
import { BrandIcon } from "@/lib/brand-icons";
import { loadWorkspaces, useWorkspace } from "@/lib/workspace";
import {
  ErrorNotice,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";
import { startCheckout } from "@/lib/billing";
import { PlanCards, type Interval } from "@/components/plans";

type SettingsTab = "profile" | "meta" | "team" | "subscription" | "workspaces";

const QUICK_COLORS = [
  "#6366f1",
  "#ef4444",
  "#f97316",
  "#f59e0b",
  "#eab308",
  "#10b981",
  "#06b6d4",
  "#3b82f6",
  "#1e293b",
  "#0f172a",
];

const SIDEBAR_BG_COLORS = [
  "#0a0a0a",
  "#0f172a",
  "#1e293b",
  "#1e1b4b",
  "#0f766e",
  "#065f46",
  "#1d4ed8",
  "#312e81",
  "#4c1d95",
  "#18181b",
];

const SIDEBAR_TEXT_COLORS = [
  "#ffffff",
  "#f8fafc",
  "#e2e8f0",
  "#cbd5e1",
  "#94a3b8",
  "#fef08a",
  "#fed7aa",
  "#fbcfe8",
  "#a7f3d0",
  "#bfdbfe",
];

export default function SettingsPage() {
  const { workspace, user: workspaceUser, prefix, manager, refresh } = useWorkspace();
  const feedback = useFeedback();

  // Active top tab
  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");

  // Profile state (real data from auth/me)
  const [currentUser, setCurrentUser] = useState<ApiUser | null>(workspaceUser || null);
  const [fullName, setFullName] = useState("");
  const [emailAddress, setEmailAddress] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [affiliateCopied, setAffiliateCopied] = useState(false);

  // Meta Accounts state (real connections from backend)
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(false);

  // Team state (real members and invitations)
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "agent">("admin");

  // Subscription state (real billing & credits)
  const [billing, setBilling] = useState<Billing | null>(null);
  const [credits, setCredits] = useState<Credits | null>(null);
  const [selectedTopUp, setSelectedTopUp] = useState<number>(10);
  const [autoRechargeEnabled, setAutoRechargeEnabled] = useState(false);
  const [autoRechargeThreshold, setAutoRechargeThreshold] = useState("2.00");
  const [autoRechargeAmount, setAutoRechargeAmount] = useState("10");
  const [planInterval, setPlanInterval] = useState<Interval>("monthly");
  const [pendingPlan, setPendingPlan] = useState("");
  const [preferredPlan, setPreferredPlan] = useState("");
  const plansRef = useRef<HTMLDivElement>(null);

  // Workspaces state (real workspaces & branding)
  const [allWorkspaces, setAllWorkspaces] = useState<Workspace[]>([workspace]);
  const [workspaceName, setWorkspaceName] = useState(workspace.name || "");
  const [workspaceColor, setWorkspaceColor] = useState(
    workspace.branding?.primary_color || "#6366f1"
  );
  const [sidebarBgColor, setSidebarBgColor] = useState("#0a0a0a");
  const [sidebarTextColor, setSidebarTextColor] = useState("#ffffff");
  const [brandName, setBrandName] = useState(
    workspace.branding?.brand_name || workspace.name || "BooSend"
  );
  const [logoUrl, setLogoUrl] = useState(workspace.branding?.logo_url || "");
  const [workspaceSubTab, setWorkspaceSubTab] = useState<"general" | "accounts" | "billing">("general");

  // 1. Load User Profile
  useEffect(() => {
    const controller = new AbortController();
    api<ApiUser>("/api/auth/me/", "GET", undefined, controller.signal)
      .then((data) => {
        setCurrentUser(data);
        setFullName(data.name || "");
        setEmailAddress(data.email || "");
      })
      .catch(() => {
        if (workspaceUser) {
          setCurrentUser(workspaceUser);
          setFullName(workspaceUser.name || "");
          setEmailAddress(workspaceUser.email || "");
        }
      });
    return () => controller.abort();
  }, [workspaceUser]);

  // 2. Load Meta Connections
  const loadConnections = async () => {
    setLoadingConnections(true);
    try {
      const res = await api<any>(`${prefix}/connections/`);
      const list = Array.isArray(res) ? res : Array.isArray(res?.results) ? res.results : [];
      setConnections(list);
    } catch {
      setConnections([]);
    } finally {
      setLoadingConnections(false);
    }
  };

  useEffect(() => {
    loadConnections();
  }, [prefix]);

  // 3. Load Team Members and Pending Invitations
  const loadTeam = async () => {
    try {
      const [membersRes, invitesRes] = await Promise.all([
        api<any>(`${prefix}/members/`).catch(() => ({ results: [] })),
        api<any>(`${prefix}/invitations/`).catch(() => ({ results: [] })),
      ]);
      const mList = Array.isArray(membersRes)
        ? membersRes
        : Array.isArray(membersRes?.results)
        ? membersRes.results
        : [];
      const iList = Array.isArray(invitesRes)
        ? invitesRes
        : Array.isArray(invitesRes?.results)
        ? invitesRes.results
        : [];
      setMembers(mList);
      setInvitations(iList);
    } catch {
      setMembers([]);
      setInvitations([]);
    }
  };

  useEffect(() => {
    loadTeam();
  }, [prefix]);

  // 4. Load Billing & Credits
  const loadBillingAndCredits = async () => {
    try {
      const [billingData, creditsData] = await Promise.all([
        api<Billing>(`${prefix}/billing/`).catch(() => null),
        api<Credits>(`${prefix}/billing/credits/`).catch(() => null),
      ]);
      if (billingData) setBilling(billingData);
      if (creditsData) {
        setCredits(creditsData);
        setAutoRechargeEnabled(creditsData.auto_topup_enabled);
        setAutoRechargeThreshold(((creditsData.auto_topup_threshold_cents || 200) / 100).toFixed(2));
        setAutoRechargeAmount(String(Math.round((creditsData.auto_topup_amount_cents || 1000) / 100)));
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadBillingAndCredits();
  }, [prefix]);

  // Stripe and the pricing page send people back to ?tab=subscription.
  useEffect(() => {
    queueMicrotask(() => {
      const query = new URLSearchParams(window.location.search);
      if (query.get("tab") === "subscription") setActiveTab("subscription");
      if (query.get("interval") === "annual") setPlanInterval("annual");
      if (query.get("plan")) setPreferredPlan(query.get("plan") || "");
      if (query.get("billing") === "success")
        feedback.setNotice("Your plan is updated. It can take a moment to show here.");
      if (query.get("credits") === "success")
        feedback.setNotice("Credits added. Your balance updates in a moment.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (preferredPlan && billing && activeTab === "subscription")
      plansRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [preferredPlan, billing, activeTab]);

  // 5. Load Workspaces and Branding
  useEffect(() => {
    const controller = new AbortController();
    loadWorkspaces(controller.signal)
      .then((list) => {
        if (list.length) setAllWorkspaces(list);
      })
      .catch(() => undefined);

    api<{ own: Branding | null; effective: Branding }>(
      `${prefix}/branding/`,
      "GET",
      undefined,
      controller.signal
    )
      .then((res) => {
        const brand = res.own || res.effective;
        if (brand) {
          if (brand.primary_color) setWorkspaceColor(brand.primary_color);
          if (brand.brand_name) setBrandName(brand.brand_name);
          if (brand.logo_url) setLogoUrl(brand.logo_url);
        }
      })
      .catch(() => undefined);

    setWorkspaceName(workspace.name || "");
    return () => controller.abort();
  }, [prefix, workspace]);

  // Affiliate link copy
  const handleCopyAffiliate = () => {
    const origin = typeof window !== "undefined" ? window.location.origin : "https://boosend.ai";
    const refCode = currentUser?.email ? currentUser.email.split("@")[0] : "member";
    const link = `${origin}/?ref=${encodeURIComponent(refCode)}`;
    navigator.clipboard.writeText(link);
    setAffiliateCopied(true);
    setTimeout(() => setAffiliateCopied(false), 2500);
  };

  // Save profile changes (real PATCH to /api/auth/me/)
  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    await feedback.run(async () => {
      const updated = await api<ApiUser>(`/api/auth/me/`, "PATCH", {
        name: fullName,
        email: emailAddress,
      });
      setCurrentUser(updated);
      await refresh();
    }, "Profile details updated successfully!");
  };

  // Update password (real POST to /api/auth/password/)
  const handleUpdatePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!newPassword || newPassword.length < 8) {
      feedback.setError("Password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      feedback.setError("Passwords do not match.");
      return;
    }
    await feedback.run(async () => {
      await api(`/api/auth/password/`, "POST", {
        password: newPassword,
      });
      setNewPassword("");
      setConfirmPassword("");
    }, "Password updated successfully!");
  };

  // Meta account actions
  const handleConnectMeta = async () => {
    await feedback.run(async () => {
      const res = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
        {}
      );
      if (res.authorization_url) {
        window.location.assign(res.authorization_url);
      }
    });
  };

  const handleReconnectAll = async () => {
    await feedback.run(async () => {
      await api(`${prefix}/connections/refresh/`, "POST");
      await loadConnections();
    }, "Refresh token request sent for Instagram accounts!");
  };

  const handleDisconnectChannel = async (connectionId: string, name: string) => {
    if (!confirm(`Are you sure you want to disconnect ${name}?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/channels/${connectionId}/disconnect/`, "POST");
      await loadConnections();
    }, `${name} disconnected.`);
  };

  // Team invite actions
  const handleInviteMember = async (e: FormEvent) => {
    e.preventDefault();
    if (!inviteEmail) return;
    await feedback.run(async () => {
      await api(`${prefix}/invitations/`, "POST", {
        email: inviteEmail,
        role: inviteRole,
      });
      setShowAddMemberModal(false);
      setInviteEmail("");
      await loadTeam();
    }, `Invitation sent to ${inviteEmail}!`);
  };

  const handleRemoveMember = async (memberId: string, memberName: string) => {
    if (!confirm(`Remove ${memberName} from this workspace?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/members/${memberId}/`, "DELETE");
      await loadTeam();
    }, `${memberName} removed.`);
  };

  const handleRevokeInvitation = async (inviteId: string, email: string) => {
    await feedback.run(async () => {
      await api(`${prefix}/invitations/${inviteId}/`, "DELETE");
      await loadTeam();
    }, `Invitation for ${email} revoked.`);
  };

  // Customer Portal / Billing (redirects to Stripe-hosted customer portal)
  const handleOpenCustomerPortal = async () => {
    await feedback.run(async () => {
      const url = await startCheckout(prefix, { kind: "portal" });
      window.location.assign(url);
    }, "Redirecting to Stripe Customer Portal…");
  };

  // Plans: a new subscriber goes to Stripe Checkout, a subscriber to Stripe's
  // plan-change confirmation for the plan they picked.
  const handleChoosePlan = async (slug: string, chosen: Interval) => {
    setPendingPlan(slug);
    await feedback.run(async () => {
      const url = await startCheckout(prefix, {
        kind: "checkout",
        plan: slug,
        interval: chosen,
      });
      window.location.assign(url);
    }, "Opening Stripe…");
    setPendingPlan("");
  };

  // AI Credits topup
  const handleTopUpCredits = async (amountDollars: number) => {
    setSelectedTopUp(amountDollars);
    await feedback.run(async () => {
      const url = await startCheckout(prefix, {
        kind: "credits",
        amount_cents: amountDollars * 100,
      });
      window.location.assign(url);
    }, `Redirecting to Stripe checkout for $${amountDollars}...`);
  };

  // Save Auto Recharge settings
  const handleToggleAutoRecharge = async () => {
    const nextState = !autoRechargeEnabled;
    setAutoRechargeEnabled(nextState);
    await feedback.run(async () => {
      await api(`${prefix}/billing/credits/`, "PATCH", {
        auto_topup_enabled: nextState,
        auto_topup_threshold_cents: Math.round(parseFloat(autoRechargeThreshold || "2") * 100),
        auto_topup_amount_cents: Math.round(parseFloat(autoRechargeAmount || "10") * 100),
      });
      await loadBillingAndCredits();
    }, `Automatic recharge ${nextState ? "enabled" : "disabled"}.`);
  };

  const handleSaveAutoRechargeSettings = async () => {
    await feedback.run(async () => {
      await api(`${prefix}/billing/credits/`, "PATCH", {
        auto_topup_enabled: autoRechargeEnabled,
        auto_topup_threshold_cents: Math.round(parseFloat(autoRechargeThreshold || "2") * 100),
        auto_topup_amount_cents: Math.round(parseFloat(autoRechargeAmount || "10") * 100),
      });
      await loadBillingAndCredits();
    }, "Automatic recharge settings saved.");
  };

  // Save Workspace & Branding changes
  const handleSaveWorkspace = async () => {
    await feedback.run(async () => {
      await api(`${prefix}/`, "PATCH", {
        name: workspaceName,
      });
      await api(`${prefix}/branding/`, "PUT", {
        brand_name: brandName,
        primary_color: workspaceColor,
        logo_url: logoUrl,
      });
      await refresh();
    }, "Workspace settings saved successfully!");
  };

  // Filter connections into Instagram and Facebook/Meta
  const connectionList = Array.isArray(connections) ? connections : [];
  const memberList = Array.isArray(members) ? members : [];
  const inviteList = Array.isArray(invitations) ? invitations : [];
  const workspaceList = Array.isArray(allWorkspaces) ? allWorkspaces : [];

  const instagramAccounts = connectionList.filter(
    (c) => c && c.provider === "instagram" && c.status !== "disconnected"
  );
  const facebookPages = connectionList.filter(
    (c) => c && (c.provider === "meta" || c.provider === "facebook") && c.status !== "disconnected"
  );

  // Separate workspace owner from general members
  const ownerMember = memberList.find((m) => m && m.role === "owner");
  const nonOwnerMembers = memberList.filter((m) => m && m.role !== "owner");

  // Calculated credits balance in dollars
  const creditBalanceDisplay = credits
    ? `$${(parseInt(credits.balance_cents || "0", 10) / 100).toFixed(2)}`
    : "$0.00";

  const userInitial = (currentUser?.name || currentUser?.email || "M").charAt(0).toUpperCase();

  return (
    <div className="boosend-settings-page">
      {/* Top Header */}
      <div className="settings-page-header">
        <div>
          <h1 className="settings-main-title">Settings</h1>
          <p className="settings-main-subtitle">
            Manage your account and automation preferences
          </p>
        </div>

        {/* Affiliate Link Button */}
        <button
          type="button"
          className="get-affiliate-link-btn"
          onClick={handleCopyAffiliate}
          title="Click to copy your personal affiliate link"
        >
          <span className="affiliate-flower-icon">🌼</span>
          {affiliateCopied ? "Affiliate Link Copied!" : "Get Affiliate Link"}
        </button>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {/* Top Navigation Tabs */}
      <div className="settings-nav-tabs-bar">
        <button
          type="button"
          className={`settings-nav-tab ${activeTab === "profile" ? "active" : ""}`}
          onClick={() => setActiveTab("profile")}
        >
          <User size={15} />
          Profile
        </button>

        <button
          type="button"
          className={`settings-nav-tab ${activeTab === "meta" ? "active" : ""}`}
          onClick={() => setActiveTab("meta")}
        >
          <InfinityIcon size={16} />
          Meta Accounts
        </button>

        <button
          type="button"
          className={`settings-nav-tab ${activeTab === "team" ? "active" : ""}`}
          onClick={() => setActiveTab("team")}
        >
          <Users size={15} />
          Team
        </button>

        <button
          type="button"
          className={`settings-nav-tab ${activeTab === "subscription" ? "active" : ""}`}
          onClick={() => setActiveTab("subscription")}
        >
          <Crown size={15} />
          Subscription
        </button>

        <button
          type="button"
          className={`settings-nav-tab ${activeTab === "workspaces" ? "active" : ""}`}
          onClick={() => setActiveTab("workspaces")}
        >
          <Briefcase size={15} />
          Workspaces
        </button>
      </div>

      {/* =========================================================================
          TAB 1: PROFILE
          ========================================================================= */}
      {activeTab === "profile" && (
        <div className="settings-tab-content stack-cards">
          {/* Card 1: Profile details */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <User size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Profile</h2>
                  <p className="card-subtitle">Update your name, email and profile photo.</p>
                </div>
              </div>
            </div>

            <form onSubmit={handleSaveProfile} className="settings-profile-form">
              <div className="profile-details-grid">
                {/* Left column: Avatar */}
                <div className="profile-avatar-col">
                  <div className="profile-avatar-circle">
                    <span>{userInitial}</span>
                  </div>
                  <div className="avatar-user-name">
                    {fullName || currentUser?.name || "User"}
                  </div>
                  <label className="change-photo-link">
                    Change photo
                    <input
                      type="file"
                      accept="image/*"
                      style={{ display: "none" }}
                      onChange={() => {
                        feedback.setNotice("Photo selected for upload on Save changes.");
                      }}
                    />
                  </label>
                </div>

                {/* Right column: Form fields */}
                <div className="profile-fields-col">
                  <div className="form-group">
                    <label className="field-label" htmlFor="settings-full-name">Full Name</label>
                    <input id="settings-full-name"
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your full name"
                      className="settings-text-input"
                    />
                  </div>

                  <div className="form-group">
                    <label className="field-label" htmlFor="settings-email-address">Email Address</label>
                    <input id="settings-email-address"
                      type="email"
                      value={emailAddress}
                      onChange={(e) => setEmailAddress(e.target.value)}
                      placeholder="Your email address"
                      className="settings-text-input"
                    />
                  </div>

                  <div className="form-group">
                    <label className="field-label">Connected accounts</label>
                    <div className="connected-account-box">
                      <div className="connected-acc-left">
                        <div className="connected-acc-icon">
                          <Mail size={14} />
                        </div>
                        <div>
                          <div className="connected-acc-type-row">
                            <span className="connected-acc-type">Email</span>
                            <span className="primary-green-badge">PRIMARY</span>
                          </div>
                          <div className="connected-acc-value">
                            {currentUser?.email || emailAddress}
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        className="connected-acc-disconnect-btn"
                        onClick={() => {
                          feedback.setError("Cannot disconnect primary account email.");
                        }}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom action row */}
              <div className="settings-card-footer">
                <div className="footer-status-hint">
                  <Mail size={14} /> Connected via Email
                </div>

                <button
                  type="submit"
                  className="save-changes-black-btn"
                  disabled={feedback.busy}
                >
                  Save changes
                </button>
              </div>
            </form>
          </div>

          {/* Card 2: Change password */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2 className="card-title">Change password</h2>
                <p className="card-subtitle">Enter a new password and confirm it.</p>
              </div>
            </div>

            <form onSubmit={handleUpdatePassword} className="change-password-form">
              <div className="password-fields-two-col">
                <div className="form-group">
                  <label className="field-label" htmlFor="settings-new-password">New password</label>
                  <div className="password-input-wrapper">
                    <input id="settings-new-password"
                      type={showNewPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="••••••••"
                      className="settings-text-input"
                    />
                    <button
                      type="button"
                      className="password-toggle-eye"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      aria-label="Toggle password view"
                    >
                      {showNewPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  <span className="field-helper-note">Minimum 8 characters</span>
                </div>

                <div className="form-group">
                  <label className="field-label" htmlFor="settings-confirm-password">Confirm Password</label>
                  <div className="password-input-wrapper">
                    <input id="settings-confirm-password"
                      type={showConfirmPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="settings-text-input"
                    />
                    <button
                      type="button"
                      className="password-toggle-eye"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      aria-label="Toggle confirm password view"
                    >
                      {showConfirmPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="settings-card-footer justify-end">
                <button
                  type="submit"
                  className="update-password-btn"
                  disabled={!newPassword || feedback.busy}
                >
                  Update password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: META ACCOUNTS
          ========================================================================= */}
      {activeTab === "meta" && (
        <div className="settings-tab-content stack-cards">
          {/* Card 1: Instagram Accounts */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <BrandIcon name="instagram" size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Instagram Accounts</h2>
                  <p className="card-subtitle">Manage your connected Instagram accounts.</p>
                </div>
              </div>

              <button
                type="button"
                className="add-black-btn"
                onClick={handleConnectMeta}
              >
                <Plus size={15} /> Add Account
              </button>
            </div>

            {loadingConnections ? (
              <div className="empty-channel-box">Loading connected Instagram accounts...</div>
            ) : instagramAccounts.length > 0 ? (
              <div className="stack-cards" style={{ gap: 10 }}>
                {instagramAccounts.map((acc, idx) => (
                  <div key={acc.id} className="connected-channel-card-row">
                    <div className="channel-info-left">
                      <div className="channel-avatar-circle instagram">
                        <BrandIcon name="instagram" size={18} mono />
                      </div>
                      <div>
                        <div className="channel-name-title-row">
                          <span className="channel-handle">
                            {acc.display_name.startsWith("@") ? acc.display_name : `@${acc.display_name}`}
                          </span>
                          {idx === 0 && <span className="primary-gray-badge">Primary</span>}
                          {acc.is_test && <span className="primary-gray-badge">Test Mode</span>}
                        </div>
                        <div className="channel-meta-stats">
                          {acc.followers !== null ? `${acc.followers} followers · ` : ""}
                          Connected {acc.expires_at ? new Date(acc.expires_at).toLocaleDateString() : "recently"}
                        </div>
                        {acc.last_refreshed_at && (
                          <div className="channel-synced-time">
                            <Clock size={12} /> Synced {new Date(acc.last_refreshed_at).toLocaleString()}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="channel-actions-right">
                      <span className="status-active-green">
                        <Check size={14} /> {acc.status === "active" ? "Active" : acc.status}
                      </span>
                      <button
                        type="button"
                        className="reconnect-text-btn"
                        onClick={handleReconnectAll}
                      >
                        <RotateCw size={13} /> Reconnect
                      </button>
                      <button
                        type="button"
                        className="disconnect-red-btn"
                        onClick={() => handleDisconnectChannel(acc.id, acc.display_name)}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-channel-box">
                No Instagram accounts connected. Click &ldquo;+ Add Account&rdquo; to connect your Instagram profile.
              </div>
            )}
          </div>

          {/* Card 2: Facebook Pages */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <BrandIcon name="facebook" size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Facebook Pages</h2>
                  <p className="card-subtitle">
                    Manage your connected Facebook Pages and Messenger access.
                  </p>
                </div>
              </div>

              <button
                type="button"
                className="add-facebook-blue-btn"
                onClick={handleConnectMeta}
              >
                <Plus size={15} /> Add Facebook Page
              </button>
            </div>

            {loadingConnections ? (
              <div className="empty-channel-box">Loading connected Facebook Pages...</div>
            ) : facebookPages.length > 0 ? (
              <div className="stack-cards" style={{ gap: 10 }}>
                {facebookPages.map((page, idx) => (
                  <div key={page.id} className="connected-channel-card-row">
                    <div className="channel-info-left">
                      <div className="channel-avatar-circle facebook">
                        <BrandIcon name="facebook" size={18} mono />
                      </div>
                      <div>
                        <div className="channel-name-title-row">
                          <span className="channel-handle">{page.display_name}</span>
                          {idx === 0 && <span className="primary-blue-badge">Primary</span>}
                        </div>
                        <div className="channel-meta-stats">
                          Facebook Page · Messenger connected
                        </div>
                      </div>
                    </div>

                    <div className="channel-actions-right">
                      <button
                        type="button"
                        className="disconnect-red-btn"
                        onClick={() => handleDisconnectChannel(page.id, page.display_name)}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-channel-box">
                No Facebook Pages connected. Click &ldquo;+ Add Facebook Page&rdquo; to connect.
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 3: TEAM
          ========================================================================= */}
      {activeTab === "team" && (
        <div className="settings-tab-content">
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Users size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Team Members</h2>
                  <p className="card-subtitle">{workspaceName || workspace.name} workspace</p>
                </div>
              </div>

              <button
                type="button"
                className="add-black-btn"
                onClick={() => setShowAddMemberModal(true)}
              >
                <Plus size={15} /> Add Member
              </button>
            </div>

            {/* Workspace Owner Section */}
            <div className="team-section-wrapper">
              <div className="team-section-eyebrow">WORKSPACE OWNER</div>

              <div className="team-member-row owner-row">
                <div className="team-member-info-left">
                  <div className="team-avatar-circle owner">
                    <span>
                      {(ownerMember?.name || currentUser?.name || currentUser?.email || "M")
                        .charAt(0)
                        .toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <div className="team-member-name">
                      {ownerMember?.name || currentUser?.name || "Workspace Owner"}
                    </div>
                    <div className="team-member-email">
                      {ownerMember?.email || currentUser?.email}
                    </div>
                  </div>
                </div>

                <span className="owner-black-badge">Owner</span>
              </div>
            </div>

            {/* Other Members & Invitations */}
            {nonOwnerMembers.length > 0 || inviteList.length > 0 ? (
              <div className="team-members-list" style={{ marginTop: 16 }}>
                <div className="team-section-eyebrow">MEMBERS & INVITATIONS</div>
                <div className="stack-cards" style={{ gap: 10 }}>
                  {nonOwnerMembers.map((m) => (
                    <div key={m.id} className="team-member-row">
                      <div className="team-member-info-left">
                        <div className="team-avatar-circle">
                          <span>{m.name ? m.name.charAt(0).toUpperCase() : "U"}</span>
                        </div>
                        <div>
                          <div className="team-member-name">{m.name}</div>
                          <div className="team-member-email">{m.email}</div>
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className="primary-gray-badge">{m.role}</span>
                        <button
                          type="button"
                          className="disconnect-red-btn"
                          onClick={() => handleRemoveMember(m.id, m.name)}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}

                  {inviteList.map((inv) => (
                    <div key={inv.id} className="team-member-row" style={{ opacity: 0.85 }}>
                      <div className="team-member-info-left">
                        <div className="team-avatar-circle" style={{ background: "#fef3c7", color: "#b45309" }}>
                          <span>✉</span>
                        </div>
                        <div>
                          <div className="team-member-name">{inv.email}</div>
                          <div className="team-member-email">Invitation Pending</div>
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className="primary-gray-badge">{inv.role}</span>
                        <button
                          type="button"
                          className="disconnect-red-btn"
                          onClick={() => handleRevokeInvitation(inv.id, inv.email)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              /* Empty state */
              <div className="team-empty-state-box">
                <div className="team-empty-icon-circle">
                  <Users size={24} />
                </div>
                <h3 className="team-empty-title">No team members yet</h3>
                <p className="team-empty-sub">
                  Invite your team to collaborate on this workspace.
                </p>
                <button
                  type="button"
                  className="add-first-member-btn"
                  onClick={() => setShowAddMemberModal(true)}
                >
                  <Plus size={15} /> Add Your First Team Member
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 4: SUBSCRIPTION
          ========================================================================= */}
      {activeTab === "subscription" && (
        <div className="settings-tab-content stack-cards">
          {/* Card 1: Current Plan */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Crown size={18} className="card-icon gold-icon" />
                <div>
                  <h2 className="card-title">Current Plan</h2>
                  <p className="card-subtitle">Your active plan and usage.</p>
                </div>
              </div>

              <div className="plan-header-actions">
                <button
                  type="button"
                  className="customer-portal-white-btn"
                  disabled={feedback.busy}
                  onClick={handleOpenCustomerPortal}
                >
                  <span className="portal-dollar-icon">$</span> Customer Portal
                </button>
                <button
                  type="button"
                  className="upgrade-plan-black-btn"
                  onClick={() =>
                    plansRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
                  }
                >
                  Upgrade Plan
                </button>
              </div>
            </div>

            {/* Dark Navy/Black Plan Banner Card */}
            <div className="subscription-plan-banner">
              <div className="plan-banner-top">
                <h3 className="plan-banner-title">
                  {billing?.plan ? billing.plan.charAt(0).toUpperCase() + billing.plan.slice(1) : "Pro"}
                </h3>
                <span className="plan-banner-billed">
                  Billed {billing?.interval || "monthly"}
                </span>
              </div>

              <div className="plan-stats-four-col">
                <div className="plan-stat-item">
                  <span className="stat-label">Automations</span>
                  <span className="stat-val">Unlimited</span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">Instagram Accounts</span>
                  <span className="stat-val">
                    {limit(billing?.channel_limit)}
                  </span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">DMs This Month</span>
                  <span className="stat-val">
                    {billing ? `${billing.used} / ${limit(billing.usage_limit)}` : "Unlimited"}
                  </span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">AI Credits</span>
                  <span className="stat-val">{creditBalanceDisplay}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: AI Credits */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <span className="ai-badge-pill">AI</span>
                <div>
                  <h2 className="card-title">AI Credits</h2>
                  <p className="card-subtitle">Manage your AI credit balance.</p>
                </div>
              </div>

              <div className="ai-credits-pricing-hint">
                <span className="hint-label">Pricing</span>
                <span className="hint-value">{creditBalanceDisplay}</span>
              </div>
            </div>

            <div className="ai-credits-body">
              {/* Top Up Credits Options */}
              <div className="topup-section">
                <label className="field-label">Top Up Credits</label>
                <div className="topup-amount-boxes-row">
                  {[10, 25, 50, 100].map((amt) => (
                    <button
                      type="button"
                      key={amt}
                      className={`topup-amount-btn ${selectedTopUp === amt ? "selected" : ""}`}
                      onClick={() => handleTopUpCredits(amt)}
                    >
                      ${amt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Automatic Recharge */}
              <div className="automatic-recharge-section">
                <div className="auto-recharge-header-row">
                  <div className="auto-recharge-title-with-hint">
                    <span>Automatic Recharge</span>
                    <HelpCircle size={14} className="info-icon" />
                  </div>
                  <button
                    type="button"
                    className={`toggle-switch-pill ${autoRechargeEnabled ? "active" : ""}`}
                    onClick={handleToggleAutoRecharge}
                    aria-label="Toggle automatic recharge"
                  >
                    <span className="toggle-switch-thumb" />
                  </button>
                </div>

                <div className="auto-recharge-inputs-row">
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="field-label" htmlFor="settings-trigger-when-balance-drops-below">Trigger when balance drops below</label>
                    <div className="dollar-input-wrapper">
                      <span className="currency-symbol">$</span>
                      <input id="settings-trigger-when-balance-drops-below"
                        type="text"
                        value={autoRechargeThreshold}
                        onChange={(e) => setAutoRechargeThreshold(e.target.value)}
                        onBlur={handleSaveAutoRechargeSettings}
                        className="dollar-text-input"
                      />
                    </div>
                  </div>

                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="field-label" htmlFor="settings-recharge-amount">Recharge amount</label>
                    <div className="custom-select-box">
                      <select id="settings-recharge-amount"
                        value={autoRechargeAmount}
                        onChange={(e) => {
                          setAutoRechargeAmount(e.target.value);
                          handleSaveAutoRechargeSettings();
                        }}
                        className="native-page-select"
                      >
                        <option value="10">$10</option>
                        <option value="25">$25</option>
                        <option value="50">$50</option>
                        <option value="100">$100</option>
                      </select>
                      <ChevronDown size={15} className="select-dropdown-chevron" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Credits Remaining Footer */}
              <div className="credits-remaining-footer-bar">
                <div>
                  <div className="credits-rem-title">Credits Remaining</div>
                  <div className="credits-rem-sub">Available balance for AI messages</div>
                </div>
                <div className="credits-rem-val">{creditBalanceDisplay}</div>
              </div>

              {credits && credits.transactions.length > 0 && (
                <div className="credit-activity">
                  <label className="field-label">Recent credit activity</label>
                  <Table head={["When", "Type", "Detail", "Amount", "Balance"]}>
                    {credits.transactions.slice(0, 10).map((row) => (
                      <tr key={row.id}>
                        <td>{when(row.created_at)}</td>
                        <td>{row.type.replace("_", " ")}</td>
                        <td>
                          {row.model
                            ? `${row.model} · ${row.tokens_in} in / ${row.tokens_out} out`
                            : row.description}
                        </td>
                        <td>
                          {(Number(row.amount_cents) / 100).toLocaleString(undefined, {
                            style: "currency",
                            currency: "USD",
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 4,
                          })}
                        </td>
                        <td>{money(Math.round(Number(row.remaining_balance_cents)))}</td>
                      </tr>
                    ))}
                  </Table>
                </div>
              )}
            </div>
          </div>

          {/* Card 3: Plans */}
          <div className="settings-card" ref={plansRef} id="plans">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Sparkles size={18} className="card-icon gold-icon" />
                <div>
                  <h2 className="card-title">Plans</h2>
                  <p className="card-subtitle">
                    Pick a plan to subscribe or switch. Payment and confirmation happen in Stripe.
                  </p>
                </div>
              </div>
            </div>
            {!billing ? (
              <p className="card-subtitle">Loading plans…</p>
            ) : workspace.parent ? (
              <p className="card-subtitle">
                This workspace is managed by your agency, which handles its plan and billing.
              </p>
            ) : workspace.role !== "owner" ? (
              <p className="card-subtitle">Only the workspace owner can change the plan.</p>
            ) : !billing.stripe_configured ? (
              <p className="card-subtitle">
                Stripe is not configured for this deployment, so plans cannot be changed here.
              </p>
            ) : (
              <>
                {preferredPlan && (
                  <p className="card-subtitle" style={{ marginBottom: 12 }}>
                    You picked{" "}
                    {billing.catalog.find((p) => p.slug === preferredPlan)?.name || preferredPlan}{" "}
                    on the pricing page. Choose it below to continue.
                  </p>
                )}
                <PlanCards
                  plans={billing.catalog.filter((p) => p.slug !== "free")}
                  interval={planInterval}
                  onInterval={setPlanInterval}
                  currentPlan={billing.plan}
                  currentInterval={billing.interval}
                  busySlug={pendingPlan}
                  trialDays={billing.trial_days}
                  onChoose={handleChoosePlan}
                />
              </>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 5: WORKSPACES
          ========================================================================= */}
      {activeTab === "workspaces" && (
        <div className="settings-tab-content workspaces-layout-grid">
          {/* Left Column: Workspaces List */}
          <div className="workspaces-left-column">
            <div className="workspaces-list-header">
              <div>
                <h3 className="ws-list-title">Workspaces</h3>
                <span className="ws-usage-count">
                  {allWorkspaces.length} workspace{allWorkspaces.length > 1 ? "s" : ""}
                </span>
              </div>
              <button
                type="button"
                className="ws-new-btn"
                onClick={() => {
                  window.location.assign("/onboarding?mode=new_workspace");
                }}
              >
                <Plus size={14} /> New
              </button>
            </div>

            <div className="ws-eyebrow">MY WORKSPACES</div>

            <div className="my-workspaces-stack">
              {workspaceList.map((ws) => {
                const isCurrent = ws.id === workspace.id;
                return (
                  <Link
                    key={ws.id}
                    href={`/w/${ws.id}/${isCurrent ? "settings" : "overview"}`}
                    className="active-workspace-card-item"
                    style={{
                      borderColor: isCurrent ? "#0f172a" : "#e2e8f0",
                      textDecoration: "none",
                      marginBottom: 8,
                      display: "flex",
                    }}
                  >
                    <div
                      className="ws-card-avatar"
                      style={{
                        background: ws.branding?.primary_color || (isCurrent ? workspaceColor : "#6366f1"),
                      }}
                    >
                      <span>{(ws.name || "W").charAt(0).toUpperCase()}</span>
                    </div>
                    <div className="ws-card-info">
                      <div className="ws-card-name-row">
                        <span className="ws-name-text">{ws.name}</span>
                        {isCurrent && <span className="current-badge-pill">Current</span>}
                      </div>
                      <div className="ws-card-role-meta">
                        {ws.role || "Member"} · Active
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Right Column: Active Workspace Settings */}
          <div className="workspaces-right-column">
            <div className="ws-settings-header-banner">
              <div className="ws-banner-avatar" style={{ background: workspaceColor }}>
                <span>{(workspaceName || workspace.name || "W").charAt(0).toUpperCase()}</span>
              </div>
              <div>
                <span className="settings-for-label">Settings for</span>
                <h2 className="ws-banner-title">{workspaceName || workspace.name}</h2>
              </div>
            </div>

            {/* Sub-tabs: General, Accounts, Billing */}
            <div className="ws-subtabs-row">
              <button
                type="button"
                className={`ws-subtab-btn ${workspaceSubTab === "general" ? "active" : ""}`}
                onClick={() => setWorkspaceSubTab("general")}
              >
                General
              </button>
              <button
                type="button"
                className={`ws-subtab-btn ${workspaceSubTab === "accounts" ? "active" : ""}`}
                onClick={() => {
                  setWorkspaceSubTab("accounts");
                  setActiveTab("meta");
                }}
              >
                Accounts
              </button>
              <button
                type="button"
                className={`ws-subtab-btn ${workspaceSubTab === "billing" ? "active" : ""}`}
                onClick={() => {
                  setWorkspaceSubTab("billing");
                  setActiveTab("subscription");
                }}
              >
                Billing
              </button>
            </div>

            {/* BASICS */}
            <div className="ws-section-block">
              <div className="ws-block-eyebrow">BASICS</div>

              <div className="form-group">
                <label className="field-label" htmlFor="settings-workspace-name">Workspace Name</label>
                <input id="settings-workspace-name"
                  type="text"
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  className="settings-text-input"
                />
              </div>

              <div className="form-group" style={{ marginTop: 14 }}>
                <label className="field-label" htmlFor="settings-workspace-color">Workspace Color</label>
                <div className="color-input-hex-row">
                  <div className="color-preview-box" style={{ background: workspaceColor }} />
                  <input id="settings-workspace-color"
                    type="text"
                    value={workspaceColor}
                    onChange={(e) => setWorkspaceColor(e.target.value)}
                    className="hex-code-input"
                  />
                </div>

                <div className="quick-select-row">
                  <span className="quick-select-label">Quick select:</span>
                  <div className="swatch-dots-row">
                    {QUICK_COLORS.map((c) => (
                      <button
                        type="button"
                        key={c}
                        className={`color-dot-swatch ${workspaceColor === c ? "active" : ""}`}
                        style={{ background: c }}
                        onClick={() => setWorkspaceColor(c)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* SIDEBAR APPEARANCE */}
            <div className="ws-section-block">
              <div className="ws-block-title">Sidebar appearance</div>
              <p className="ws-block-desc">
                Customize the background and text color of your main navigation sidebar.
              </p>

              {/* Live Preview Bar of Sidebar */}
              <div
                className="sidebar-live-preview-bar"
                style={{ background: sidebarBgColor, color: sidebarTextColor }}
              >
                <div className="preview-ws-icon" style={{ background: workspaceColor }}>
                  {(workspaceName || "W").charAt(0).toUpperCase()}
                </div>
                <div className="preview-copy-col">
                  <span className="preview-ws-name">{workspaceName || "Workspace"}</span>
                  <span className="preview-subtitle">Preview of your sidebar</span>
                </div>
              </div>

              <div className="sidebar-color-controls">
                <div className="form-group">
                  <label className="field-label">Side Bar Color</label>
                  <div className="swatch-with-hex-row">
                    <div className="swatch-dots-row">
                      {SIDEBAR_BG_COLORS.map((c) => (
                        <button
                          type="button"
                          key={c}
                          className={`color-dot-swatch ${sidebarBgColor === c ? "active" : ""}`}
                          style={{ background: c }}
                          onClick={() => setSidebarBgColor(c)}
                        />
                      ))}
                    </div>
                    <input
                      type="text"
                      value={sidebarBgColor}
                      onChange={(e) => setSidebarBgColor(e.target.value)}
                      className="sidebar-hex-field"
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: 14 }}>
                  <label className="field-label">Sidebar Text Color</label>
                  <div className="swatch-with-hex-row">
                    <div className="swatch-dots-row">
                      {SIDEBAR_TEXT_COLORS.map((c) => (
                        <button
                          type="button"
                          key={c}
                          className={`color-dot-swatch ${sidebarTextColor === c ? "active" : ""}`}
                          style={{ background: c }}
                          onClick={() => setSidebarTextColor(c)}
                        />
                      ))}
                    </div>
                    <input
                      type="text"
                      value={sidebarTextColor}
                      onChange={(e) => setSidebarTextColor(e.target.value)}
                      className="sidebar-hex-field"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* BRANDING */}
            <div className="ws-section-block">
              <div className="ws-block-eyebrow">BRANDING</div>

              <div className="form-group">
                <label className="field-label">Logo</label>
                <div className="logo-upload-wrapper">
                  <div className="logo-ghost-box">
                    {logoUrl ? (
                      <img
                        src={logoUrl}
                        alt="Logo"
                        style={{ width: "100%", height: "100%", objectFit: "contain", borderRadius: 8 }}
                      />
                    ) : (
                      <Sparkles size={22} className="ghost-icon" />
                    )}
                  </div>
                  <div>
                    <label className="upload-file-btn">
                      Upload
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: "none" }}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            const reader = new FileReader();
                            reader.onload = () => {
                              setLogoUrl(reader.result as string);
                            };
                            reader.readAsDataURL(file);
                          }
                        }}
                      />
                    </label>
                    <span className="file-format-hint">PNG, JPG, GIF or WebP - max 5MB</span>
                  </div>
                </div>
              </div>

              <div className="form-group" style={{ marginTop: 14 }}>
                <label className="field-label" htmlFor="settings-brand-name">Brand name</label>
                <input id="settings-brand-name"
                  type="text"
                  value={brandName}
                  onChange={(e) => setBrandName(e.target.value)}
                  className="settings-text-input"
                />
                <span className="field-helper-note">
                  Shown in the sidebar instead of &ldquo;BooSend&rdquo;.
                </span>
              </div>

              <div className="ws-save-btn-row">
                <button
                  type="button"
                  className="save-changes-black-btn"
                  onClick={handleSaveWorkspace}
                  disabled={feedback.busy}
                >
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Add Team Member */}
      {showAddMemberModal && (
        <div className="settings-modal-backdrop" onClick={() => setShowAddMemberModal(false)}>
          <div className="settings-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Invite Team Member</h3>
            <p className="modal-sub">
              Collaborate with colleagues on {workspaceName || workspace.name}.
            </p>

            <form onSubmit={handleInviteMember} style={{ marginTop: 16 }}>
              <div className="form-group">
                <label className="field-label" htmlFor="settings-email-address-2">Email Address</label>
                <input id="settings-email-address-2"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com"
                  className="settings-text-input"
                  required
                />
              </div>

              <div className="form-group" style={{ marginTop: 12 }}>
                <label className="field-label" htmlFor="settings-role">Role</label>
                <div className="custom-select-box">
                  <select id="settings-role"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as "admin" | "agent")}
                    className="native-page-select"
                  >
                    <option value="admin">Admin (full access)</option>
                    <option value="agent">Agent (conversations & CRM only)</option>
                  </select>
                  <ChevronDown size={15} className="select-dropdown-chevron" />
                </div>
              </div>

              <div className="modal-actions-row">
                <button
                  type="button"
                  className="modal-cancel-btn"
                  onClick={() => setShowAddMemberModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="save-changes-black-btn">
                  Send Invitation
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
