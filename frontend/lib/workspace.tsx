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
  /** Channel connection chosen in the account switcher; null shows every account. */
  activeAccount: string | null;
  setActiveAccount: (connectionId: string | null) => void;
};

const accountKey = (workspaceId: string) => `nemio:account:${workspaceId}`;

function storedAccount(workspaceId: string) {
  try {
    return localStorage.getItem(accountKey(workspaceId));
  } catch {
    return null;
  }
}

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
  // The selection is per workspace and per browser: a convenience, not shared state.
  const [selection, setSelection] = useState(() => ({
    workspaceId,
    account: storedAccount(workspaceId),
  }));
  const activeAccount =
    selection.workspaceId === workspaceId
      ? selection.account
      : storedAccount(workspaceId);
  const setActiveAccount = useCallback(
    (account: string | null) => {
      setSelection({ workspaceId, account });
      try {
        if (account) localStorage.setItem(accountKey(workspaceId), account);
        else localStorage.removeItem(accountKey(workspaceId));
      } catch {
        // Storage may be unavailable; the choice then lasts for this visit only.
      }
    },
    [workspaceId],
  );
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
            activeAccount,
            setActiveAccount,
          }
        : null,
    [user, workspace, workspaces, refresh, activeAccount, setActiveAccount],
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
