"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, message, type Automation } from "@/lib/api";
import { ErrorNotice, Panel } from "@/components/ui";

export function AutomationStarter({
  workspaceId,
  prefix,
}: {
  workspaceId: string;
  prefix: string;
}) {
  const router = useRouter();
  const [goal, setGoal] = useState("pricing");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const text = String(data.get("reply") || "").trim();
    const keyword = String(data.get("keyword") || "").trim();
    const url = String(data.get("url") || "").trim();
    if (
      !text ||
      !keyword ||
      (goal === "booking" && !/^https:\/\/[^\s]+$/i.test(url))
    ) {
      setError(
        "Add a keyword, a reply and, for booking, a valid HTTPS booking link.",
      );
      setBusy(false);
      return;
    }
    const nodes = [
      {
        id: "welcome",
        position: { x: 80, y: 80 },
        data:
          goal === "booking"
            ? {
                kind: "send_buttons",
                text,
                buttons: [{ type: "web_url", url, title: "Choose a time" }],
              }
            : { kind: "send_message", text },
      },
      ...(goal === "qualify"
        ? [
            { id: "wait", position: { x: 80, y: 240 }, data: { kind: "wait" } },
            {
              id: "thanks",
              position: { x: 80, y: 400 },
              data: {
                kind: "send_message",
                text: "Thanks for sharing. Our team can review your reply here and help with the next step.",
              },
            },
          ]
        : []),
      {
        id: "done",
        position: { x: 80, y: goal === "qualify" ? 560 : 240 },
        data: { kind: "end" },
      },
    ];
    const draft = {
      start: "welcome",
      triggers: [{ kind: String(data.get("trigger")), keyword }],
      nodes,
      edges: nodes
        .slice(0, -1)
        .map((node, index) => ({
          id: `${node.id}-${nodes[index + 1].id}`,
          source: node.id,
          target: nodes[index + 1].id,
        })),
    };
    try {
      const item = await api<Automation>(`${prefix}/automations/`, "POST", {
        name:
          goal === "pricing"
            ? "Answer pricing questions"
            : goal === "qualify"
              ? "Qualify an enquiry"
              : "Share a booking link",
        draft,
      });
      router.push(`/w/${workspaceId}/automations/${item.id}`);
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }
  return (
    <Panel title="Start with a customer goal">
      <p>
        Fill in your business details to create a draft. Review it before
        publishing.
      </p>
      <form onSubmit={create} className="form-grid">
        <label>
          What should happen first?
          <select
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
          >
            <option value="pricing">Answer pricing questions</option>
            <option value="qualify">Ask what the customer needs</option>
            <option value="booking">Share my booking link</option>
          </select>
        </label>
        <label>
          When a customer sends
          <select name="trigger">
            <option value="comment">A comment</option>
            <option value="dm">A direct message</option>
            <option value="story_reply">A story reply</option>
          </select>
        </label>
        <label>
          Containing this keyword
          <input
            key={goal}
            name="keyword"
            defaultValue={
              goal === "pricing"
                ? "price"
                : goal === "booking"
                  ? "book"
                  : "interested"
            }
            maxLength={100}
            required
          />
        </label>
        <label>
          {goal === "qualify" ? "Your qualifying question" : "Your reply"}
          <textarea
            key={goal}
            name="reply"
            placeholder={
              goal === "pricing"
                ? "Our consultation costs… and includes…"
                : goal === "qualify"
                  ? "Which service are you interested in, and when would you like to start?"
                  : "You can find a time that works for you using the link below."
            }
            maxLength={1000}
            required
          />
        </label>
        {goal === "booking" && (
          <label>
            Booking page
            <input
              name="url"
              type="url"
              placeholder="https://your-booking-page.com"
              required
            />
            <small>
              This shares your scheduling page; it does not confirm a booking
              automatically.
            </small>
          </label>
        )}
        {goal === "qualify" && (
          <p>
            The reply is saved in the inbox for your team to review. This
            starter does not automatically score leads.
          </p>
        )}
        <div className="form-actions">
          <button className="button primary" disabled={busy}>
            {busy ? "Creating draft…" : "Create starter draft"}
          </button>
        </div>
      </form>
      <ErrorNotice error={error} />
    </Panel>
  );
}
