import type { CSSProperties } from "react";
import type { Branding } from "./api";

export const DEFAULT_WORKSPACE_COLOR = "#10244a";
export const DEFAULT_SIDEBAR_BACKGROUND = "#ffffff";
export const DEFAULT_SIDEBAR_TEXT = "#41516e";
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
  const primary = color(branding.primary_color, DEFAULT_WORKSPACE_COLOR);
  const background = color(
    branding.sidebar_bg_color,
    DEFAULT_SIDEBAR_BACKGROUND,
  );
  const text = color(branding.sidebar_text_color, DEFAULT_SIDEBAR_TEXT);
  const foreground =
    colorContrast(primary, "#ffffff") >= colorContrast(primary, "#0c1b3a")
      ? "#ffffff"
      : "#0c1b3a";
  let link = primary;
  for (let i = 0; i < 20 && colorContrast(link, "#ffffff") < 4.5; i++)
    link = mix(link, "#0c1b3a", 0.15);
  return {
    "--brand-primary": primary,
    "--brand-action": primary,
    "--green": primary,
    "--brand-primary-hover": mix(primary, "#000000", 0.12),
    "--brand-action-hover": mix(primary, "#000000", 0.12),
    "--brand-primary-light": mix(primary, "#ffffff", 0.92),
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
