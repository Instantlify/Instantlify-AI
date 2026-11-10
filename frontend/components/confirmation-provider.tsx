"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { Modal } from "./ui";

type Options = { title?: string; confirmLabel?: string; destructive?: boolean };
type Confirm = (message: string, options?: Options) => Promise<boolean>;
type Request = {
  message: string;
  options: Options;
  resolve: (approved: boolean) => void;
};
const ConfirmationContext = createContext<Confirm | null>(null);

function actionFor(message: string) {
  if (/discard/i.test(message)) return "Discard changes";
  if (/disconnect/i.test(message)) return "Disconnect";
  if (/unlist/i.test(message)) return "Unlist";
  if (/revoke/i.test(message)) return "Revoke access";
  if (/leave this workspace/i.test(message)) return "Leave workspace";
  if (/cancel this scheduled post/i.test(message))
    return "Cancel scheduled post";
  if (/delete/i.test(message)) return "Delete";
  if (/remove/i.test(message)) return "Remove";
  if (/promote/i.test(message)) return "Promote winner";
  return "Continue";
}

export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Request | null>(null);
  const active = useRef<Request | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  const finish = useCallback((approved: boolean) => {
    const request = active.current;
    active.current = null;
    setPending(null);
    request?.resolve(approved);
  }, []);
  const confirm = useCallback<Confirm>((message, options = {}) => {
    if (active.current) return Promise.resolve(false);
    return new Promise<boolean>((resolve) => {
      const request = { message, options, resolve };
      active.current = request;
      setPending(request);
    });
  }, []);
  useEffect(() => {
    queueMicrotask(() => finish(false));
  }, [pathname, finish]);
  useEffect(
    () => () => {
      active.current?.resolve(false);
      active.current = null;
    },
    [],
  );
  const label = pending
    ? pending.options.confirmLabel || actionFor(pending.message)
    : "Continue";
  return (
    <ConfirmationContext.Provider value={confirm}>
      {children}
      {pending && (
        <Modal
          role="alertdialog"
          descriptionId="confirmation-description"
          initialFocusRef={cancelRef}
          title={pending.options.title || `${label}?`}
          onClose={() => finish(false)}
        >
          <div className="confirmation-brand">
            <AlertTriangle size={18} aria-hidden="true" /> Instantlify
          </div>
          <p id="confirmation-description" className="confirmation-message">
            {pending.message}
          </p>
          <div className="confirmation-actions">
            <button
              type="button"
              className="button secondary"
              ref={cancelRef}
              onClick={() => finish(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`button ${pending.options.destructive === false || label === "Promote winner" ? "primary" : "danger"}`}
              onClick={() => finish(true)}
            >
              {label}
            </button>
          </div>
        </Modal>
      )}
    </ConfirmationContext.Provider>
  );
}

export function useConfirmation() {
  const confirm = useContext(ConfirmationContext);
  if (!confirm) throw new Error("ConfirmationProvider is required.");
  return confirm;
}
