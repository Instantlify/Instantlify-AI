import {
  CalendarDays,
  FileText,
  TrendingUp,
  Link2,
  MessageSquareText,
  ShieldBan,
  Smartphone,
  GraduationCap,
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
    id: "tutorials",
    label: "Tutorials",
    icon: GraduationCap,
    description:
      "Step-by-step setup guides that tick off as you complete them.",
    highlights: ["Live setup checklist", "Links to each step"],
    section: "tutorials",
    agents: true,
  },
  {
    id: "forum",
    label: "Community",
    icon: MessageSquareText,
    description: "Share questions and answers with Instantlify members.",
    highlights: ["Discussions and replies", "Community search assistant"],
    section: "forum",
    agents: true,
  },
  {
    id: "forms",
    label: "Forms",
    icon: FileText,
    description: "Publish and embed lead forms with consent and CRM capture.",
    highlights: ["Custom questions", "Response exports"],
    section: "forms",
    agents: false,
  },
  {
    id: "creator-kit",
    label: "Creator kit",
    icon: TrendingUp,
    description: "A public media kit for your work, audience and offers.",
    highlights: ["Shareable page", "Collaboration contact"],
    section: "creator-kit",
    agents: false,
  },
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
      "Plan and schedule Instagram posts, then let Instantlify publish them on time.",
    highlights: ["Scheduled publishing", "Retry and status per post"],
    section: "calendar",
    agents: true,
  },
  {
    id: "shield",
    label: "Comment shield",
    icon: ShieldBan,
    description:
      "Hide, delete or reply to comments on your Meta posts using keyword rules or AI rules written in plain words.",
    highlights: ["Keyword and AI rules", "Hide, delete, flag or reply"],
    section: "shield",
    agents: false,
  },
  {
    id: "deeplinks",
    label: "Smart deep links",
    icon: Smartphone,
    description:
      "Share trackable links to Instagram, WhatsApp and your other destinations.",
    highlights: ["HTTPS destinations", "Per-link click counts"],
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
