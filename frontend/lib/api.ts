export type User = { id: number; name: string; email: string };
export type Workspace = {
  id: string;
  name: string;
  role: "owner" | "admin" | "agent";
  created_at: string;
};
export type Member = { id: string; name: string; email: string; role: string };
export type Invitation = {
  id: string;
  email: string;
  role: "admin" | "agent";
  expires_at: string;
  accept_url?: string;
};
export type Audit = { id: string; action: string; created_at: string };
export type Connection = {
  id: string;
  provider: string;
  display_name: string;
  is_test: boolean;
};
export type Status = { checks: Record<string, boolean>; pending_jobs: number };
export type Page<T> = { results: T[]; count: number; next: string | null };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

function errorMessage(data: unknown): string {
  if (!data || typeof data !== "object")
    return "Something went wrong. Please try again.";
  return Object.entries(data)
    .map(
      ([key, value]) =>
        `${key === "detail" ? "" : `${key}: `}${Array.isArray(value) ? value.join(" ") : String(value)}`,
    )
    .join(" ");
}

export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (method !== "GET") {
    const csrf = await fetch("/api/auth/csrf/", {
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
    if (!csrf.ok)
      throw new ApiError(
        "Unable to establish a secure session. Please try again.",
        csrf.status,
      );
    headers["X-CSRFToken"] = (await csrf.json()).csrfToken;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: data ? JSON.stringify(data) : undefined,
    signal,
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({
    detail: "The service is temporarily unavailable. Please try again.",
  }));
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status);
  return payload as T;
}
