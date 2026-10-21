"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Sparkles,
  Zap,
} from "lucide-react";
import type { Integration } from "@/lib/api";

export interface IntegrationConfigMeta {
  id: string;
  name: string;
  description: string;
  providerKey?: string;
  iconBg: string;
  iconColor: string;
  logo: React.ReactNode;
}

interface IntegrationConfigureViewProps {
  app: IntegrationConfigMeta;
  existingIntegration?: Integration;
  onBack: () => void;
  onSave: (credentials: Record<string, string>, isTest: boolean) => Promise<void>;
  onConnect?: (credentials: Record<string, string>, isTest: boolean) => Promise<void>;
  busy?: boolean;
}

interface GuideStep {
  text: string;
  link?: { label: string; url: string };
  copyable?: string;
}

interface ConfigSchema {
  guideTitle?: string;
  guideSteps: GuideStep[];
  guideNotice?: string;
  fields: {
    key: string;
    label: string;
    placeholder: string;
    type?: "text" | "password" | "readonly";
    required?: boolean;
    helper?: string;
    defaultValue?: string;
    isRedirectUrl?: boolean;
  }[];
  docsUrl: string;
  docsLabel: string;
}

export function IntegrationConfigureView({
  app,
  existingIntegration,
  onBack,
  onSave,
  onConnect,
  busy = false,
}: IntegrationConfigureViewProps) {
  const [guideOpen, setGuideOpen] = useState(true);
  const [showPassword, setShowPassword] = useState<Record<string, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [testMode, setTestMode] = useState(existingIntegration?.is_test || false);

  const pk = (app.providerKey || app.id || "").toLowerCase();

  // Dynamic host redirect URL for this workspace
  const origin = typeof window !== "undefined" ? window.location.origin : "https://app.nemio.ai";
  const oauthRedirectUrl = `${origin}/oauth/callback/${pk.replace(/[^a-z0-9]/g, "_")}`;

  // Tailored configurations per integration
  const schema: ConfigSchema = getConfigSchema(app.name, pk, oauthRedirectUrl);

  // Form field state
  const [formData, setFormData] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    schema.fields.forEach((f) => {
      if (f.isRedirectUrl) {
        initial[f.key] = oauthRedirectUrl;
      } else {
        const stored = existingIntegration?.options?.[f.key];
        initial[f.key] = stored || f.defaultValue || "";
      }
    });
    return initial;
  });

  const handleCopy = (text: string, keyName: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(keyName);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const togglePasswordVisibility = (fieldKey: string) => {
    setShowPassword((prev) => ({ ...prev, [fieldKey]: !prev[fieldKey] }));
  };

  const handleFieldChange = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveClick = async () => {
    await onSave(formData, testMode);
  };

  const handleConnectClick = async () => {
    if (onConnect) {
      await onConnect(formData, testMode);
    } else {
      await onSave(formData, testMode);
    }
  };

  return (
    <div className="boosend-config-page">
      {/* Top Breadcrumb & Back Action */}
      <div className="boosend-config-nav-row">
        <div>
          <h1 className="boosend-integrations-title">Integrations</h1>
          <p className="boosend-integrations-sub">
            Connect external platforms for automation workflows
          </p>
        </div>
      </div>

      <div style={{ marginTop: "16px", marginBottom: "16px" }}>
        <button type="button" className="boosend-btn-back-int" onClick={onBack}>
          <ArrowLeft size={14} /> Back to integrations
        </button>
      </div>

      {/* Main Configuration Card (Matching User Screenshot) */}
      <div className="boosend-config-card">
        {/* Card Header Row: App Logo, Title, Subtitle, and Primary Actions */}
        <div className="boosend-config-card-header">
          <div className="boosend-config-app-info">
            <div
              className="boosend-config-logo"
              style={{ backgroundColor: app.iconBg, color: app.iconColor }}
            >
              {app.logo}
            </div>
            <div>
              <h2 className="boosend-config-app-name">{app.name}</h2>
              <p className="boosend-config-app-desc">{app.description}</p>
            </div>
          </div>

          <div className="boosend-config-actions-row">
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={handleSaveClick}
              style={{
                background: "#0f172a",
                color: "#ffffff",
                padding: "9px 18px",
                borderRadius: "8px",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
                border: "1px solid #0f172a",
              }}
            >
              {busy ? "Saving…" : "Save Configuration"}
            </button>
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={handleConnectClick}
              style={{
                background: "#0f172a",
                color: "#ffffff",
                padding: "9px 20px",
                borderRadius: "8px",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
                border: "1px solid #0f172a",
              }}
            >
              {busy ? "Connecting…" : "Connect"}
            </button>
          </div>
        </div>

        {/* Collapsible Setup Guide (Blue Box Accordion) */}
        <div className="boosend-setup-guide-box">
          <button
            type="button"
            className="setup-guide-toggle-btn"
            onClick={() => setGuideOpen(!guideOpen)}
          >
            <span>{guideOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
            <strong>Setup Guide</strong>
          </button>

          {guideOpen && (
            <div className="setup-guide-content">
              <ol className="setup-guide-steps-list">
                {schema.guideSteps.map((step, idx) => (
                  <li key={idx} className="setup-step-item">
                    <span>
                      {step.text}{" "}
                      {step.link && (
                        <a
                          href={step.link.url}
                          target="_blank"
                          rel="noreferrer"
                          className="guide-ext-link"
                        >
                          {step.link.label} <ExternalLink size={12} style={{ display: "inline" }} />
                        </a>
                      )}
                      {step.copyable && (
                        <span className="guide-copy-chip">
                          <code>{step.copyable}</code>
                          <button
                            type="button"
                            className="guide-copy-btn"
                            onClick={() => handleCopy(step.copyable!, `step-${idx}`)}
                            title="Copy to clipboard"
                          >
                            {copiedKey === `step-${idx}` ? (
                              <Check size={12} color="#10b981" />
                            ) : (
                              <Copy size={12} />
                            )}
                          </button>
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>

              {schema.guideNotice && (
                <div className="setup-guide-notice">
                  <Zap size={14} color="#f59e0b" style={{ flexShrink: 0 }} />
                  <span>{schema.guideNotice}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Configuration Form Inputs */}
        <div className="boosend-config-form">
          {schema.fields.map((field) => {
            const isPassword = field.type === "password";
            const visible = showPassword[field.key] || false;
            const inputType = isPassword ? (visible ? "text" : "password") : "text";

            return (
              <div key={field.key} className="config-form-field-group">
                <label className="config-field-label">
                  {field.label} {field.required && <span className="req-star">*</span>}
                </label>

                <div className="config-input-wrapper">
                  <input
                    type={inputType}
                    value={formData[field.key] || ""}
                    readOnly={field.isRedirectUrl}
                    placeholder={field.placeholder}
                    onChange={(e) => handleFieldChange(field.key, e.target.value)}
                    className={`config-input-element ${field.isRedirectUrl ? "readonly-input" : ""}`}
                  />

                  {/* Password Show/Hide Toggle */}
                  {isPassword && (
                    <button
                      type="button"
                      className="input-inline-action-btn"
                      onClick={() => togglePasswordVisibility(field.key)}
                      title={visible ? "Hide secret" : "Show secret"}
                    >
                      {visible ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  )}

                  {/* Copy Button for Redirect URL */}
                  {field.isRedirectUrl && (
                    <button
                      type="button"
                      className="input-inline-action-btn"
                      onClick={() => handleCopy(formData[field.key] || oauthRedirectUrl, field.key)}
                      title="Copy URL"
                    >
                      {copiedKey === field.key ? (
                        <Check size={15} color="#10b981" />
                      ) : (
                        <Copy size={15} />
                      )}
                    </button>
                  )}
                </div>

                {field.helper && <p className="config-field-helper">{field.helper}</p>}
              </div>
            );
          })}

          {/* Test Simulation Mode Switch */}
          <div className="config-test-mode-row">
            <label className="test-mode-label">
              <input
                type="checkbox"
                checked={testMode}
                onChange={(e) => setTestMode(e.target.checked)}
                className="test-mode-checkbox"
              />
              <span>Use local test simulation (no live external API calls)</span>
            </label>
          </div>
        </div>

        {/* Bottom Documentation Link */}
        <div className="boosend-config-footer">
          <a
            href={schema.docsUrl}
            target="_blank"
            rel="noreferrer"
            className="config-docs-link"
          >
            <ExternalLink size={13} /> {schema.docsLabel}
          </a>
        </div>
      </div>
    </div>
  );
}

/**
 * Returns customized setup guides, fields, and API documentation per platform
 */
function getConfigSchema(appName: string, pk: string, redirectUrl: string): ConfigSchema {
  // 1. Google Sheets / Google Workspace
  if (pk.includes("sheet") || appName.toLowerCase().includes("sheet")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Go to",
          link: {
            label: "Google Cloud Console ➔ Credentials",
            url: "https://console.cloud.google.com/apis/credentials",
          },
        },
        { text: "2. Create \"OAuth client ID\" ➔ Select Web Application" },
        { text: "3. Add Authorized Redirect URI:", copyable: redirectUrl },
        { text: "4. Copy the Client ID and Client Secret and paste them below" },
        {
          text: "5. Publish your app so the connection stays active permanently. If you keep it in Testing instead, add your email as a Test user, but the connection will stop working after 7 days and you'll need to reconnect. Do either in",
          link: {
            label: "Google Cloud Console ➔ Audience",
            url: "https://console.cloud.google.com/apis/credentials/consent",
          },
        },
      ],
      guideNotice:
        "Make sure to enable these APIs in your project: Google Sheets API, Google Calendar API, Gmail API",
      fields: [
        {
          key: "client_id",
          label: "Client ID",
          placeholder: "e.g. 123456789-abcdef.apps.googleusercontent.com",
          required: true,
          defaultValue: "mtahirmalik3600921@gmail.com",
        },
        {
          key: "client_secret",
          label: "Client Secret",
          placeholder: "••••••••",
          type: "password",
          required: true,
          defaultValue: "GOCSPX-dummysecret12345",
          helper: "Stored encrypted. Used only to exchange/refresh tokens.",
        },
        {
          key: "redirect_url",
          label: "OAuth Redirect URL",
          placeholder: redirectUrl,
          isRedirectUrl: true,
          helper: "Add this URL to your app's allowed redirect URIs.",
        },
      ],
      docsUrl: "https://developers.google.com/sheets/api/guides/concepts",
      docsLabel: "View Google Sheets API Documentation",
    };
  }

  // 2. Google Calendar
  if (pk.includes("calendar") || appName.toLowerCase().includes("calendar")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Open",
          link: {
            label: "Google Cloud Console ➔ Credentials",
            url: "https://console.cloud.google.com/apis/credentials",
          },
        },
        { text: "2. Create \"OAuth client ID\" with type Web Application" },
        { text: "3. Add Authorized Redirect URI:", copyable: redirectUrl },
        { text: "4. Paste your Client ID and Secret below and click Connect" },
      ],
      guideNotice: "Make sure Google Calendar API is enabled in your Google Cloud Project.",
      fields: [
        {
          key: "client_id",
          label: "Client ID",
          placeholder: "your-client-id.apps.googleusercontent.com",
          required: true,
        },
        {
          key: "client_secret",
          label: "Client Secret",
          placeholder: "••••••••",
          type: "password",
          required: true,
          helper: "Stored encrypted. Used only to exchange/refresh tokens.",
        },
        {
          key: "redirect_url",
          label: "OAuth Redirect URL",
          placeholder: redirectUrl,
          isRedirectUrl: true,
          helper: "Add this URL to your app's allowed redirect URIs.",
        },
      ],
      docsUrl: "https://developers.google.com/calendar/api/guides/overview",
      docsLabel: "View Google Calendar API Documentation",
    };
  }

  // 3. Gmail
  if (pk.includes("gmail") || appName.toLowerCase().includes("gmail")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Go to",
          link: {
            label: "Google Cloud Console ➔ Credentials",
            url: "https://console.cloud.google.com/apis/credentials",
          },
        },
        { text: "2. Register OAuth Client ID for Web Application" },
        { text: "3. Add Authorized Redirect URI:", copyable: redirectUrl },
        { text: "4. Copy Client ID and Secret" },
      ],
      guideNotice: "Make sure Gmail API is enabled in your Google Cloud project.",
      fields: [
        {
          key: "client_id",
          label: "Client ID",
          placeholder: "your-client-id.apps.googleusercontent.com",
          required: true,
        },
        {
          key: "client_secret",
          label: "Client Secret",
          placeholder: "••••••••",
          type: "password",
          required: true,
          helper: "Stored encrypted. Used only to send automated emails.",
        },
        {
          key: "redirect_url",
          label: "OAuth Redirect URL",
          placeholder: redirectUrl,
          isRedirectUrl: true,
          helper: "Add this URL to your app's allowed redirect URIs.",
        },
      ],
      docsUrl: "https://developers.google.com/gmail/api/guides",
      docsLabel: "View Gmail API Documentation",
    };
  }

  // 4. N8N
  if (pk.includes("n8n") || appName.toLowerCase().includes("n8n")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Open your n8n workspace ➔ Go to Settings ➔",
          link: { label: "n8n API", url: "https://docs.n8n.io/api/" },
        },
        { text: "2. Click \"Create an API Key\" and grant workflow trigger permissions" },
        { text: "3. Enter your n8n public instance URL and paste the API key below" },
        { text: "4. (Optional) Provide a default Webhook path to trigger workflows directly from chat" },
      ],
      guideNotice: "Nemio connects directly to your self-hosted or cloud n8n instance via REST API.",
      fields: [
        {
          key: "base_url",
          label: "n8n Instance URL",
          placeholder: "https://n8n.yourcompany.com",
          required: true,
          defaultValue: "https://n8n.instance.internal",
        },
        {
          key: "api_key",
          label: "API Key / Secret Token",
          placeholder: "••••••••",
          type: "password",
          required: true,
          helper: "Used to trigger workflows and query execution results.",
        },
        {
          key: "webhook_path",
          label: "Default Webhook Path (optional)",
          placeholder: "/webhook/lead-captured",
          helper: "Endpoint invoked when conversation triggers fire.",
        },
      ],
      docsUrl: "https://docs.n8n.io/api/",
      docsLabel: "View N8N Documentation",
    };
  }

  // 5. Make.com
  if (pk.includes("make") || appName.toLowerCase().includes("make")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Log in to Make.com ➔ Click Profile ➔",
          link: { label: "API Tokens", url: "https://www.make.com/en/help/tools/make-api" },
        },
        { text: "2. Click \"Add token\" and select Scenarios & Webhooks scopes" },
        { text: "3. Copy your Webhook URL from your Make scenario's Custom Webhook module" },
      ],
      guideNotice: "Incoming conversation events are formatted as clean JSON payloads for Make scenarios.",
      fields: [
        {
          key: "webhook_url",
          label: "Webhook URL",
          placeholder: "https://hook.eu1.make.com/abcdef123456",
          required: true,
        },
        {
          key: "api_key",
          label: "API Token (optional)",
          placeholder: "••••••••",
          type: "password",
          helper: "Required if you want Nemio to inspect or activate scenarios programmatically.",
        },
      ],
      docsUrl: "https://www.make.com/en/api-documentation",
      docsLabel: "View Make.com Documentation",
    };
  }

  // 6. Slack
  if (pk.includes("slack") || appName.toLowerCase().includes("slack")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Open",
          link: { label: "Slack API: Your Apps", url: "https://api.slack.com/apps" },
        },
        { text: "2. Create a new app \"From scratch\" and install it to your workspace" },
        { text: "3. Under \"OAuth & Permissions\", copy the \"Bot User OAuth Token\" (starts with xoxb-)" },
        { text: "4. Ensure the bot is invited to your target channel (e.g. /invite @Nemio in #leads)" },
      ],
      guideNotice: "Bot token requires `chat:write` and `channels:read` scopes.",
      fields: [
        {
          key: "bot_token",
          label: "Bot User OAuth Token (xoxb-...)",
          placeholder: "xoxb-123456789-abcdef",
          type: "password",
          required: true,
          helper: "Stored securely. Used to post lead alerts and message transcripts.",
        },
        {
          key: "default_channel",
          label: "Default Channel Name",
          placeholder: "#leads",
          required: true,
          defaultValue: "#leads",
          helper: "Channel where automated notifications will be posted.",
        },
        {
          key: "webhook_url",
          label: "Incoming Webhook URL (optional)",
          placeholder: "https://hooks.slack.com/services/...",
        },
      ],
      docsUrl: "https://api.slack.com/messaging/sending",
      docsLabel: "View Slack API Documentation",
    };
  }

  // 7. HubSpot
  if (pk.includes("hubspot") || appName.toLowerCase().includes("hubspot")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. In HubSpot, click the Settings gear ➔",
          link: { label: "Integrations ➔ Private Apps", url: "https://app.hubspot.com/" },
        },
        { text: "2. Click \"Create a private app\" and name it \"Nemio AI\"" },
        { text: "3. Under Scopes, select `crm.objects.contacts.write` and `crm.objects.contacts.read`" },
        { text: "4. Click \"Create app\" and copy the access token starting with `pat-`" },
      ],
      guideNotice: "Automatically creates contacts and updates deal pipelines from conversations.",
      fields: [
        {
          key: "api_key",
          label: "Private App Access Token (pat-...)",
          placeholder: "pat-na1-abcdef-123456",
          type: "password",
          required: true,
          helper: "Access token with contact creation permissions.",
        },
        {
          key: "portal_id",
          label: "HubSpot Portal / Hub ID (optional)",
          placeholder: "e.g. 12345678",
        },
      ],
      docsUrl: "https://developers.hubspot.com/docs/api/crm/contacts",
      docsLabel: "View HubSpot API Documentation",
    };
  }

  // 8. ElevenLabs
  if (pk.includes("eleven") || appName.toLowerCase().includes("eleven")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Log in to ElevenLabs ➔ Click your Profile in bottom left ➔",
          link: { label: "API Keys", url: "https://elevenlabs.io/app/settings/api-keys" },
        },
        { text: "2. Click \"Create API Key\" and copy the generated key" },
        { text: "3. (Optional) Find your desired Voice ID in VoiceLab to use as default" },
      ],
      guideNotice: "Generates instant voice notes sent directly to leads in Instagram and WhatsApp DMs.",
      fields: [
        {
          key: "api_key",
          label: "ElevenLabs API Key",
          placeholder: "sk_1234567890abcdef...",
          type: "password",
          required: true,
        },
        {
          key: "voice_id",
          label: "Default Voice ID (optional)",
          placeholder: "21m00Tcm4TlvDq8ikWAM (Rachel)",
          helper: "ID of the cloned or pre-made voice to speak responses.",
        },
      ],
      docsUrl: "https://elevenlabs.io/docs/api-reference",
      docsLabel: "View ElevenLabs Documentation",
    };
  }

  // 9. HeyGen
  if (pk.includes("heygen") || appName.toLowerCase().includes("heygen")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Go to HeyGen ➔ Space Settings ➔",
          link: { label: "API Keys", url: "https://app.heygen.com/settings?nav=API" },
        },
        { text: "2. Click \"Generate API Key\" and copy your token" },
        { text: "3. Copy your preferred Avatar ID from the Avatar library" },
      ],
      guideNotice: "Renders personalized avatar videos with lead names for high-converting welcome messages.",
      fields: [
        {
          key: "api_key",
          label: "HeyGen API Key",
          placeholder: "your-heygen-api-key",
          type: "password",
          required: true,
        },
        {
          key: "avatar_id",
          label: "Default Avatar ID (optional)",
          placeholder: "e.g. Wayne_20240101",
        },
      ],
      docsUrl: "https://docs.heygen.com/",
      docsLabel: "View HeyGen Documentation",
    };
  }

  // 10. Calendly
  if (pk.includes("calendly") || appName.toLowerCase().includes("calendly")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. Go to Calendly ➔ Integrations ➔",
          link: { label: "API & Webhooks", url: "https://calendly.com/integrations/api_webhooks" },
        },
        { text: "2. Click \"Generate New Token\" under Personal Access Tokens" },
        { text: "3. Paste your token and your scheduling link below" },
      ],
      guideNotice: "Lets AI agents book qualified leads into available calendar slots automatically.",
      fields: [
        {
          key: "api_key",
          label: "Personal Access Token",
          placeholder: "eyJhbGciOi...",
          type: "password",
          required: true,
        },
        {
          key: "scheduling_url",
          label: "Calendly Event Link",
          placeholder: "https://calendly.com/your-team/30min",
          required: true,
        },
      ],
      docsUrl: "https://developer.calendly.com/",
      docsLabel: "View Calendly API Documentation",
    };
  }

  // 11. Stripe
  if (pk.includes("stripe") || appName.toLowerCase().includes("stripe")) {
    return {
      guideTitle: "Setup Guide",
      guideSteps: [
        {
          text: "1. In Stripe Dashboard ➔ Developers ➔",
          link: { label: "API Keys", url: "https://dashboard.stripe.com/apikeys" },
        },
        { text: "2. Copy your Secret Key (starts with sk_live_ or sk_test_)" },
        {
          text: "3. In Webhooks, add endpoint:",
          copyable: `${origin}/webhooks/stripe/`,
        },
      ],
      guideNotice: "Enables instant payment link generation and checkout tracking in chats.",
      fields: [
        {
          key: "api_key",
          label: "Stripe Secret Key (sk_...)",
          placeholder: "sk_live_...",
          type: "password",
          required: true,
        },
        {
          key: "webhook_secret",
          label: "Webhook Signing Secret (whsec_...) (optional)",
          placeholder: "whsec_...",
          type: "password",
        },
      ],
      docsUrl: "https://stripe.com/docs/api",
      docsLabel: "View Stripe API Documentation",
    };
  }

  // Default Fallback (Webhook / Custom Tool)
  return {
    guideTitle: "Setup Guide",
    guideSteps: [
      { text: `1. Generate an API Key or Webhook Token in your ${appName} dashboard` },
      { text: "2. Paste the credentials or endpoint URL in the fields below" },
      { text: "3. Click \"Save Configuration\" to store the credentials securely" },
    ],
    fields: [
      {
        key: "api_key",
        label: "API Key or Secret Token",
        placeholder: "Enter your API token",
        type: "password",
        required: true,
        helper: "Stored encrypted with workspace isolation.",
      },
      {
        key: "account_id",
        label: "Account / Workspace ID (optional)",
        placeholder: "e.g. workspace_123",
      },
    ],
    docsUrl: "https://docs.nemio.ai/integrations",
    docsLabel: `View ${appName} Documentation`,
  };
}
