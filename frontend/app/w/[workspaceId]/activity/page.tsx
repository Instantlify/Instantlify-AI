"use client";

import { useEffect, useState } from "react";
import { api, message, type Audit, type Page } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { ActivityList } from "@/components/activity";
import { Empty, ErrorNotice, PageHeading, Panel } from "@/components/ui";

export default function ActivityPage() {
  const { prefix, manager } = useWorkspace();
  const [events, setEvents] = useState<Audit[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!manager) return;
    const controller = new AbortController();
    api<Page<Audit>>(`${prefix}/audit/`, "GET", undefined, controller.signal)
      .then((page) => setEvents(page.results))
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, [prefix, manager]);
  return (
    <>
      <PageHeading eyebrow="Audit log" title="Every change, accounted for." />
      <ErrorNotice error={error} />
      <Panel title="Workspace audit log" aside="Latest 50 events">
        {manager ? (
          <ActivityList events={events} />
        ) : (
          <Empty>
            Only owners and admins can view the workspace audit log.
          </Empty>
        )}
      </Panel>
    </>
  );
}
