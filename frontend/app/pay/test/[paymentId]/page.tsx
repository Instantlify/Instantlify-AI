"use client";

import { Check } from "lucide-react";

export default function TestCheckoutPage() {
  return (
    <main className="setup-screen">
      <section className="setup-card" style={{ textAlign: "center" }}>
        <span className="section-icon">
          <Check size={26} />
        </span>
        <h1>Local test checkout</h1>
        <p>
          This workspace uses the local test payment integration, so no real
          checkout exists. In production this link opens Stripe Checkout on the
          business’s own account.
        </p>
      </section>
    </main>
  );
}
