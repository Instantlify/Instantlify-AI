"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Bounded local editing history. Restoration includes triggers and account scope. */
export function useGraphHistory<T>(
  key: string,
  graph: T,
  restore: (graph: T) => void,
) {
  const history = useRef({ key: "", entries: [] as string[], index: -1 });
  const [availability, setAvailability] = useState({
    canUndo: false,
    canRedo: false,
  });
  const serialized = JSON.stringify(graph);
  const record = useCallback(() => {
    const state = history.current;
    if (!key) return;
    if (state.key !== key) {
      history.current = { key, entries: [serialized], index: 0 };
      setAvailability({ canUndo: false, canRedo: false });
      return;
    }
    if (state.entries[state.index] === serialized) return;
    state.entries = [
      ...state.entries.slice(0, state.index + 1),
      serialized,
    ].slice(-50);
    state.index = state.entries.length - 1;
    setAvailability({ canUndo: state.index > 0, canRedo: false });
  }, [key, serialized]);

  useEffect(() => {
    if (key && history.current.key !== key) {
      history.current = { key, entries: [serialized], index: 0 };
      queueMicrotask(() => setAvailability({ canUndo: false, canRedo: false }));
      return;
    }
    const timer = setTimeout(() => {
      record();
    }, 250);
    return () => clearTimeout(timer);
  }, [key, serialized, record]);

  const move = useCallback(
    (direction: number) => {
      record();
      const state = history.current;
      const index = state.index + direction;
      if (index < 0 || index >= state.entries.length) return;
      state.index = index;
      restore(JSON.parse(state.entries[index]) as T);
      setAvailability({
        canUndo: index > 0,
        canRedo: index < state.entries.length - 1,
      });
    },
    [record, restore],
  );

  const undo = useCallback(() => move(-1), [move]);
  const redo = useCallback(() => move(1), [move]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      if (
        (event.target as HTMLElement)?.closest(
          "input,textarea,select,[contenteditable=true]",
        )
      )
        return;
      if (event.key.toLowerCase() === "z" || event.key.toLowerCase() === "y") {
        event.preventDefault();
        if (event.shiftKey || event.key.toLowerCase() === "y") redo();
        else undo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  return { undo, redo, ...availability };
}
