import type { FlowGraph } from "./api";

export type MetaTemplate = {
  id: string;
  name: string;
  channel: "instagram" | "messenger" | "whatsapp";
  summary: string;
  steps: string[];
  graph: FlowGraph;
};

/** Ready-made drafts for the most common Meta workflows. Each opens in the builder
 * as a disabled draft; links are placeholders to replace before publishing. */
export const META_TEMPLATES: MetaTemplate[] = [
  {
    id: "comment-lead-magnet",
    name: "Comment → lead magnet",
    channel: "instagram",
    summary:
      "Someone comments a keyword on a post or reel; Instantlify DMs them, asks for an email and sends your guide.",
    steps: ["Comment “SEND”", "Private reply asks for email", "DM the guide"],
    graph: {
      start: "ask_email",
      triggers: [{ kind: "comment", keyword: "SEND", channel: "instagram" }],
      nodes: [
        {
          id: "ask_email",
          position: { x: 80, y: 80 },
          data: {
            kind: "send_message",
            text: "Thanks for commenting! Reply with your best email and I'll send the guide right over.",
          },
        },
        {
          id: "email",
          position: { x: 80, y: 250 },
          data: { kind: "wait", variable: "email" },
        },
        {
          id: "guide",
          position: { x: 80, y: 420 },
          data: {
            kind: "send_buttons",
            text: "Here's your guide. Enjoy!",
            buttons: [
              {
                type: "web_url",
                url: "https://example.com/guide",
                title: "Get the guide",
              },
            ],
          },
        },
        { id: "done", position: { x: 80, y: 590 }, data: { kind: "end" } },
      ],
      edges: [
        { id: "ask_email-email", source: "ask_email", target: "email" },
        { id: "email-guide", source: "email", target: "guide" },
        { id: "guide-done", source: "guide", target: "done" },
      ],
    },
  },
  {
    id: "story-quiz",
    name: "Story reply → quiz",
    channel: "instagram",
    summary:
      "A story reply with your keyword starts a one-question quiz, then branches to a voucher or tips.",
    steps: ["Story reply “QUIZ”", "Ask A or B", "Voucher or tips"],
    graph: {
      start: "question",
      triggers: [
        { kind: "story_reply", keyword: "QUIZ", channel: "instagram" },
      ],
      nodes: [
        {
          id: "question",
          position: { x: 240, y: 80 },
          data: {
            kind: "send_message",
            text: "Thanks for replying! Quick quiz: what do you want first? Reply A for styling tips or B for a voucher.",
          },
        },
        {
          id: "answer",
          position: { x: 240, y: 250 },
          data: { kind: "wait", variable: "answer" },
        },
        {
          id: "check",
          position: { x: 240, y: 420 },
          data: { kind: "condition", variable: "answer", equals: "B" },
        },
        {
          id: "voucher",
          position: { x: 80, y: 590 },
          data: {
            kind: "send_buttons",
            text: "Great pick! Here's your voucher.",
            buttons: [
              {
                type: "web_url",
                url: "https://example.com/voucher",
                title: "Claim voucher",
              },
            ],
          },
        },
        {
          id: "tips",
          position: { x: 400, y: 590 },
          data: {
            kind: "send_message",
            text: "Here are three quick tips to get started: …",
          },
        },
        { id: "done", position: { x: 240, y: 760 }, data: { kind: "end" } },
      ],
      edges: [
        { id: "question-answer", source: "question", target: "answer" },
        { id: "answer-check", source: "answer", target: "check" },
        {
          id: "check-voucher",
          source: "check",
          target: "voucher",
          sourceHandle: "true",
        },
        {
          id: "check-tips",
          source: "check",
          target: "tips",
          sourceHandle: "false",
        },
        { id: "voucher-done", source: "voucher", target: "done" },
        { id: "tips-done", source: "tips", target: "done" },
      ],
    },
  },
  {
    id: "whatsapp-greeting",
    name: "WhatsApp lead greeting",
    channel: "whatsapp",
    summary:
      "A new WhatsApp “hi” gets a warm greeting, a name question and a personal follow-up.",
    steps: ["Message “hi”", "Ask their name", "Personal reply"],
    graph: {
      start: "greet",
      triggers: [{ kind: "dm", keyword: "hi", channel: "whatsapp" }],
      nodes: [
        {
          id: "greet",
          position: { x: 80, y: 80 },
          data: {
            kind: "send_message",
            text: "Hi there, thanks for reaching out! What's your name?",
          },
        },
        {
          id: "name",
          position: { x: 80, y: 250 },
          data: { kind: "wait", variable: "name" },
        },
        {
          id: "follow_up",
          position: { x: 80, y: 420 },
          data: {
            kind: "send_message",
            text: "Lovely to meet you, {{name}}! How can we help today?",
          },
        },
        { id: "done", position: { x: 80, y: 590 }, data: { kind: "end" } },
      ],
      edges: [
        { id: "greet-name", source: "greet", target: "name" },
        { id: "name-follow_up", source: "name", target: "follow_up" },
        { id: "follow_up-done", source: "follow_up", target: "done" },
      ],
    },
  },
];

/** Channels an automation listens on. A trigger without a channel listens wherever
 * its kind can arrive, which for DMs means every connected channel. */
export function triggerChannels(
  triggers: FlowGraph["triggers"] | undefined,
): string[] {
  const found = new Set<string>();
  for (const trigger of triggers || []) {
    if (trigger.channel) found.add(trigger.channel);
    else
      for (const channel of KIND_CHANNELS[trigger.kind] || [])
        found.add(channel);
  }
  return [...found];
}

/** Meta channels each trigger kind can arrive on; mirrors the backend's rules. */
export const KIND_CHANNELS: Record<string, string[]> = {
  dm: ["instagram", "messenger", "whatsapp", "webchat"],
  comment: ["instagram", "messenger"],
  story_reply: ["instagram"],
  live_comment: ["instagram"],
};

export const TRIGGER_LABELS: Record<string, string> = {
  comment: "Post or reel comment",
  dm: "Direct message",
  story_reply: "Story reply",
  live_comment: "Live comment",
};
