import type { FlowGraph, FlowNodeData } from "./api";

export type GuidedPlatform = "instagram" | "facebook" | "whatsapp" | "telegram";
export const GUIDED_CHANNELS: Record<GuidedPlatform, string> = {
  instagram: "instagram",
  facebook: "messenger",
  whatsapp: "whatsapp",
  telegram: "telegram",
};
export type GuidedSettings = {
  platform: GuidedPlatform;
  connectionId: string;
  trigger: "comment" | "story_reply" | "dm" | "live_comment";
  matchAny: boolean;
  keywords: string;
  postScope?: "all" | "specific" | "next";
  postIds?: string[];
  publicReplies?: string[];
  opening: boolean;
  openingText: string;
  openingButton: string;
  requireFollow?: boolean;
  followText?: string;
  followButton?: string;
  collectEmail: boolean;
  emailQuestion: string;
  resourceText: string;
  trackClicks?: boolean;
  reminder?: boolean;
  reminderDelay?: number;
  reminderText?: string;
  links: { title: string; url: string }[];
  tag: string;
  assignee: string;
  transfer: string;
};

/** Compile every offered setting into an executable, inspectable graph. */
export function compileGuidedAutomation(
  settings: GuidedSettings,
  responseToken: string,
): FlowGraph {
  const text = (value: string, label: string, limit = 2000) => {
    const clean = value.trim();
    if (!clean || clean.length > limit)
      throw new Error(`${label} needs 1–${limit} characters.`);
    return clean;
  };
  if (!settings.connectionId)
    throw new Error("Choose a connected account before saving.");
  const channel = GUIDED_CHANNELS[settings.platform];
  if (
    (settings.trigger === "story_reply" ||
      settings.trigger === "live_comment") &&
    channel !== "instagram"
  )
    throw new Error("Story replies and live comments require Instagram.");
  if (
    settings.trigger === "comment" &&
    !["instagram", "messenger"].includes(channel)
  )
    throw new Error("Comments require Instagram or Facebook.");
  const postIds =
    settings.trigger === "comment" && settings.postScope === "specific"
      ? settings.postIds || []
      : [];
  if (
    settings.trigger === "comment" &&
    settings.postScope === "specific" &&
    (!postIds.length ||
      postIds.length > 50 ||
      postIds.some((id) => !/^[A-Za-z0-9_-]{1,200}$/.test(id)))
  )
    throw new Error("Choose at least one post for this comment trigger.");
  const publicReplies =
    settings.trigger === "comment" ? settings.publicReplies || [] : [];
  if (
    publicReplies.length > 10 ||
    publicReplies.some((reply) => !reply.trim() || reply.trim().length > 1000)
  )
    throw new Error(
      "Each public reply needs 1–1000 characters. Add up to 10 variations.",
    );
  const keywords = settings.matchAny
    ? ["*"]
    : [
        ...new Set(
          settings.keywords
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean),
        ),
      ];
  if (
    !keywords.length ||
    keywords.length > 20 ||
    keywords.some((k) => k.length > 100 || (k === "*" && !settings.matchAny))
  )
    throw new Error(
      "Add 1–20 keywords, up to 100 characters each, or choose Any word.",
    );
  if (settings.links.length < 1 || settings.links.length > 3)
    throw new Error("Add 1–3 resource links.");
  const buttons = settings.links.map((link) => {
    const title = text(link.title, "Link label", 20);
    let url: URL;
    try {
      url = new URL(link.url.trim());
    } catch {
      throw new Error("Enter a complete HTTPS link.");
    }
    if (
      url.protocol !== "https:" ||
      !url.hostname ||
      url.username ||
      url.password ||
      url.href.length > 2000
    )
      throw new Error(
        "Resource links need a valid HTTPS address without credentials.",
      );
    return { type: "web_url" as const, title, url: url.href };
  });
  const nodes: FlowGraph["nodes"] = [];
  const add = (id: string, data: FlowNodeData) =>
    nodes.push({ id, data, position: { x: 180, y: 80 + nodes.length * 150 } });
  if (settings.opening) {
    add("opening", {
      kind: "send_buttons",
      text: text(
        settings.openingText,
        "Opening message",
        channel === "whatsapp" ? 1024 : 2000,
      ),
      buttons: [
        {
          type: "postback",
          title: text(settings.openingButton, "Opening button", 20),
          payload: responseToken,
        },
      ],
    });
    add("accept", {
      kind: "wait",
      variable: "opt_in",
      expected_reply: responseToken,
    });
  }
  if (settings.requireFollow && channel === "instagram") {
    add("follow", {
      kind: "follow_gate",
      text: text(settings.followText || "", "Follow request"),
      button_title: text(settings.followButton || "", "Follow button", 20),
      expected_reply: responseToken.slice(0, 56) + ":follow",
    });
  }
  if (settings.collectEmail) {
    add("ask_email", {
      kind: "send_message",
      text: text(settings.emailQuestion, "Email question"),
    });
    add("email", {
      kind: "capture_email",
      variable: "email",
      retry_text:
        "That does not look like a valid email address. Please try again.",
    });
  }
  const resourceText = text(settings.resourceText, "Resource message");
  if (
    channel === "whatsapp" &&
    resourceText.length +
      buttons.reduce(
        (length, b) => length + b.title.length + b.url.length + 3,
        2,
      ) >
      4096
  )
    throw new Error(
      "Shorten the WhatsApp message or resource URLs to fit 4,096 characters.",
    );
  add("resources", {
    kind: "send_buttons",
    text: resourceText,
    buttons,
    ...(settings.trackClicks || settings.reminder
      ? { track_clicks: true }
      : {}),
  });
  if (settings.reminder) {
    const seconds = settings.reminderDelay ?? 3600;
    if (!Number.isInteger(seconds) || seconds < 60 || seconds > 82800)
      throw new Error("Choose a reminder delay between 1 minute and 23 hours.");
    if (
      ["comment", "live_comment"].includes(settings.trigger) &&
      !settings.opening &&
      !settings.collectEmail
    )
      throw new Error(
        "Enable an opening reply or email collection before reminding a commenter.",
      );
    add("reminder-delay", { kind: "delay", seconds });
    add("reminder", {
      kind: "send_reminder",
      source_node: "resources",
      text: text(settings.reminderText || "", "Reminder message"),
    });
  }
  if (settings.tag.trim())
    add("tag", { kind: "add_tag", tag: text(settings.tag, "Tag", 40) });
  if (settings.assignee) {
    const userId = Number(settings.assignee);
    if (!Number.isInteger(userId) || userId < 1)
      throw new Error("Choose a team member.");
    add("assign", { kind: "assign_member", user_id: userId });
  }
  if (settings.transfer)
    add("transfer", { kind: "transfer", automation_id: settings.transfer });
  else add("done", { kind: "end" });
  return {
    connection_id: settings.connectionId,
    ...(settings.trigger === "comment" && settings.postScope === "next"
      ? { comment_post_mode: "next" as const }
      : {}),
    ...(postIds.length ? { comment_post_ids: postIds } : {}),
    ...(publicReplies.length
      ? { comment_replies: publicReplies.map((reply) => reply.trim()) }
      : {}),
    start: nodes[0].id,
    triggers: keywords.map((keyword) => ({
      kind: settings.trigger,
      keyword,
      channel,
    })),
    nodes,
    edges: nodes.slice(1).map((node, i) => ({
      id: `${nodes[i].id}-${node.id}`,
      source: nodes[i].id,
      target: node.id,
    })),
  };
}
