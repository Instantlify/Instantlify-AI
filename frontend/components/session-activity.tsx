"use client";

import { useEffect } from "react";
import { api, ApiError } from "@/lib/api";

type SessionStatus = {
  authenticated: boolean;
  idle_timeout: number;
  remaining: number;
};
const CHANNEL = "instantlify-session";
const HEARTBEAT_MS = 30_000;

/** Background API polling never keeps an unattended browser signed in. */
export function SessionActivity() {
  useEffect(() => {
    let disposed = false;
    let active = false;
    let expiresAt = 0;
    let lastInteraction = 0;
    let lastSent = 0;
    let sending = false;
    let statusRequest = 0;
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    let activityTimer: ReturnType<typeof setTimeout> | undefined;
    const channel = new BroadcastChannel(CHANNEL);

    function redirect() {
      if (disposed) return;
      active = false;
      window.location.replace("/auth/?session=expired");
    }

    function schedule(deadline: number) {
      expiresAt = deadline;
      clearTimeout(expiryTimer);
      expiryTimer = setTimeout(
        () => void synchronize(true),
        Math.max(0, deadline - Date.now()),
      );
    }

    async function synchronize(expiring = false) {
      const request = ++statusRequest;
      try {
        const status = await api<SessionStatus>("/api/auth/session/");
        if (disposed || request !== statusRequest) return;
        if (status.authenticated && status.remaining > 0) {
          active = true;
          schedule(Date.now() + status.remaining * 1000);
        } else {
          if (active || expiring) redirect();
          active = false;
        }
      } catch {
        // The server remains authoritative when a browser is offline or asleep.
        if (expiring && request === statusRequest) redirect();
      }
    }

    async function renew() {
      activityTimer = undefined;
      if (!active || disposed || sending) return;
      if (Date.now() >= expiresAt) {
        await synchronize(true);
        return;
      }
      const inactiveFor = (Date.now() - lastInteraction) / 1000;
      if (inactiveFor > 60) return;
      sending = true;
      lastSent = Date.now();
      try {
        const status = await api<SessionStatus>("/api/auth/session/", "POST", {
          inactive_for: Math.max(0, inactiveFor),
        });
        if (disposed) return;
        if (!status.authenticated || status.remaining <= 0) {
          redirect();
          return;
        }
        schedule(Date.now() + status.remaining * 1000);
        channel.postMessage({ expiresAt });
      } catch (err) {
        if (err instanceof ApiError && [401, 403].includes(err.status))
          redirect();
      } finally {
        sending = false;
      }
    }

    function interaction(event: Event) {
      if (!event.isTrusted || document.visibilityState !== "visible" || !active)
        return;
      lastInteraction = Date.now();
      if (activityTimer !== undefined) return;
      const wait = Math.max(0, HEARTBEAT_MS - (Date.now() - lastSent));
      if (wait === 0) void renew();
      else activityTimer = setTimeout(() => void renew(), wait);
    }

    function visible() {
      // Returning to a tab checks expiry; focus alone is not user activity.
      if (document.visibilityState === "visible") void synchronize();
    }

    function sessionChanged() {
      void synchronize();
      channel.postMessage({ check: true });
    }

    channel.onmessage = (
      event: MessageEvent<{ expiresAt?: number; check?: boolean }>,
    ) => {
      if (event.data.check) void synchronize();
      else if (
        active &&
        typeof event.data.expiresAt === "number" &&
        event.data.expiresAt > expiresAt
      ) {
        schedule(event.data.expiresAt);
      }
    };
    const events = [
      "pointerdown",
      "pointermove",
      "keydown",
      "wheel",
      "touchstart",
    ];
    for (const event of events)
      window.addEventListener(event, interaction, { passive: true });
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("instantlify:session-changed", sessionChanged);
    void synchronize();

    return () => {
      disposed = true;
      clearTimeout(expiryTimer);
      clearTimeout(activityTimer);
      channel.close();
      for (const event of events)
        window.removeEventListener(event, interaction);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("instantlify:session-changed", sessionChanged);
    };
  }, []);

  return null;
}
