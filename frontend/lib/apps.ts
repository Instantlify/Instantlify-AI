import {
  CalendarDays,
  Link2,
  MessageSquareText,
  ShieldBan,
  Smartphone,
  type LucideIcon,
} from "lucide-react";

export type AppEntry = {
  /** Matches the backend's PINNABLE_APPS for apps that can be pinned. */
  id: string;
  label: string;
  icon: LucideIcon;
  description: string;
  highlights: string[];
  /** Workspace section the app opens; absent while the app is not available yet. */
  section?: string;
  /** Whether agents (not just owners and admins) can open it. */
  agents: boolean;
};

export const APPS: AppEntry[] = [
  {
    id: "bio",
    label: "Link in bio",
    icon: Link2,
    description:
      "A mobile-first bio page with your links, published at your workspace's public address.",
    highlights: ["Custom accent and avatar", "Click tracking per link"],
    section: "bio",
    agents: false,
  },
  {
    id: "calendar",
    label: "Content calendar",
    icon: CalendarDays,
    description:
      "Plan and schedule Instagram posts, then let Nemio publish them on time.",
    highlights: ["Scheduled publishing", "Retry and status per post"],
    section: "calendar",
    agents: true,
  },
  {
    id: "shield",
    label: "Comment shield",
    icon: ShieldBan,
    description:
      "Hide spam and abusive comments on your Meta posts automatically and alert your team.",
    highlights: ["Keyword and toxicity rules", "Team alerts"],
    section: "shield",
    agents: false,
  },
  {
    id: "deeplinks",
    label: "Smart deep links",
    icon: Smartphone,
    description:
      "Links that open the native Instagram or WhatsApp app instead of an in-app browser.",
    highlights: ["Native app hand-off", "Per-link click counts"],
    section: "deeplinks",
    agents: true,
  },
  {
    id: "webchat",
    label: "Web chat widget",
    icon: MessageSquareText,
    description:
      "An embeddable live chat for your website that lands in the same inbox.",
    highlights: ["One-line embed", "Shared inbox and AI agent"],
    section: "webchat",
    agents: false,
  },
];

export const appById = (id: string) => APPS.find((app) => app.id === id);
