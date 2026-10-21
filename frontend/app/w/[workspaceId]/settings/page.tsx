"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Briefcase,
  Camera,
  Check,
  ChevronDown,
  Clock,
  Copy,
  CreditCard,
  Crown,
  Eye,
  EyeOff,
  Facebook,
  FileText,
  HelpCircle,
  History,
  Image as ImageIcon,
  Infinity as InfinityIcon,
  Instagram,
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
  message,
  type Branding,
  type ClientWorkspace,
  type Connection,
  type Member,
  type Page,
} from "@/lib/api";
import { loadWorkspaces, useWorkspace } from "@/lib/workspace";
import { ErrorNotice, SuccessNotice, useFeedback } from "@/components/ui";

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
  const { workspace, user, prefix, manager, refresh } = useWorkspace();
  const feedback = useFeedback();

  // Active top tab
  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");

  // Profile state
  const [fullName, setFullName] = useState(user?.name || "Muhammad Tahir");
  const [emailAddress, setEmailAddress] = useState(user?.email || "mtahirmalik3600921@gmail.com");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [affiliateCopied, setAffiliateCopied] = useState(false);

  // Meta Accounts state
  const [instagramConnected, setInstagramConnected] = useState(true);
  const [facebookConnected, setFacebookConnected] = useState(true);

  // Team state
  const [members, setMembers] = useState<Member[]>([]);
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "agent">("admin");

  // Subscription state
  const [selectedTopUp, setSelectedTopUp] = useState<number>(10);
  const [autoRechargeEnabled, setAutoRechargeEnabled] = useState(false);
  const [autoRechargeThreshold, setAutoRechargeThreshold] = useState("2.00");
  const [autoRechargeAmount, setAutoRechargeAmount] = useState("10");

  // Workspaces state
  const [allWorkspaces, setAllWorkspaces] = useState<typeof workspace[]>([workspace]);
  const [workspaceName, setWorkspaceName] = useState(workspace.name || "Muhammad Tahir's Workspace");
  const [workspaceColor, setWorkspaceColor] = useState("#6366f1");
  const [sidebarBgColor, setSidebarBgColor] = useState("#0a0a0a");
  const [sidebarTextColor, setSidebarTextColor] = useState("#ffffff");
  const [brandName, setBrandName] = useState("BooSend");
  const [workspaceSubTab, setWorkspaceSubTab] = useState<"general" | "accounts" | "billing">("general");

  // Load team members and workspaces
  useEffect(() => {
    const controller = new AbortController();
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((res) => {
        setMembers(res.results || []);
      })
      .catch(() => undefined);

    loadWorkspaces(controller.signal)
      .then((list) => {
        if (list.length) setAllWorkspaces(list);
      })
      .catch(() => undefined);

    return () => controller.abort();
  }, [prefix]);

  // Affiliate link copy
  const handleCopyAffiliate = () => {
    const link = `https://boosend.ai/?ref=${encodeURIComponent(user?.email || "tahir")}`;
    navigator.clipboard.writeText(link);
    setAffiliateCopied(true);
    setTimeout(() => setAffiliateCopied(false), 2500);
  };

  // Save profile changes
  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    await feedback.run(async () => {
      await api(`/api/auth/me/`, "PATCH", {
        name: fullName,
        email: emailAddress,
      });
      await refresh();
    }, "Profile details updated successfully!");
  };

  // Update password
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

  // Save workspace settings
  const handleSaveWorkspace = async () => {
    await feedback.run(async () => {
      await api(`${prefix}/`, "PATCH", {
        name: workspaceName,
      });
      await api(`${prefix}/branding/`, "PUT", {
        brand_name: brandName,
        primary_color: workspaceColor,
      });
      await refresh();
    }, "Workspace settings saved successfully!");
  };

  // Add team member
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
    }, `Invitation sent to ${inviteEmail}!`);
  };

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

        {/* Affiliate Link Button with yellow border / icon */}
        <button
          type="button"
          className="get-affiliate-link-btn"
          onClick={handleCopyAffiliate}
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
          TAB 1: PROFILE (Screenshot 1)
          ========================================================================= */}
      {activeTab === "profile" && (
        <div className="settings-tab-content stack-cards">
          {/* Section 1: Profile details card */}
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
                    <span>{fullName.charAt(0).toUpperCase() || "M"}</span>
                  </div>
                  <div className="avatar-user-name">{fullName}</div>
                  <label className="change-photo-link">
                    Change photo
                    <input type="file" accept="image/*" style={{ display: "none" }} />
                  </label>
                </div>

                {/* Right column: Form fields */}
                <div className="profile-fields-col">
                  <div className="form-group">
                    <label className="field-label">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your full name"
                      className="settings-text-input"
                    />
                  </div>

                  <div className="form-group">
                    <label className="field-label">Email Address</label>
                    <input
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
                          <div className="connected-acc-value">{emailAddress}</div>
                        </div>
                      </div>

                      <button type="button" className="connected-acc-disconnect-btn">
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

          {/* Section 2: Change password card */}
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
                  <label className="field-label">New password</label>
                  <div className="password-input-wrapper">
                    <input
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
                    >
                      {showNewPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  <span className="field-helper-note">Minimum 8 characters</span>
                </div>

                <div className="form-group">
                  <label className="field-label">Confirm Password</label>
                  <div className="password-input-wrapper">
                    <input
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
          TAB 2: META ACCOUNTS (Screenshot 2)
          ========================================================================= */}
      {activeTab === "meta" && (
        <div className="settings-tab-content stack-cards">
          {/* Card 1: Instagram Accounts */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Camera size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Instagram Accounts</h2>
                  <p className="card-subtitle">Manage your connected Instagram accounts.</p>
                </div>
              </div>

              <button
                type="button"
                className="add-black-btn"
                onClick={() => {
                  window.location.assign(`/api/meta/oauth/authorize/?action=connect&provider=instagram`);
                }}
              >
                <Plus size={15} /> Add Account
              </button>
            </div>

            {instagramConnected ? (
              <div className="connected-channel-card-row">
                <div className="channel-info-left">
                  <div className="channel-avatar-circle instagram">
                    <Instagram size={18} />
                  </div>
                  <div>
                    <div className="channel-name-title-row">
                      <span className="channel-handle">@censtd_nutech</span>
                      <span className="primary-gray-badge">Primary</span>
                    </div>
                    <div className="channel-meta-stats">
                      183 followers · Connected 9/2/2026
                    </div>
                    <div className="channel-synced-time">
                      <Clock size={12} /> Synced Oct 21, 06:50 PM
                    </div>
                  </div>
                </div>

                <div className="channel-actions-right">
                  <span className="status-active-green">
                    <Check size={14} /> Active
                  </span>
                  <button
                    type="button"
                    className="reconnect-text-btn"
                    onClick={() => {
                      window.location.assign(`/api/meta/oauth/authorize/?action=connect&provider=instagram`);
                    }}
                  >
                    <RotateCw size={13} /> Reconnect
                  </button>
                  <button
                    type="button"
                    className="disconnect-red-btn"
                    onClick={() => setInstagramConnected(false)}
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-channel-box">
                No Instagram accounts connected. Click &ldquo;+ Add Account&rdquo; to connect.
              </div>
            )}
          </div>

          {/* Card 2: Facebook Pages */}
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Facebook size={18} className="card-icon fb-blue-icon" />
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
                onClick={() => {
                  window.location.assign(`/api/meta/oauth/authorize/?action=connect&provider=meta`);
                }}
              >
                <Plus size={15} /> Add Facebook Page
              </button>
            </div>

            {facebookConnected ? (
              <div className="connected-channel-card-row">
                <div className="channel-info-left">
                  <div className="channel-avatar-circle facebook">
                    <Facebook size={18} />
                  </div>
                  <div>
                    <div className="channel-name-title-row">
                      <span className="channel-handle">SHAMA - Lightening The Path For Youth</span>
                      <span className="primary-blue-badge">Primary</span>
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
                    onClick={() => setFacebookConnected(false)}
                  >
                    Disconnect
                  </button>
                </div>
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
          TAB 3: TEAM (Screenshot 3)
          ========================================================================= */}
      {activeTab === "team" && (
        <div className="settings-tab-content">
          <div className="settings-card">
            <div className="settings-card-header">
              <div className="card-header-icon-title">
                <Users size={18} className="card-icon" />
                <div>
                  <h2 className="card-title">Team Members</h2>
                  <p className="card-subtitle">{workspaceName} workspace</p>
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
                    <span>{fullName.charAt(0).toUpperCase() || "M"}</span>
                  </div>
                  <div>
                    <div className="team-member-name">{fullName}</div>
                    <div className="team-member-email">{emailAddress}</div>
                  </div>
                </div>

                <span className="owner-black-badge">Owner</span>
              </div>
            </div>

            {/* Members List or Empty State */}
            {members.length > 0 ? (
              <div className="team-members-list" style={{ marginTop: 16 }}>
                {members.map((m) => (
                  <div key={m.id} className="team-member-row">
                    <div className="team-member-info-left">
                      <div className="team-avatar-circle">
                        <span>{m.name.charAt(0).toUpperCase()}</span>
                      </div>
                      <div>
                        <div className="team-member-name">{m.name}</div>
                        <div className="team-member-email">{m.email}</div>
                      </div>
                    </div>
                    <span className="primary-gray-badge">{m.role}</span>
                  </div>
                ))}
              </div>
            ) : (
              /* Empty state matching Screenshot 3 */
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
          TAB 4: SUBSCRIPTION (Screenshot 4)
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
                  onClick={() => window.open("https://billing.stripe.com/p/login/", "_blank")}
                >
                  <span className="portal-dollar-icon">$</span> Customer Portal
                </button>
                <button
                  type="button"
                  className="upgrade-plan-black-btn"
                  onClick={() => window.location.assign(`/w/${workspace.id}/payments`)}
                >
                  Upgrade Plan
                </button>
              </div>
            </div>

            {/* Dark Navy/Black Plan Banner Card */}
            <div className="subscription-plan-banner">
              <div className="plan-banner-top">
                <h3 className="plan-banner-title">Lifetime</h3>
                <span className="plan-banner-billed">Billed lifetime</span>
              </div>

              <div className="plan-stats-four-col">
                <div className="plan-stat-item">
                  <span className="stat-label">Automations</span>
                  <span className="stat-val">Unlimited</span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">Instagram Accounts</span>
                  <span className="stat-val">Unlimited</span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">DMs This Month</span>
                  <span className="stat-val">Unlimited</span>
                </div>
                <div className="plan-stat-item">
                  <span className="stat-label">AI Credits</span>
                  <span className="stat-val">$5.00</span>
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
                <span className="hint-value">$5.00</span>
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
                      onClick={() => setSelectedTopUp(amt)}
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
                    onClick={() => setAutoRechargeEnabled(!autoRechargeEnabled)}
                  >
                    <span className="toggle-switch-thumb" />
                  </button>
                </div>

                <div className="auto-recharge-inputs-row">
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="field-label">Trigger when balance drops below</label>
                    <div className="dollar-input-wrapper">
                      <span className="currency-symbol">$</span>
                      <input
                        type="text"
                        value={autoRechargeThreshold}
                        onChange={(e) => setAutoRechargeThreshold(e.target.value)}
                        className="dollar-text-input"
                      />
                    </div>
                  </div>

                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="field-label">Recharge amount</label>
                    <div className="custom-select-box">
                      <select
                        value={autoRechargeAmount}
                        onChange={(e) => setAutoRechargeAmount(e.target.value)}
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
                <div className="credits-rem-val">$5.00</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 5: WORKSPACES (Screenshot 5)
          ========================================================================= */}
      {activeTab === "workspaces" && (
        <div className="settings-tab-content workspaces-layout-grid">
          {/* Left Column: Workspaces List */}
          <div className="workspaces-left-column">
            <div className="workspaces-list-header">
              <div>
                <h3 className="ws-list-title">Workspaces</h3>
                <span className="ws-usage-count">1 of 1 used</span>
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
              {allWorkspaces.map((ws) => (
                <div key={ws.id} className="active-workspace-card-item">
                  <div className="ws-card-avatar" style={{ background: workspaceColor }}>
                    <span>{ws.name.charAt(0).toUpperCase()}</span>
                  </div>
                  <div className="ws-card-info">
                    <div className="ws-card-name-row">
                      <span className="ws-name-text">{ws.name}</span>
                      <span className="current-badge-pill">Current</span>
                    </div>
                    <div className="ws-card-role-meta">Owner · Default · 1 member</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Active Workspace Settings */}
          <div className="workspaces-right-column">
            <div className="ws-settings-header-banner">
              <div className="ws-banner-avatar" style={{ background: workspaceColor }}>
                <span>{workspaceName.charAt(0).toUpperCase()}</span>
              </div>
              <div>
                <span className="settings-for-label">Settings for</span>
                <h2 className="ws-banner-title">{workspaceName}</h2>
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
                onClick={() => setWorkspaceSubTab("accounts")}
              >
                Accounts
              </button>
              <button
                type="button"
                className={`ws-subtab-btn ${workspaceSubTab === "billing" ? "active" : ""}`}
                onClick={() => setWorkspaceSubTab("billing")}
              >
                Billing
              </button>
            </div>

            {/* BASICS */}
            <div className="ws-section-block">
              <div className="ws-block-eyebrow">BASICS</div>

              <div className="form-group">
                <label className="field-label">Workspace Name</label>
                <input
                  type="text"
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  className="settings-text-input"
                />
              </div>

              <div className="form-group" style={{ marginTop: 14 }}>
                <label className="field-label">Workspace Color</label>
                <div className="color-input-hex-row">
                  <div className="color-preview-box" style={{ background: workspaceColor }} />
                  <input
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
                  {workspaceName.charAt(0).toUpperCase()}
                </div>
                <div className="preview-copy-col">
                  <span className="preview-ws-name">{workspaceName}</span>
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
                    <Sparkles size={22} className="ghost-icon" />
                  </div>
                  <div>
                    <label className="upload-file-btn">
                      Upload
                      <input type="file" accept="image/*" style={{ display: "none" }} />
                    </label>
                    <span className="file-format-hint">PNG, JPG, GIF or WebP - max 5MB</span>
                  </div>
                </div>
              </div>

              <div className="form-group" style={{ marginTop: 14 }}>
                <label className="field-label">Brand name</label>
                <input
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
            <p className="modal-sub">Collaborate with colleagues on {workspaceName}.</p>

            <form onSubmit={handleInviteMember} style={{ marginTop: 16 }}>
              <div className="form-group">
                <label className="field-label">Email Address</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com"
                  className="settings-text-input"
                  required
                />
              </div>

              <div className="form-group" style={{ marginTop: 12 }}>
                <label className="field-label">Role</label>
                <div className="custom-select-box">
                  <select
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
