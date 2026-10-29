"use client";
import { useWorkspace } from "@/lib/workspace";
import { PageHeading } from "@/components/ui";
import { MyTickets } from "@/components/support-center";
export default function SupportPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeading eyebrow="Help & support" title="My tickets" />
      <MyTickets key={workspace.id} workspaceId={workspace.id} />
    </>
  );
}
