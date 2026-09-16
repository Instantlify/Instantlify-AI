"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError, message, type User, type Workspace } from "@/lib/api";
import { loadWorkspaces, WorkspaceProvider } from "@/lib/workspace";
import { Shell, Brand } from "@/components/shell";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<User>("/api/auth/me/", "GET", undefined, controller.signal),
      loadWorkspaces(controller.signal),
    ])
      .then(([me, all]) => {
        if (controller.signal.aborted) return;
        if (!all.some((item) => item.id === workspaceId)) {
          router.replace("/");
          return;
        }
        setUser(me);
        setWorkspaces(all);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && [401, 403].includes(err.status)) {
          router.replace("/");
          return;
        }
        setError(message(err));
      });
    return () => controller.abort();
  }, [workspaceId, router]);
  if (!user || !workspaces)
    return (
      <div className="loading-screen">
        <Brand />
        <p>{error || "Opening your workspace…"}</p>
      </div>
    );
  return (
    <WorkspaceProvider
      user={user}
      workspaceId={workspaceId}
      initialWorkspaces={workspaces}
    >
      <Shell>{children}</Shell>
    </WorkspaceProvider>
  );
}
