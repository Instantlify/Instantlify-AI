import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy policy · Nemio" };

// DRAFT: written to satisfy Meta App Review's requirements; have it reviewed by a
// lawyer and fill in the company details before launch.
export default function PrivacyPage() {
  return (
    <main className="setup-screen">
      <article
        className="stack"
        style={{ maxWidth: 720, margin: "0 auto", padding: 24 }}
      >
        <h1>Privacy policy</h1>
        <p className="muted-text">
          Last updated: [date]. Operated by [company name, address].
        </p>
        <h2>What Nemio does</h2>
        <p>
          Nemio lets businesses manage customer conversations from Instagram,
          Facebook Messenger, WhatsApp, Telegram and their website, automate
          replies, and keep a contact list.
        </p>
        <h2>Information we process</h2>
        <ul>
          <li>
            <strong>Account holders:</strong> name, email, password hash,
            workspace settings and billing details (processed by Stripe).
          </li>
          <li>
            <strong>Connected business accounts:</strong> account IDs, profile
            name and access tokens granted through Meta or other platforms,
            stored encrypted.
          </li>
          <li>
            <strong>People who message a business:</strong> the messages,
            profile name and handle the platform provides, and any details they
            share (for example an email address). The business decides how this
            is used and is the controller of that data; Nemio processes it on
            the business&rsquo;s behalf.
          </li>
        </ul>
        <h2>How we use it</h2>
        <p>
          To deliver and receive messages, run the automations and AI replies a
          business configures, show conversations in its inbox, and operate,
          secure and bill the service. We do not sell personal data or use
          customer messages to advertise.
        </p>
        <h2>AI processing</h2>
        <p>
          When a business turns on AI features, relevant message text is sent to
          the AI provider it selects (such as OpenAI, Anthropic, Google or xAI)
          to generate a reply. Providers process it under their own terms.
        </p>
        <h2>Retention and deletion</h2>
        <p>
          Message content is kept for the retention period the service is
          configured with and then removed. Owners can export or delete their
          workspace at any time. Removing the app from Instagram or Facebook
          disconnects the account and deletes its tokens. See{" "}
          <Link href="/data-deletion/">data deletion</Link>.
        </p>
        <h2>Security</h2>
        <p>
          Data is encrypted in transit, credentials and message content are
          encrypted at rest, and each workspace&rsquo;s data is isolated from
          others.
        </p>
        <h2>Contact</h2>
        <p>Questions or requests: [privacy contact email].</p>
      </article>
    </main>
  );
}
