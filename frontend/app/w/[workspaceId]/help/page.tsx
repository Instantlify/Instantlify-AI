"use client";

import Link from "next/link";
import { useWorkspace } from "@/lib/workspace";
import { PageHeading } from "@/components/ui";

export default function HelpPage() {
  const { workspace } = useWorkspace();
  const w = `/w/${workspace.id}`;
  return (
    <>
      <PageHeading
        eyebrow="Getting started"
        title="Start with the essentials."
      />
      <section className="panel help-panel stack">
        <div>
          <h3>1. Connect a channel</h3>
          <p>
            Instagram connects through Meta login on the{" "}
            <Link href={`${w}/overview`}>Overview</Link>. WhatsApp, Messenger
            and Telegram are added under{" "}
            <Link href={`${w}/settings`}>Settings → Channels</Link>.
          </p>
        </div>
        <div>
          <h3>2. Build an automation</h3>
          <p>
            In <Link href={`${w}/automations`}>Automations</Link>, create a flow
            such as “comment <em>price</em> → DM with a button → wait for a
            reply → branch”. Publish it and it fires on every matching comment
            or message. Import a template from the{" "}
            <Link href={`${w}/templates`}>marketplace</Link> to start faster.
          </p>
        </div>
        <div>
          <h3>3. Train the AI agent</h3>
          <p>
            Add your FAQ and pricing under{" "}
            <Link href={`${w}/agent`}>AI agent</Link>, choose the tools it may
            use, and switch it on. Enable AI per conversation in the inbox.
            Booking always asks the customer to confirm with a code, and
            payments can only use offers you created.
          </p>
        </div>
        <div>
          <h3>4. Work the inbox together</h3>
          <p>
            The <Link href={`${w}/inbox`}>Inbox</Link> shows every channel in
            one place. Assign conversations, leave internal notes, and take over
            when the agent hands off. Invite teammates from{" "}
            <Link href={`${w}/team`}>Team</Link>.
          </p>
        </div>
        <div>
          <h3>5. Measure and grow</h3>
          <p>
            <Link href={`${w}/analytics`}>Analytics</Link> tracks comment → DM →
            booked → paid per automation and channel, and lets you A/B test two
            flows. Schedule content under{" "}
            <Link href={`${w}/calendar`}>Content</Link> and publish a{" "}
            <Link href={`${w}/bio`}>link-in-bio</Link> page.
          </p>
        </div>
      </section>
    </>
  );
}
