"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type PipelineStage = { id: string; label: string; color: string };

/** Mirrors backend apps/crm/stages.py; shown until the workspace's own list loads. */
export const DEFAULT_STAGES: PipelineStage[] = [
  { id: "new", label: "No stage", color: "#94a3b8" },
  { id: "qualified", label: "Qualified", color: "#6366f1" },
  { id: "interested", label: "Interested", color: "#f59e0b" },
  { id: "booked", label: "Booked", color: "#0ea5e9" },
  { id: "won", label: "Won", color: "#16a34a" },
  { id: "lost", label: "Lost", color: "#ef4444" },
];
/** Set by the platform itself (bookings, payments); renamable but not removable. */
export const SYSTEM_STAGES = new Set(["new", "booked", "won", "lost"]);

const cache = new Map<string, PipelineStage[]>();
const listeners = new Set<() => void>();

export function setPipelineStages(prefix: string, stages: PipelineStage[]) {
  cache.set(prefix, stages);
  listeners.forEach((listener) => listener());
}

/** The workspace's ordered stages, shared by every screen and refreshed on save. */
export function usePipelineStages(prefix: string): PipelineStage[] {
  const [, rerender] = useState(0);
  useEffect(() => {
    const listener = () => rerender((n) => n + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  useEffect(() => {
    if (cache.has(prefix)) return;
    const controller = new AbortController();
    api<{ stages: PipelineStage[] }>(
      `${prefix}/pipeline-stages/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((result) => setPipelineStages(prefix, result.stages))
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix]);
  return cache.get(prefix) ?? DEFAULT_STAGES;
}

export const stageLabelFor = (stages: PipelineStage[], id: string) =>
  stages.find((stage) => stage.id === (id || "new"))?.label ?? id;
