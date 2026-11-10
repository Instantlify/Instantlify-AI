"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type CustomFieldType =
  "text" | "number" | "date" | "select" | "url" | "email";
export type CustomFieldDef = {
  key: string;
  label: string;
  type: CustomFieldType;
  options?: string[];
};

export const FIELD_TYPES: { value: CustomFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "select", label: "Dropdown" },
  { value: "url", label: "Website" },
  { value: "email", label: "Email" },
];

const cache = new Map<string, CustomFieldDef[]>();
const listeners = new Set<() => void>();

export function setCustomFields(prefix: string, fields: CustomFieldDef[]) {
  cache.set(prefix, fields);
  listeners.forEach((listener) => listener());
}

/** The workspace's typed contact field definitions, shared across screens. */
export function useCustomFields(prefix: string): CustomFieldDef[] {
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
    api<{ fields: CustomFieldDef[] }>(
      `${prefix}/custom-fields/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((result) => setCustomFields(prefix, result.fields))
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix]);
  return cache.get(prefix) ?? [];
}
