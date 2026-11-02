import type { LeadRow } from "@/lib/api";

export function contactSourceLabel(lead: LeadRow): string {
  if (lead.fields?.source === "form") return "Added via form";
  if (lead.identities.length || lead.channels.length)
    return "Added via channel";
  return "Added by hand";
}
