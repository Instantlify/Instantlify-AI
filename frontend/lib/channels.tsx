import {
  Facebook,
  Instagram,
  Linkedin,
  MessageCircle,
  Send,
  type LucideIcon,
} from "lucide-react";
import type { Connection } from "./api";

/** Meta channels lead every channel list; the rest follow in this order. */
export const META_CHANNELS = ["instagram", "messenger", "whatsapp"] as const;

const CHANNELS: Record<
  string,
  { label: string; short: string; icon: LucideIcon }
> = {
  instagram: { label: "Instagram", short: "IG", icon: Instagram },
  messenger: { label: "Facebook", short: "FB", icon: Facebook },
  whatsapp: { label: "WhatsApp", short: "WA", icon: MessageCircle },
  telegram: { label: "Telegram", short: "TG", icon: Send },
  linkedin: { label: "LinkedIn", short: "LI", icon: Linkedin },
};

export function channelLabel(provider: string) {
  return CHANNELS[provider]?.label ?? provider;
}

export function ChannelIcon({
  provider,
  size = 14,
}: {
  provider: string;
  size?: number;
}) {
  const Icon = CHANNELS[provider]?.icon ?? MessageCircle;
  return (
    <span className={`channel-icon channel-${provider}`} aria-hidden="true">
      <Icon size={size} />
    </span>
  );
}

/** Soft container pill in the channel's brand colour. */
export function ChannelBadge({
  provider,
  compact = false,
}: {
  provider: string;
  compact?: boolean;
}) {
  const meta = CHANNELS[provider];
  const Icon = meta?.icon ?? MessageCircle;
  return (
    <span
      className={`channel-badge channel-${provider}`}
      title={channelLabel(provider)}
    >
      <Icon size={12} aria-hidden="true" />
      {compact ? (meta?.short ?? provider) : channelLabel(provider)}
    </span>
  );
}

export type TokenHealth = "active" | "expiring" | "reconnect";

const EXPIRY_WARNING_MS = 7 * 24 * 3600 * 1000;

/** Token state for the account switcher. `now` is passed in so renders stay pure. */
export function tokenHealth(connection: Connection, now: number): TokenHealth {
  const expires = new Date(connection.expires_at).getTime();
  if (connection.status !== "active" || expires <= now) return "reconnect";
  if (expires - now < EXPIRY_WARNING_MS) return "expiring";
  return "active";
}

export const TOKEN_LABELS: Record<TokenHealth, string> = {
  active: "Active",
  expiring: "Expiring soon",
  reconnect: "Reconnect required",
};

export const compactNumber = (value: number) =>
  new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

/** Connections that can appear in the switcher: everything not disconnected. */
export const switchable = (connections: Connection[]) =>
  connections
    .filter((item) => item.status !== "disconnected")
    .sort(
      (a, b) =>
        rank(a.provider) - rank(b.provider) ||
        a.display_name.localeCompare(b.display_name),
    );

const rank = (provider: string) => {
  const index = Object.keys(CHANNELS).indexOf(provider);
  return index < 0 ? 99 : index;
};
