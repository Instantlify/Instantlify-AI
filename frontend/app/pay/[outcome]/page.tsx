"use client";

import { useParams } from "next/navigation";
import { Check, X } from "lucide-react";

/** Return pages for in-chat checkouts: /pay/thanks/, /pay/cancelled/, /pay/test/<id>/. */
export default function PaymentOutcomePage() {
  const { outcome } = useParams<{ outcome: string }>();
  const paid = outcome === "thanks";
  const test = outcome === "test";
  return (
    <main className="setup-screen">
      <section className="setup-card" style={{ textAlign: "center" }}>
        <span className="section-icon">
          {paid ? <Check size={26} /> : <X size={26} />}
        </span>
        <h1>
          {paid
            ? "Thank you! Your payment went through."
            : test
              ? "Local test checkout"
              : "Payment cancelled."}
        </h1>
        <p>
          {paid
            ? "You can close this tab and head back to the chat — we’ve got it from here."
            : test
              ? "This workspace uses the local test payment integration. No real checkout was created; mark the payment as paid from the backend to simulate a webhook."
              : "No charge was made. You can return to the conversation and try again whenever you like."}
        </p>
      </section>
    </main>
  );
}
