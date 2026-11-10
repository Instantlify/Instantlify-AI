import type { CSSProperties } from "react";
import type { Branding } from "./api";

export const DEFAULT_WORKSPACE_COLOR = "#b4f277";
export const DEFAULT_SIDEBAR_BACKGROUND = "#0e161a";
export const DEFAULT_SIDEBAR_TEXT = "#dce6e5";
export const isThemeColor = (value: string) => /^#[0-9a-f]{6}$/i.test(value);
const color = (value: string | undefined, fallback: string) =>
  value && isThemeColor(value) ? value : fallback;
const rgb = (hex: string) =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
function mix(first: string, second: string, amount: number) {
  const left = rgb(first),
    right = rgb(second);
  return `#${left
    .map((v, i) =>
      Math.round(v * (1 - amount) + right[i] * amount)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}
function luminance(hex: string) {
  const channels = rgb(hex).map((value) => {
    const v = value / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
export function colorContrast(first: string, second: string) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
export function workspaceTheme(branding: Branding): CSSProperties {
  // Upgrade the former Instantlify defaults; explicit white-label palettes stay intact.
  const legacyDefault =
    (!branding.primary_color ||
      ["#10244a", "#347359"].includes(branding.primary_color.toLowerCase())) &&
    (!branding.sidebar_bg_color ||
      branding.sidebar_bg_color.toLowerCase() === "#ffffff") &&
    (!branding.sidebar_text_color ||
      branding.sidebar_text_color.toLowerCase() === "#41516e");
  const primary = legacyDefault
    ? DEFAULT_WORKSPACE_COLOR
    : color(branding.primary_color, DEFAULT_WORKSPACE_COLOR);
  const background = color(
    legacyDefault ? undefined : branding.sidebar_bg_color,
    DEFAULT_SIDEBAR_BACKGROUND,
  );
  const text = color(
    legacyDefault ? undefined : branding.sidebar_text_color,
    DEFAULT_SIDEBAR_TEXT,
  );
  const foreground =
    colorContrast(primary, "#0c1b3a") >= 4.5
      ? "#0c1b3a"
      : colorContrast(primary, "#ffffff") >= colorContrast(primary, "#000000")
        ? "#ffffff"
        : "#000000";
  // Move hover away from its label color so contrast cannot drop on hover.
  const hover = mix(
    primary,
    foreground === "#ffffff" ? "#000000" : "#ffffff",
    0.12,
  );
  let link = primary;
  for (let i = 0; i < 20 && colorContrast(link, "#0b1013") < 4.5; i++)
    link = mix(link, "#ffffff", 0.15);
  return {
    "--brand-primary": primary,
    "--brand-action": primary,
    "--green": primary,
    "--brand-primary-hover": hover,
    "--brand-action-hover": hover,
    "--brand-primary-light": mix(primary, "#0b1013", 0.88),
    "--brand-on-primary": foreground,
    "--brand-link": link,
    "--brand-sidebar": background,
    "--workspace-indicator":
      colorContrast(primary, "#c3ff5c") >= 3 ? "#c3ff5c" : foreground,
    "--workspace-sidebar-text": text,
    "--workspace-sidebar-muted": mix(background, text, 0.8),
    "--workspace-sidebar-card": mix(background, text, 0.035),
    "--workspace-sidebar-hover": mix(background, text, 0.08),
    "--workspace-sidebar-border": mix(background, text, 0.16),
  } as CSSProperties;
}
