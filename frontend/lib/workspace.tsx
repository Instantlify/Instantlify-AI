"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, type Page, type User, type Workspace } from "./api";

export type WorkspaceContextValue = {
  user: User;
  workspace: Workspace;
  workspaces: Workspace[];
  /** Owners and admins manage settings; agents only work conversations. */
  manager: boolean;
  prefix: string;
  refresh: () => Promise<void>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export async function loadWorkspaces(signal?: AbortSignal) {
  const page = await api<Page<Workspace>>(
    "/api/workspaces/",
    "GET",
    undefined,
    signal,
  );
  return page.results;
}

export function WorkspaceProvider({
  user,
  workspaceId,
  initialWorkspaces,
  children,
}: {
  user: User;
  workspaceId: string;
  initialWorkspaces: Workspace[];
  children: ReactNode;
}) {
  const [workspaces, setWorkspaces] = useState(initialWorkspaces);
  const refresh = useCallback(async () => {
    setWorkspaces(await loadWorkspaces());
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("nemio:last-workspace", workspaceId);
    } catch {
      // Storage may be unavailable; the URL is the source of truth anyway.
    }
  }, [workspaceId]);
  const workspace = workspaces.find((item) => item.id === workspaceId);
  const value = useMemo(
    () =>
      workspace
        ? {
            user,
            workspace,
            workspaces,
            manager: workspace.role !== "agent",
            prefix: `/api/workspaces/${workspace.id}`,
            refresh,
          }
        : null,
    [user, workspace, workspaces, refresh],
  );
  if (!value) return null;
  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside a workspace");
  return value;
}

export function lastWorkspaceId() {
  try {
    return localStorage.getItem("nemio:last-workspace");
  } catch {
    return null;
  }
}
