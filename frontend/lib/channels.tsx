import { MessageCircle } from "lucide-react";
import type { Connection } from "./api";
import { BrandIcon, type BrandName } from "./brand-icons";

/** Meta channels lead every channel list; the rest follow in this order. */
export const META_CHANNELS = ["instagram", "messenger", "whatsapp"] as const;

const CHANNELS: Record<
  string,
  { label: string; short: string; brand?: BrandName }
> = {
  instagram: { label: "Instagram", short: "IG", brand: "instagram" },
  messenger: { label: "Messenger", short: "FB", brand: "messenger" },
  whatsapp: { label: "WhatsApp", short: "WA", brand: "whatsapp" },
  telegram: { label: "Telegram", short: "TG", brand: "telegram" },
  linkedin: { label: "LinkedIn", short: "LI", brand: "linkedin" },
  webchat: { label: "Website chat", short: "Web" },
};

/** The provider's real logo, or a generic chat glyph for unknown providers. */
function ProviderMark({ provider, size }: { provider: string; size: number }) {
  const brand = CHANNELS[provider]?.brand;
  return brand ? (
    <BrandIcon name={brand} size={size} />
  ) : (
    <MessageCircle size={size} aria-hidden="true" />
  );
}

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
  return (
    <span className={`channel-icon channel-${provider}`} aria-hidden="true">
      <ProviderMark provider={provider} size={size} />
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
  return (
    <span
      className={`channel-badge channel-${provider}`}
      title={channelLabel(provider)}
    >
      <ProviderMark provider={provider} size={12} />
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
