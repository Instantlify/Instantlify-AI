import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Terms of service · Nemio" };

// DRAFT: have this reviewed by a lawyer and fill in the company details before launch.
export default function TermsPage() {
  return (
    <main className="setup-screen">
      <article
        className="stack"
        style={{ maxWidth: 720, margin: "0 auto", padding: 24 }}
      >
        <h1>Terms of service</h1>
        <p className="muted-text">
          Last updated: [date]. Provided by [company name].
        </p>
        <h2>Using Nemio</h2>
        <p>
          You must have the right to connect each account you add, and you are
          responsible for the content you send and the automations you run.
          Follow the rules of each messaging platform, including Meta&rsquo;s
          Platform Terms and messaging policies, and get any consent the law
          requires before messaging people.
        </p>
        <h2>Prohibited use</h2>
        <p>
          No spam, unsolicited bulk messaging, harassment, illegal content, or
          attempts to break, overload or access other workspaces.
        </p>
        <h2>Plans and billing</h2>
        <p>
          Paid plans and AI credits are billed through Stripe as shown at
          checkout. You can cancel any time; access continues to the end of the
          paid period.
        </p>
        <h2>Your data</h2>
        <p>
          You keep ownership of your workspace data. Our handling of personal
          data is described in the <Link href="/privacy/">privacy policy</Link>.
        </p>
        <h2>Availability and liability</h2>
        <p>
          The service depends on third-party platforms that may change or limit
          access. To the extent the law allows, the service is provided as is
          and our liability is limited to the fees you paid in the previous 12
          months.
        </p>
        <h2>Contact</h2>
        <p>[support contact email]</p>
      </article>
    </main>
  );
}
