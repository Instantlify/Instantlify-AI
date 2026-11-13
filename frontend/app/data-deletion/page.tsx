import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL } from "@/lib/legal";
import { LegalLinks } from "@/components/legal-links";
import { DeletionStatus } from "./status";

export const metadata: Metadata = {
  title: "Data deletion instructions · Instantlify",
  description:
    "Request deletion of Instantlify account information and Meta Platform Data, and check your deletion confirmation code.",
  robots: { index: false, follow: true },
};

export default function DataDeletionPage() {
  return (
    <main className="setup-screen">
      <article
        className="stack"
        style={{
          maxWidth: 760,
          margin: "0 auto",
          padding: 24,
          overflowWrap: "anywhere",
        }}
      >
        <h1>Data deletion</h1>
        <p>
          Effective {LEGAL.effectiveDate}. Instantlify is a product of{" "}
          {LEGAL.company}, {LEGAL.address}.
        </p>
        <p>
          You can request deletion of information held by Instantlify, including
          data received through Instagram, Facebook Messenger and WhatsApp,
          without signing in or keeping a paid subscription.
        </p>
        <DeletionStatus />
        <h2>1. Contact our privacy team</h2>
        <p>
          Email{" "}
          <a
            href={`mailto:${LEGAL.privacyEmail}?subject=Instantlify%20data%20deletion%20request`}
          >
            {LEGAL.privacyEmail}
          </a>{" "}
          with the subject “Instantlify data deletion request”. You can also
          contact{" "}
          <a href={`tel:${LEGAL.supportPhoneHref}`}>{LEGAL.supportPhone}</a> for
          assistance.
        </p>
        <ul>
          <li>
            Tell us which account, workspace, business or connected Meta account
            is involved and what data you want deleted.
          </li>
          <li>
            If you messaged a business, identify that business and the channel
            or handle you used. You can contact the business directly or ask us
            to help coordinate the request.
          </li>
          <li>
            Include an existing deletion confirmation code if you have one. We
            may request reasonable proof that you own the data or are authorized
            to act for the account.
          </li>
          <li>
            Never send passwords, access tokens, one-time codes or full
            payment-card details.
          </li>
        </ul>
        <h2>2. Request deletion through Meta</h2>
        <p>
          In Facebook or Instagram, open Settings and find Apps and Websites or
          Business Integrations, as applicable. Select Instantlify and use the
          removal or deletion-request option offered by Meta. Menu names and
          available options vary by account and Meta product.
        </p>
        <p>
          Removing a connection revokes access; it does not by itself confirm
          deletion of previously stored data. When Meta sends a valid
          data-deletion callback, we issue a confirmation code and a link to
          this page. Access tokens for identified accounts are removed and the
          erasure request is processed. The status remains pending or under
          review until the applicable erasure is complete or verified.
        </p>
        <p>
          If Meta does not offer a deletion option, the account was connected
          manually, or its identifier cannot be safely matched, use the email
          route above. Requests are still available to you.
        </p>
        <h2>3. Workspace and account deletion</h2>
        <p>
          Workspace owners can export information or request permanent workspace
          deletion under Settings → Data &amp; privacy. Confirm your password
          and workspace name. The app may require cancellation of an active
          subscription before deleting the entire workspace; that does not
          prevent a separate personal-data or Meta-data erasure request.
        </p>
        <p>
          For deletion of your Instantlify sign-in account, contact the privacy
          team. We will verify ownership and address workspaces, team
          memberships and any records that must lawfully be retained.
        </p>
        <h2>4. What is erased and what may remain</h2>
        <p>
          Depending on the verified scope, erasure includes connected-account
          identifiers and credentials, related messages, attachments, comments,
          delivery/event records, contact information and derived data held by
          Instantlify. Shared contacts, independent records or payment-related
          records may require a separate review so we do not erase another
          person&apos;s data or records that must lawfully be kept.
        </p>
        <p>
          We handle requests promptly and within applicable legal deadlines, and
          explain verification needs, delays or lawful exceptions. Minimal
          request/audit records and necessary accounting, fraud-prevention or
          legal records may remain with restricted use. Access-restricted
          backups expire according to their rotation; applicable deletion
          requests must be reapplied after restoration.
        </p>
        <p>
          Deleting data from Instantlify does not delete your Meta account or
          messages held by Meta, the business or another independent service.
          Where appropriate, we coordinate with relevant businesses and
          providers about copies they hold.
        </p>
        <p>
          Read our <Link href="/privacy/">privacy policy</Link> and{" "}
          <Link href="/terms/">terms and conditions</Link> for further
          information.
        </p>
        <LegalLinks />
      </article>
    </main>
  );
}
