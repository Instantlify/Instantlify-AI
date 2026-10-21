"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  ExternalLink,
  HelpCircle,
  KeyRound,
  LayoutGrid,
  Mail,
  MessageSquare,
  Mic,
  PhoneCall,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Volume2,
  Webhook,
  Workflow,
  X,
} from "lucide-react";
import {
  api,
  when,
  WEBHOOK_EVENTS,
  type APIKey,
  type Connection,
  type Delivery,
  type Integration,
  type Page,
  type WebhookDelivery,
  type WebhookSubscription,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { CopyField, Empty, ErrorNotice, Modal, Pill, statusTone, SuccessNotice, Table, useFeedback } from "@/components/ui";
import { IntegrationAnimatedExplainer } from "@/components/integration-animated-explainer";

type Category =
  | "All"
  | "CRM & Contacts"
  | "Email"
  | "Email Marketing"
  | "Calendar & Scheduling"
  | "Voice & AI Media"
  | "Payments"
  | "Knowledge Base"
  | "Data & Records"
  | "Workflow Tools"
  | "Team Chat";

const CATEGORIES: Category[] = [
  "All",
  "CRM & Contacts",
  "Email",
  "Email Marketing",
  "Calendar & Scheduling",
  "Voice & AI Media",
  "Payments",
  "Knowledge Base",
  "Data & Records",
  "Workflow Tools",
  "Team Chat",
];

interface AppItem {
  id: string;
  name: string;
  category: Category[];
  description: string;
  status?: "available" | "coming_soon" | "connected";
  providerKey?: string;
  oauthSupported?: boolean;
  oauthAction?: "meta" | "google_calendar" | "slack" | "linkedin";
  iconBg: string;
  iconColor: string;
  logo: ReactNode;
  explainer?: {
    stepType: string;
    description: string;
    trigger: string;
    action: string;
  };
}

export default function IntegrationsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const owner = workspace.role === "owner";

  const [activeTab, setActiveTab] = useState<"gallery" | "developer">("gallery");
  const [selectedCategory, setSelectedCategory] = useState<Category>("All");
  const [explainingApp, setExplainingApp] = useState<AppItem | null>(null);

  // Data & API states
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [subscriptions, setSubscriptions] = useState<WebhookSubscription[]>([]);
  const [hookLog, setHookLog] = useState<WebhookDelivery[]>([]);
  const [configuring, setConfiguring] = useState<string>("");
  const [testMode, setTestMode] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newSecret, setNewSecret] = useState("");
  const [newToken, setNewToken] = useState("");
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const channels = await api<Page<Connection>>(
          `${prefix}/connections/`,
          "GET",
          undefined,
          signal,
        );
        setConnections(channels.results || []);

        if (manager) {
          const [items, keyPage, subs, log] = await Promise.all([
            api<Page<Integration>>(
              `${prefix}/integrations/`,
              "GET",
              undefined,
              signal,
            ).catch(() => ({ results: [] as Integration[] })),
            api<Page<APIKey>>(`${prefix}/api-keys/`, "GET", undefined, signal).catch(() => ({
              results: [] as APIKey[],
            })),
            api<Page<WebhookSubscription>>(
              `${prefix}/webhooks/`,
              "GET",
              undefined,
              signal,
            ).catch(() => ({ results: [] as WebhookSubscription[] })),
            api<WebhookDelivery[]>(
              `${prefix}/webhook-deliveries/`,
              "GET",
              undefined,
              signal,
            ).catch(() => [] as WebhookDelivery[]),
          ]);
          setIntegrations(items.results || []);
          setKeys(keyPage.results || []);
          setSubscriptions(subs.results || []);
          setHookLog(log || []);
        }
      } catch (err) {
        if (!signal?.aborted) {
          console.error("Failed to load integrations", err);
        }
      }
    },
    [prefix, manager],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(String(err.message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function connectOAuth(provider: string) {
    await feedback.run(async () => {
      const started = await api<{ authorization_url: string }>(
        `${prefix}/integrations/${provider}/oauth/`,
        "POST",
        {},
      );
      window.location.assign(started.authorization_url);
    });
  }

  async function connectMeta() {
    await feedback.run(async () => {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    });
  }

  async function disconnectIntegration(providerKey: string) {
    const current = integrations.find((i) => i.provider === providerKey);
    if (!current) return;
    if (!window.confirm("Disconnect integration? Stored credentials will be removed.")) return;
    await feedback.run(async () => {
      await api(`${prefix}/integrations/${current.id}/`, "DELETE");
      setIntegrations((list) => list.filter((item) => item.id !== current.id));
    }, "Integration disconnected.");
  }

  async function saveIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const credentials: Record<string, string> = {};
    for (const [k, v] of data.entries()) {
      if (k.startsWith("cred_") && v) {
        credentials[k.replace("cred_", "")] = String(v);
      }
    }
    const isTest = data.get("is_test") === "on";
    await feedback.run(async () => {
      const saved = await api<Integration>(`${prefix}/integrations/`, "POST", {
        provider: configuring,
        credentials,
        options: {},
        enabled: true,
        is_test: isTest,
      });
      setIntegrations((list) => [
        ...list.filter((item) => item.provider !== saved.provider),
        saved,
      ]);
      setConfiguring("");
    }, "Integration saved.");
  }

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const scopes = ["read", "write"].filter((s) => data.get(s) === "on");
    await feedback.run(async () => {
      const created = await api<APIKey>(`${prefix}/api-keys/`, "POST", {
        name: data.get("name"),
        scopes,
      });
      setKeys((list) => [created, ...list]);
      setNewKey(created.key || "");
      (event.target as HTMLFormElement).reset();
    }, "API key created. Copy it now; it will not be shown again.");
  }

  async function revokeKey(key: APIKey) {
    if (!window.confirm(`Revoke ${key.name}?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/api-keys/${key.id}/`, "DELETE");
      setKeys((list) => list.filter((i) => i.id !== key.id));
    }, "API key revoked.");
  }

  async function createSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const events = WEBHOOK_EVENTS.filter((name) => data.get(name) === "on");
    await feedback.run(async () => {
      const created = await api<WebhookSubscription>(`${prefix}/webhooks/`, "POST", {
        url: data.get("url"),
        events,
      });
      setSubscriptions((list) => [created, ...list]);
      setNewSecret(created.secret || "");
      setNewToken(created.token || "");
      (event.target as HTMLFormElement).reset();
    }, "Webhook subscribed.");
  }

  async function removeSubscription(subscription: WebhookSubscription) {
    if (!window.confirm("Remove this webhook subscription?")) return;
    await feedback.run(async () => {
      await api(`${prefix}/webhooks/${subscription.id}/`, "DELETE");
      setSubscriptions((list) => list.filter((item) => item.id !== subscription.id));
    }, "Webhook removed.");
  }

  // Gallery apps catalog (matching BooSend Screenshots 5, 6, 7)
  const APPS: AppItem[] = [
    {
      id: "google-sheets",
      name: "Google Sheets",
      category: ["Data & Records"],
      description: "Connect Google Sheets to read and write data in your automations",
      providerKey: "google_sheets",
      iconBg: "#e6f4ea",
      iconColor: "#137333",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14H6v-2h6v2zm0-4H6v-2h6v2zm0-4H6V7h6v2zm6 8h-4v-2h4v2zm0-4h-4v-2h4v2zm0-4h-4V7h4v2z" />
        </svg>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Add a Google Sheets step to your automation to log conversation events, append new lead rows, or pull existing customer records directly inside the workflow.",
        trigger: "Message Received",
        action: "Append Row to Google Sheet",
      },
    },
    {
      id: "google-calendar",
      name: "Google Calendar",
      category: ["Calendar & Scheduling"],
      description: "Connect Google Calendar to schedule and manage events",
      providerKey: "google_calendar",
      oauthSupported: true,
      oauthAction: "google_calendar",
      iconBg: "#e8f0fe",
      iconColor: "#1a73e8",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zm-7 5h5v5h-5z" />
        </svg>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Add a Google Calendar step to your automations to let customers check live availability and book discovery calls directly in chat.",
        trigger: "Customer requests a booking",
        action: "Reserve Google Calendar Slot",
      },
    },
    {
      id: "gmail",
      name: "Gmail",
      category: ["Email"],
      description: "Connect Gmail to send emails directly from your automations",
      providerKey: "gmail",
      iconBg: "#fce8e6",
      iconColor: "#ea4335",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
        </svg>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Send transactional emails, order confirmations, or booking receipts directly from your connected Gmail address during conversations.",
        trigger: "Lead shares contact info",
        action: "Send Email via Gmail",
      },
    },
    {
      id: "outlook",
      name: "Outlook",
      category: ["Email"],
      description: "Connect Outlook to send emails directly from your automations",
      providerKey: "outlook",
      iconBg: "#e1f0fa",
      iconColor: "#0078d4",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M1 5h14v14H1V5zm16 2.5v9l6 3.5V4l-6 3.5z" />
        </svg>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Connect Microsoft Outlook to trigger follow-up emails, sales collateral, and meeting invitations from your workflows.",
        trigger: "Conversation marked hot",
        action: "Send Outlook Email",
      },
    },
    {
      id: "gohighlevel",
      name: "GoHighLevel",
      category: ["CRM & Contacts"],
      description:
        "Connect your GoHighLevel Account so your leads can be automatically synced from Instagram",
      providerKey: "gohighlevel",
      iconBg: "#eff6ff",
      iconColor: "#2563eb",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "16px", color: "#2563eb", letterSpacing: "-1px" }}>
          GHL
        </div>
      ),
      explainer: {
        stepType: "CRM & Contacts step",
        description:
          "Add a GoHighLevel step to sync contacts, apply tags, and trigger GHL nurture pipelines automatically from Instagram comments and DMs.",
        trigger: "Lead captures form or phone",
        action: "Sync Contact to GoHighLevel",
      },
    },
    {
      id: "eleven-labs",
      name: "Eleven Labs",
      category: ["Voice & AI Media"],
      description: "Connect Eleven Labs for AI voice synthesis in automations",
      providerKey: "elevenlabs",
      iconBg: "#f8fafc",
      iconColor: "#0f172a",
      logo: (
        <div style={{ display: "flex", gap: "2px", alignItems: "center" }}>
          <div style={{ width: "4px", height: "16px", background: "#0f172a", borderRadius: "1px" }} />
          <div style={{ width: "4px", height: "16px", background: "#0f172a", borderRadius: "1px" }} />
        </div>
      ),
      explainer: {
        stepType: "Voice synthesis step",
        description:
          "Converts text responses into ultra-realistic AI voice notes and delivers them natively as voice messages in Instagram DMs and WhatsApp.",
        trigger: "Voice Note requested in DM",
        action: "Synthesize ElevenLabs Audio",
      },
    },
    {
      id: "inworld-ai",
      name: "Inworld AI",
      category: ["Voice & AI Media"],
      description: "Connect Inworld AI for advanced text-to-speech synthesis",
      providerKey: "inworld",
      iconBg: "#f1f5f9",
      iconColor: "#0f172a",
      logo: (
        <div style={{ width: "16px", height: "16px", borderRadius: "50%", border: "3px solid #0f172a" }} />
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Connect Inworld AI character engines to empower real-time voice agents and contextual character interactions inside social channels.",
        trigger: "Inbound voice interaction",
        action: "Run Inworld AI Voice Agent",
      },
    },
    {
      id: "minimax",
      name: "Minimax",
      category: ["Voice & AI Media"],
      description: "Connect Minimax for AI voice synthesis in automations",
      providerKey: "minimax",
      iconBg: "#fff1f2",
      iconColor: "#e11d48",
      logo: <Volume2 size={20} color="#e11d48" />,
      explainer: {
        stepType: "Voice synthesis step",
        description:
          "Generate high-fidelity conversational audio using Minimax voice synthesis models for automated audio delivery.",
        trigger: "Workflow audio node activated",
        action: "Generate Minimax Voice Clip",
      },
    },
    {
      id: "heygen",
      name: "HeyGen",
      category: ["Voice & AI Media"],
      description:
        "Connect HeyGen to generate avatar videos inside your Instagram automations.",
      providerKey: "heygen",
      iconBg: "#f5f3ff",
      iconColor: "#7c3aed",
      logo: <Play size={20} color="#7c3aed" />,
      explainer: {
        stepType: "AI Video generator step",
        description:
          "Add a HeyGen step to generate dynamic personalized video responses featuring an AI avatar speaking directly to the user.",
        trigger: "Lead qualifies as VIP",
        action: "Render Personalized HeyGen Video",
      },
    },
    {
      id: "jotform",
      name: "JotForm",
      category: ["Workflow Tools"],
      description: "Connect JotForm to let AI collect form responses during conversations",
      providerKey: "jotform",
      iconBg: "#fff7ed",
      iconColor: "#ea580c",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "14px", color: "#ea580c" }}>JF</div>
      ),
      explainer: {
        stepType: "Workflow tool step",
        description:
          "Stream JotForm submissions straight into your conversation context and trigger automated follow-ups immediately upon form submission.",
        trigger: "JotForm Submitted",
        action: "Trigger Onboarding Workflow",
      },
    },
    {
      id: "n8n",
      name: "N8N",
      category: ["Workflow Tools"],
      description: "Connect N8N workflows to extend your automations with custom logic",
      providerKey: "n8n",
      iconBg: "#fdf2f8",
      iconColor: "#db2777",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "13px", color: "#db2777", letterSpacing: "-0.5px" }}>
          n8n
        </div>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Add an N8N step to your automation to trigger one of your n8n workflows from a conversation. Nemio sends the conversation data over, your workflow runs its custom logic, and the result comes back into the chat.",
        trigger: "Message Received (any message)",
        action: "Run Workflow: N8N",
      },
    },
    {
      id: "make",
      name: "Make.com",
      category: ["Workflow Tools"],
      description:
        "Connect Make.com scenarios to trigger external automations from your Instagram conversations.",
      providerKey: "make",
      iconBg: "#f5f3ff",
      iconColor: "#9333ea",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "15px", color: "#9333ea" }}>///</div>
      ),
      explainer: {
        stepType: "Automation builder step",
        description:
          "Trigger any Make.com scenario with chat variables, payload objects, and lead parameters. Return processed outputs back to the live customer thread.",
        trigger: "Checkout initiated",
        action: "Execute Make.com Scenario",
      },
    },
    {
      id: "slack",
      name: "Slack",
      category: ["Team Chat"],
      description: "Connect Slack workspaces to send notifications from your automations",
      providerKey: "slack",
      oauthSupported: true,
      oauthAction: "slack",
      iconBg: "#fdf4ff",
      iconColor: "#a21caf",
      logo: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 15a2 2 0 1 1-2-2h2v2zm1 0a2 2 0 1 1 2 2v-2H7zm0-6a2 2 0 1 1-2-2 2 2 0 0 1 2 2v2zm6 0a2 2 0 1 1 2 2h-2V9zm-1 0a2 2 0 1 1-2-2v2h2zm0 6a2 2 0 1 1 2-2v2h-2z" />
        </svg>
      ),
      explainer: {
        stepType: "Team alert step",
        description:
          "Broadcast hot lead alerts, handoff requests, and payment notifications to team channels in Slack with 1-click links to jump into the chat.",
        trigger: "Lead marked 'hot' or 'needs_human'",
        action: "Post Alert to Slack #sales",
      },
    },
    {
      id: "discord",
      name: "Discord",
      category: ["Team Chat"],
      description: "Connect Discord servers to send notifications from your automations",
      providerKey: "discord",
      iconBg: "#eef2ff",
      iconColor: "#4f46e5",
      logo: <MessageSquare size={20} color="#4f46e5" />,
      explainer: {
        stepType: "Team alert step",
        description:
          "Push real-time community alerts, purchase notifications, and lead pings into your Discord server channels via webhooks.",
        trigger: "New member signup",
        action: "Post Notification to Discord",
      },
    },
    {
      id: "shopify",
      name: "Shopify",
      category: ["Payments", "CRM & Contacts"],
      description: "Connect your Shopify store for product discovery in AI agents.",
      providerKey: "shopify",
      iconBg: "#f0fdf4",
      iconColor: "#16a34a",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "14px", color: "#16a34a" }}>$</div>
      ),
      explainer: {
        stepType: "Commerce & Store step",
        description:
          "Allow AI agents to query product inventory, prices, variants, and generate pre-filled checkout carts directly in conversation threads.",
        trigger: "Customer asks about a product",
        action: "Search Shopify Catalog & Cart",
      },
    },
    {
      id: "notavo",
      name: "Notavo",
      category: ["Knowledge Base"],
      description: "Connect your Notavo knowledge bases to power AI automations in Nemio.",
      providerKey: "notavo",
      iconBg: "#faf5ff",
      iconColor: "#6b21a8",
      logo: <Database size={20} color="#6b21a8" />,
      explainer: {
        stepType: "Knowledge Base step",
        description:
          "Sync knowledge bases, product documentation, FAQs, and company policies into Nemio AI so the agent answers with verified facts.",
        trigger: "Customer asks technical question",
        action: "Retrieve Context from Notavo",
      },
    },
    {
      id: "zorromail",
      name: "ZorroMail",
      category: ["Email"],
      description:
        "Connect your ZorroMail Transactional Email account to send emails directly from your automations",
      providerKey: "zorromail",
      iconBg: "#f8fafc",
      iconColor: "#0f172a",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "14px", color: "#0f172a" }}>Z</div>
      ),
      explainer: {
        stepType: "Transactional email step",
        description:
          "Send instantaneous transactional email confirmations, download links, and alerts via high-deliverability ZorroMail SMTP.",
        trigger: "Lead completes questionnaire",
        action: "Send ZorroMail Transactional Email",
      },
    },
    {
      id: "klaviyo",
      name: "Klaviyo",
      category: ["Email Marketing"],
      description: "Connect your Klaviyo account to automatically sync your contacts to your list",
      providerKey: "klaviyo",
      iconBg: "#f0fdf4",
      iconColor: "#15803d",
      logo: <Mail size={20} color="#15803d" />,
      explainer: {
        stepType: "Email Marketing sync step",
        description:
          "Push emails and custom DM profile attributes into Klaviyo lists to kick off automated email marketing flows and segments.",
        trigger: "User opt-in via comment",
        action: "Add Profile to Klaviyo List",
      },
    },
    {
      id: "mailerlite",
      name: "MailerLite",
      category: ["Email Marketing"],
      description:
        "Connect your MailerLite account to automatically sync your contacts to your subscriber list",
      providerKey: "mailerlite",
      iconBg: "#f0fdfa",
      iconColor: "#0d9488",
      logo: <Mail size={20} color="#0d9488" />,
      explainer: {
        stepType: "Email Marketing step",
        description:
          "Subscribe qualified leads into MailerLite groups with mapped custom fields for ongoing campaign newsletters.",
        trigger: "Lead shares contact info",
        action: "Subscribe to MailerLite Group",
      },
    },
    {
      id: "stripe",
      name: "Stripe",
      category: ["Payments"],
      description: "Connect your Stripe account to use Stripe-powered features across Nemio.",
      providerKey: "stripe",
      iconBg: "#eef2ff",
      iconColor: "#4338ca",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "14px", color: "#4338ca" }}>S</div>
      ),
      explainer: {
        stepType: "Payments & Checkout step",
        description:
          "Generate instant secure Stripe checkout links in chat. Confirm payments and automatically trigger fulfillment workflows.",
        trigger: "Customer agrees to purchase",
        action: "Generate Stripe Checkout Link",
      },
    },
    {
      id: "poppy-ai",
      name: "Poppy AI",
      category: ["Voice & AI Media"],
      description: "Connect Poppy AI for intelligent automation responses",
      providerKey: "poppy_ai",
      iconBg: "#fff1f2",
      iconColor: "#f43f5e",
      logo: <Sparkles size={20} color="#f43f5e" />,
      explainer: {
        stepType: "Automation builder step",
        description:
          "Use Poppy AI models to evaluate lead sentiment and personalize conversational copy dynamically.",
        trigger: "Inbound conversation initiated",
        action: "Run Poppy AI Persona Evaluator",
      },
    },
    {
      id: "systeme-io",
      name: "Systeme.io",
      category: ["Email Marketing", "CRM & Contacts"],
      description:
        "Connect your Systeme.io account to automatically sync your contacts to your audience",
      providerKey: "systeme_io",
      iconBg: "#f0f9ff",
      iconColor: "#0284c7",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "14px", color: "#0284c7" }}>S</div>
      ),
      explainer: {
        stepType: "Marketing & CRM step",
        description:
          "Automatically tag and enroll leads in Systeme.io courses, funnels, and email campaigns from social conversations.",
        trigger: "Lead signs up in DM",
        action: "Enroll Contact in Systeme.io",
      },
    },
    {
      id: "vapi",
      name: "Vapi",
      category: ["Voice & AI Media"],
      description: "Connect Vapi for AI-powered phone calls in automations",
      providerKey: "vapi",
      iconBg: "#ecfdf5",
      iconColor: "#059669",
      logo: <PhoneCall size={20} color="#059669" />,
      explainer: {
        stepType: "AI Voice phone call step",
        description:
          "Trigger outbound AI voice phone calls to leads immediately upon DM qualification with real-time conversational agents.",
        trigger: "Lead requests immediate phone call",
        action: "Initiate Vapi AI Phone Call",
      },
    },
    {
      id: "retell",
      name: "Retell",
      category: ["Voice & AI Media"],
      description: "Connect Retell for realtime AI voice calls in your automations",
      providerKey: "retell",
      iconBg: "#f8fafc",
      iconColor: "#0f172a",
      logo: <Mic size={20} color="#0f172a" />,
      explainer: {
        stepType: "Realtime Voice step",
        description:
          "Power low-latency bidirectional voice agents that call customers back within seconds of an Instagram conversation.",
        trigger: "Lead books voice callback",
        action: "Spawn Retell Realtime Voice Call",
      },
    },
    {
      id: "airtable",
      name: "Airtable",
      category: ["Data & Records", "Knowledge Base"],
      description:
        "Connect Airtable to your Nemio Account as a knowledgebase and database for your automations!",
      providerKey: "airtable",
      iconBg: "#fffbeb",
      iconColor: "#d97706",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L1 8l11 6 11-6-11-6zm0 13.5L3.5 10 1 11.5l11 6 11-6L20.5 10 12 15.5zm0 4.5L3.5 14.5 1 16l11 6 11-6-2.5-1.5L12 20z" />
        </svg>
      ),
      explainer: {
        stepType: "Database & Knowledge step",
        description:
          "Sync lead records, conversation transcripts, and order metadata into Airtable bases in real time.",
        trigger: "Form submission completed",
        action: "Append Record in Airtable Base",
      },
    },
    // Coming Soon Apps
    {
      id: "salesforce",
      name: "Salesforce",
      category: ["CRM & Contacts"],
      description: "Enterprise CRM sync for enterprise pipelines and account management.",
      status: "coming_soon",
      iconBg: "#f0f9ff",
      iconColor: "#0284c7",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z" />
        </svg>
      ),
    },
    {
      id: "hubspot",
      name: "HubSpot",
      category: ["CRM & Contacts"],
      description: "Inbound CRM, deal pipelines, and marketing hub synchronization.",
      status: "coming_soon",
      iconBg: "#fff7ed",
      iconColor: "#ea580c",
      logo: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14.93V18h-2v-1.07A4.002 4.002 0 0 1 8 13h2a2 2 0 1 0 4 0c0-1.1-.9-2-2-2-2.21 0-4-1.79-4-4a4 4 0 0 1 3-3.86V3h2v1.14A4.002 4.002 0 0 1 16 8h-2a2 2 0 0 0-4 0c0 1.1.9 2 2 2 2.21 0 4 1.79 4 4a3.996 3.996 0 0 1-3 3.93z" />
        </svg>
      ),
    },
    {
      id: "zapier",
      name: "Zapier",
      category: ["Workflow Tools"],
      description: "Connect 5,000+ external apps via Zapier instant zaps and triggers.",
      status: "coming_soon",
      iconBg: "#fff7ed",
      iconColor: "#f97316",
      logo: (
        <div style={{ fontWeight: 800, fontSize: "16px", color: "#f97316" }}>_</div>
      ),
    },
  ];

  // Filter apps by category
  const filteredApps = APPS.filter((app) => {
    if (selectedCategory === "All") return true;
    return app.category.includes(selectedCategory);
  });

  const isConnected = (providerKey?: string) => {
    if (!providerKey) return false;
    return integrations.some((i) => i.provider === providerKey && i.configured);
  };

  const handleActionClick = (app: AppItem) => {
    if (app.status === "coming_soon") return;

    if (isConnected(app.providerKey)) {
      disconnectIntegration(app.providerKey!);
      return;
    }

    if (app.oauthSupported && app.oauthAction === "google_calendar") {
      connectOAuth("google_calendar");
      return;
    }
    if (app.oauthSupported && app.oauthAction === "slack") {
      connectOAuth("slack");
      return;
    }

    // Open configuration modal
    if (app.providerKey) {
      setConfiguring(app.providerKey);
    }
  };

  return (
    <div className="boosend-integrations-page">
      {/* Page Header */}
      <div className="boosend-integrations-header">
        <div>
          <h1 className="boosend-integrations-title">Integrations</h1>
          <p className="boosend-integrations-sub">
            Connect external platforms for automation workflows
          </p>
        </div>

        {/* Tab Switcher: Gallery vs Developer API & Webhooks */}
        <div className="boosend-view-tabs">
          <button
            type="button"
            className={`boosend-view-tab ${activeTab === "gallery" ? "active" : ""}`}
            onClick={() => setActiveTab("gallery")}
          >
            <LayoutGrid size={15} />
            Apps Gallery
          </button>
          <button
            type="button"
            className={`boosend-view-tab ${activeTab === "developer" ? "active" : ""}`}
            onClick={() => setActiveTab("developer")}
          >
            <Code2 size={15} />
            API & Webhooks
          </button>
        </div>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {activeTab === "gallery" ? (
        <>
          {/* Category Filter Pills (Screenshots 5, 6) */}
          <div className="boosend-categories-bar">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                className={`boosend-cat-pill ${selectedCategory === cat ? "active" : ""}`}
                onClick={() => setSelectedCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* 3-Column App Cards Grid (Screenshots 5, 6, 7) */}
          <div className="boosend-integrations-grid">
            {filteredApps.map((app) => {
              const connected = isConnected(app.providerKey);
              const isComingSoon = app.status === "coming_soon";

              return (
                <div key={app.id} className="boosend-int-card">
                  <div>
                    {/* Head: Brand Logo + Platform Name */}
                    <div className="boosend-int-card-head">
                      <div
                        className="boosend-int-logo"
                        style={{ backgroundColor: app.iconBg, color: app.iconColor }}
                      >
                        {app.logo}
                      </div>
                      <span className="boosend-int-name">{app.name}</span>
                    </div>

                    {/* Description */}
                    <p className="boosend-int-desc">{app.description}</p>
                  </div>

                  {/* Footer Actions */}
                  <div className="boosend-int-footer">
                    {isComingSoon ? (
                      <span className="boosend-pill-coming">
                        <Clock size={13} />
                        Coming Soon
                      </span>
                    ) : connected ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span className="boosend-pill-connected">
                          <CheckCircle2 size={13} />
                          Connected
                        </span>
                        <button
                          type="button"
                          className="boosend-btn-what"
                          onClick={() => handleActionClick(app)}
                        >
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="boosend-btn-create"
                        onClick={() => handleActionClick(app)}
                      >
                        Create Integration
                      </button>
                    )}

                    {!isComingSoon && (
                      <button
                        type="button"
                        className="boosend-btn-what"
                        onClick={() => setExplainingApp(app)}
                      >
                        <HelpCircle size={13} />
                        What does this do?
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        /* Developer Tools Tab (API Keys & Outbound Webhooks without cluttering main view) */
        <div style={{ display: "flex", flexDirection: "column", gap: "24px", marginTop: "12px" }}>
          {/* Connectors overview */}
          <div className="boosend-int-card" style={{ padding: "20px" }}>
            <h3 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "#0f172a" }}>
              Ready-made Connectors
            </h3>
            <p style={{ fontSize: "13px", color: "#64748b", margin: "6px 0 16px" }}>
              Pre-built packages living in <code>connectors/</code>. Authenticate with an API key below.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
              {[
                { name: "Zapier", path: "connectors/zapier", text: "Instant triggers & message actions" },
                { name: "n8n", path: "connectors/n8n", text: "Community node: Trigger + CRM node" },
                { name: "Make.com", path: "connectors/make", text: "Custom app: Watch events & search leads" },
              ].map((c) => (
                <div
                  key={c.name}
                  style={{
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    borderRadius: "10px",
                    padding: "12px",
                  }}
                >
                  <strong style={{ fontSize: "13px" }}>{c.name}</strong>
                  <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>{c.text}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
            {/* API Keys */}
            <div className="boosend-int-card" style={{ padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#0f172a", margin: 0 }}>
                  API Keys
                </h3>
                <span style={{ fontSize: "11px", color: "#94a3b8" }}>Header: X-API-Key</span>
              </div>

              {keys.length ? (
                <div style={{ marginTop: "14px" }}>
                  <Table head={["Name", "Prefix", "Scopes", ""]}>
                    {keys.map((key) => (
                      <tr key={key.id}>
                        <td>
                          <strong>{key.name}</strong>
                          <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                            {when(key.created_at)}
                          </div>
                        </td>
                        <td className="mono">{key.prefix}…</td>
                        <td>
                          <span style={{ display: "flex", gap: "4px" }}>
                            {key.scopes.map((s) => (
                              <Pill key={s}>{s}</Pill>
                            ))}
                          </span>
                        </td>
                        <td>
                          {owner && (
                            <button
                              type="button"
                              className="text-button"
                              disabled={feedback.busy}
                              onClick={() => revokeKey(key)}
                            >
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </Table>
                </div>
              ) : (
                <Empty>No API keys yet.</Empty>
              )}

              {newKey && (
                <div style={{ marginTop: "12px" }}>
                  <CopyField label="New API key (shown once)" value={newKey} />
                </div>
              )}

              {owner && (
                <form className="form-grid" style={{ marginTop: "16px" }} onSubmit={createKey}>
                  <label>
                    Key name
                    <input name="name" maxLength={80} placeholder="e.g. My Automation Script" required />
                  </label>
                  <div style={{ display: "flex", gap: "16px" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px" }}>
                      <input type="checkbox" name="read" defaultChecked />
                      Read
                    </label>
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px" }}>
                      <input type="checkbox" name="write" />
                      Write
                    </label>
                  </div>
                  <button className="button primary small" style={{ marginTop: "8px" }} disabled={feedback.busy}>
                    <KeyRound size={14} />
                    Create Key
                  </button>
                </form>
              )}
            </div>

            {/* Outbound Webhooks */}
            <div className="boosend-int-card" style={{ padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#0f172a", margin: 0 }}>
                  Outbound Webhooks
                </h3>
                <span style={{ fontSize: "11px", color: "#94a3b8" }}>REST Hooks</span>
              </div>
              <p style={{ fontSize: "12px", color: "#64748b", margin: "6px 0 14px" }}>
                Sign events with HMAC-SHA256 signature header for verification.
              </p>

              {subscriptions.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {subscriptions.map((sub) => (
                    <div
                      key={sub.id}
                      style={{
                        padding: "10px",
                        background: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <strong className="mono">{sub.url}</strong>
                        <button
                          type="button"
                          className="text-button"
                          style={{ color: "#ef4444" }}
                          onClick={() => removeSubscription(sub)}
                        >
                          Remove
                        </button>
                      </div>
                      <div style={{ display: "flex", gap: "4px", marginTop: "6px" }}>
                        {sub.events.map((e) => (
                          <Pill key={e}>{e}</Pill>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>No active webhook subscriptions.</Empty>
              )}

              {newSecret && (
                <div style={{ marginTop: "12px" }}>
                  <CopyField label="Signing secret (shown once)" value={newSecret} />
                </div>
              )}

              <form className="form-grid" style={{ marginTop: "16px" }} onSubmit={createSubscription}>
                <label>
                  Endpoint URL
                  <input name="url" type="url" placeholder="https://api.yourdomain.com/webhook" required />
                </label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", fontSize: "12px" }}>
                  {WEBHOOK_EVENTS.map((name) => (
                    <label key={name} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                      <input type="checkbox" name={name} />
                      {name}
                    </label>
                  ))}
                </div>
                <button className="button primary small" style={{ marginTop: "8px" }} disabled={feedback.busy}>
                  <Webhook size={14} />
                  Subscribe Endpoint
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Screenshot 7 Explainer Canvas Modal */}
      {explainingApp && (
        <div className="boosend-modal-overlay" onClick={() => setExplainingApp(null)}>
          <div className="boosend-modal-window" onClick={(e) => e.stopPropagation()}>
            <div className="boosend-modal-header">
              <div className="boosend-modal-appinfo">
                <div
                  className="boosend-int-logo"
                  style={{
                    backgroundColor: explainingApp.iconBg,
                    color: explainingApp.iconColor,
                    width: "36px",
                    height: "36px",
                  }}
                >
                  {explainingApp.logo}
                </div>
                <strong style={{ fontSize: "16px", color: "#0f172a" }}>{explainingApp.name}</strong>
                <span className="boosend-step-pill">
                  {explainingApp.explainer?.stepType || "Automation builder step"}
                </span>
              </div>
              <button
                type="button"
                className="boosend-modal-close-btn"
                onClick={() => setExplainingApp(null)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="boosend-modal-body">
              <p className="boosend-modal-desc">
                {explainingApp.explainer?.description ||
                  `Add a ${explainingApp.name} step to your automation to trigger one of your ${explainingApp.name} workflows from a conversation. Nemio sends the conversation data over, your workflow runs its custom logic, and the result comes back into the chat.`}
              </p>

              {/* Two-Frame Interactive Animated Storyboard (Builder Step ➔ Live Execution) */}
              <IntegrationAnimatedExplainer app={explainingApp} />

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "20px" }}>
                <button
                  type="button"
                  className="boosend-btn-create"
                  onClick={() => setExplainingApp(null)}
                >
                  Got it
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Integration Setup Modal */}
      {configuring && (
        <Modal
          title={`Configure ${APPS.find((a) => a.providerKey === configuring)?.name || configuring}`}
          onClose={() => setConfiguring("")}
        >
          <form className="form-grid" onSubmit={saveIntegration}>
            <label
              className="inline"
              style={{
                display: "flex",
                flexDirection: "row",
                alignItems: "center",
                gap: "10px",
                marginBottom: "18px",
                cursor: "pointer",
                fontSize: "13.5px",
                fontWeight: 500,
                color: "#1e293b",
              }}
            >
              <input
                type="checkbox"
                name="is_test"
                checked={testMode}
                onChange={(e) => setTestMode(e.target.checked)}
                style={{
                  width: "18px",
                  height: "18px",
                  accentColor: "#0f1117",
                  margin: 0,
                  cursor: "pointer",
                }}
              />
              Use local test simulation (no live external API calls)
            </label>

            {!testMode && (
              <>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "14px", fontSize: "13px", fontWeight: 600, color: "#334155" }}>
                  API Key or Secret Token
                  <input
                    name="cred_api_key"
                    type="password"
                    placeholder="Enter your API token"
                    style={{
                      border: "1px solid #cbd5e1",
                      borderRadius: "8px",
                      padding: "10px 12px",
                      fontSize: "13.5px",
                      outline: "none",
                      color: "#0f172a",
                    }}
                    required
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "14px", fontSize: "13px", fontWeight: 600, color: "#334155" }}>
                  Account / Workspace ID (optional)
                  <input
                    name="cred_account_id"
                    placeholder="e.g. workspace_123"
                    style={{
                      border: "1px solid #cbd5e1",
                      borderRadius: "8px",
                      padding: "10px 12px",
                      fontSize: "13.5px",
                      outline: "none",
                      color: "#0f172a",
                    }}
                  />
                </label>
              </>
            )}

            <div className="form-actions" style={{ marginTop: "20px", display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button
                type="button"
                className="button secondary"
                onClick={() => setConfiguring("")}
                style={{
                  background: "#ffffff",
                  color: "#334155",
                  border: "1px solid #cbd5e1",
                  borderRadius: "8px",
                  padding: "9px 16px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="button primary"
                disabled={feedback.busy}
                style={{
                  background: "#0f1117",
                  color: "#ffffff",
                  border: "1px solid #0f1117",
                  borderRadius: "8px",
                  padding: "9px 18px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {feedback.busy ? "Connecting…" : "Save Integration"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
