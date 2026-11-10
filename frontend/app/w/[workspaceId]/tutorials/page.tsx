"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { api, message } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice, PageHeading, Panel } from "@/components/ui";
import { asList } from "@/lib/as-list";

type Step = { id: string; done: boolean };

const GUIDES: Record<
  string,
  { title: string; text: string; section: string; action: string }
> = {
  connect_channel: {
    title: "Connect a channel",
    text: "Link Instagram, Messenger, WhatsApp or Telegram so customer messages reach your inbox.",
    section: "integrations?tab=channels",
    action: "Connect a channel",
  },
  publish_automation: {
    title: "Publish your first automation",
    text: "Start with a comment-to-DM template or the simple builder, then publish it.",
    section: "automations",
    action: "Open automations",
  },
  configure_agent: {
    title: "Turn on the AI assistant",
    text: "Choose a model and instructions so the assistant can answer when no flow does.",
    section: "agent",
    action: "Set up the AI agent",
  },
  add_knowledge: {
    title: "Teach the AI your business",
    text: "Add FAQs, pricing or your website so replies are grounded in your own facts.",
    section: "agent",
    action: "Add knowledge",
  },
  publish_bio: {
    title: "Publish your link in bio",
    text: "Build a branded page with links, videos and an email signup for your profile.",
    section: "bio",
    action: "Build your page",
  },
  create_form: {
    title: "Create a lead form",
    text: "Collect contact details with consent; responses become CRM contacts.",
    section: "forms",
    action: "Create a form",
  },
  setup_webchat: {
    title: "Add chat to your website",
    text: "Paste one script tag so website visitors land in the same inbox.",
    section: "webchat",
    action: "Set up web chat",
  },
  invite_team: {
    title: "Invite your team",
    text: "Add teammates as admins, agents or read-only viewers.",
    section: "team",
    action: "Invite teammates",
  },
};

export default function TutorialsPage() {
  const { prefix, workspace } = useWorkspace();
  const [steps, setSteps] = useState<Step[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<{ steps: Step[] }>(
      `${prefix}/setup-progress/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((result) => setSteps(asList(result?.steps)))
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, [prefix]);

  const done = steps.filter((step) => step.done).length;
  return (
    <>
      <PageHeading
        eyebrow="Apps / Tutorials"
        title="Get set up, step by step."
        text="Each guide checks your workspace, so finished steps tick themselves off."
      />
      <ErrorNotice error={error} />
      <Panel
        title="Setup guides"
        aside={steps.length ? `${done} of ${steps.length} done` : undefined}
      >
        <div className="card-list">
          {steps.map((step) => {
            const guide = GUIDES[step.id];
            if (!guide) return null;
            return (
              <div
                key={step.id}
                className="card row"
                style={{ gap: 12, alignItems: "flex-start" }}
              >
                {step.done ? (
                  <CheckCircle2
                    size={20}
                    color="var(--good, #16a34a)"
                    aria-label="Done"
                  />
                ) : (
                  <Circle
                    size={20}
                    className="subtle"
                    aria-label="Not done yet"
                  />
                )}
                <div style={{ flex: 1 }}>
                  <strong>{guide.title}</strong>
                  <p className="muted-text" style={{ margin: "4px 0 0" }}>
                    {guide.text}
                  </p>
                </div>
                <Link
                  className={`button small ${step.done ? "secondary" : "primary"}`}
                  href={`/w/${workspace.id}/${guide.section}`}
                >
                  {step.done ? "Review" : guide.action}
                </Link>
              </div>
            );
          })}
        </div>
      </Panel>
    </>
  );
}
