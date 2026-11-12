"use client";

import { useCallback, useEffect, useState } from "react";
import { api, message } from "@/lib/api";
import { useConfirmation } from "./confirmation-provider";
import styles from "./device-sessions.module.css";

type Device = {
  id: string;
  device: string;
  ip_address: string | null;
  last_activity: string;
  expires_at: string;
  current: boolean;
};

export function DeviceSessions() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const confirm = useConfirmation();
  const refresh = useCallback(async () => {
    try {
      const result = await api<{ results: Device[] }>("/api/auth/sessions/");
      setDevices(Array.isArray(result.results) ? result.results : []);
      setError("");
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    queueMicrotask(() => void refresh());
  }, [refresh]);

  async function revoke(device?: Device) {
    if (
      busy ||
      !(await confirm(
        device
          ? `Sign out ${device.device}${device.current ? " (this device)" : ""}?`
          : "Sign out everywhere, including this device?",
        { title: "End sessions", confirmLabel: "Sign out", destructive: true },
      ))
    )
      return;
    setBusy(true);
    try {
      await api(
        device
          ? `/api/auth/sessions/${device.id}/`
          : "/api/auth/sessions/revoke-all/",
        device ? "DELETE" : "POST",
      );
      if (!device || device.current) {
        window.dispatchEvent(
          new CustomEvent("instantlify:session-changed", {
            detail: { action: "logout" },
          }),
        );
        window.location.assign(new URL("/auth/", window.location.origin).href);
      } else await refresh();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-card" aria-label="Devices and sessions">
      <div className="settings-card-header">
        <div>
          <h2 className="card-title">Devices and sessions</h2>
          <p className="card-subtitle">
            Sessions end after one hour without activity. Sign out a device you
            no longer use.
          </p>
        </div>
        <button
          className="text-button"
          disabled={loading || busy}
          onClick={() => void refresh()}
        >
          Refresh devices
        </button>
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">Loading devices…</p>
      ) : (
        !devices.length && <p>No active browser sessions.</p>
      )}
      <ul className={styles.list}>
        {devices.map((device) => (
          <li key={device.id}>
            <div>
              <strong>{device.device}</strong>{" "}
              {device.current && <span className="badge">This device</span>}
              <p>
                {device.ip_address || "IP unavailable"} · Last active{" "}
                {new Date(device.last_activity).toLocaleString()}
              </p>
              <p>
                Expires {new Date(device.expires_at).toLocaleString()} unless
                you stay active.
              </p>
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() => void revoke(device)}
              aria-label={`Sign out ${device.device}${device.current ? " (this device)" : ""}`}
            >
              Sign out device
            </button>
          </li>
        ))}
      </ul>
      <div className="settings-card-footer justify-end">
        <button
          className="button"
          disabled={busy || loading}
          onClick={() => void revoke()}
        >
          Sign out everywhere
        </button>
      </div>
    </section>
  );
}
