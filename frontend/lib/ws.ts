"use client";

import { useEffect, useRef } from "react";

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]"]);

function socketUrl(workspaceId: string) {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  let base =
    configured ||
    `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  try {
    // Session cookies are per host: when both sides are loopback aliases, use the
    // one the browser is on so the socket is authenticated.
    const url = new URL(base);
    if (
      LOOPBACK.has(url.hostname) &&
      LOOPBACK.has(window.location.hostname) &&
      url.hostname !== window.location.hostname
    ) {
      url.hostname = window.location.hostname;
      base = url.toString();
    }
  } catch {
    // Keep the configured value as-is.
  }
  return `${base.replace(/\/$/, "")}/ws/workspaces/${workspaceId}/`;
}

/**
 * Live "something changed" hints for a workspace. The server never pushes
 * customer data; on each hint the caller refetches through the authorized API.
 * Reconnects with backoff; polling in the caller remains the safety net.
 */
export function useWorkspaceSocket(
  workspaceId: string,
  onRefresh: () => void,
  onStatus?: (connected: boolean) => void,
) {
  const refresh = useRef(onRefresh);
  const status = useRef(onStatus);
  useEffect(() => {
    refresh.current = onRefresh;
    status.current = onStatus;
  });
  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let attempts = 0;
    let closed = false;
    function connect() {
      try {
        socket = new WebSocket(socketUrl(workspaceId));
      } catch {
        return;
      }
      socket.onopen = () => {
        attempts = 0;
        status.current?.(true);
      };
      socket.onmessage = (event) => {
        try {
          if (JSON.parse(event.data).type === "refresh") refresh.current();
        } catch {
          // Ignore malformed frames.
        }
      };
      socket.onclose = () => {
        status.current?.(false);
        if (closed) return;
        attempts += 1;
        timer = window.setTimeout(
          connect,
          Math.min(30000, 1000 * 2 ** attempts),
        );
      };
      socket.onerror = () => socket?.close();
    }
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [workspaceId]);
}
