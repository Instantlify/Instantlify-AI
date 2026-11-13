import type { Metadata } from "next";
import Link from "next/link";
import { LegalLinks } from "@/components/legal-links";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy policy · Instantlify",
  description:
    "How Instantlify and its operator SKY INNOVA SERVICES (PRIVATE) LIMITED collect, use, share, retain and delete personal information and Meta Platform Data.",
};

const ARTICLE = { maxWidth: 760, margin: "0 auto", padding: 24 } as const;

// Describes what Instantlify actually collects and does. Company details live in
// lib/legal.ts. Have this reviewed by a lawyer for your jurisdiction before launch.
export default function PrivacyPage() {
  return (
    <main className="setup-screen">
      <article className="stack" style={ARTICLE}>
        <h1>Privacy policy</h1>
        <p className="muted-text">
          Effective {LEGAL.effectiveDate}. Instantlify is a product operated by{" "}
          {LEGAL.company}, {LEGAL.address}.
        </p>

        <p>
          Instantlify is a platform businesses use to manage customer
          conversations on Instagram, Facebook Messenger, WhatsApp, Telegram and
          their own website, to automate replies (including with AI), and to
          keep a contact list, forms, link-in-bio pages and related tools. This
          policy explains what personal information we handle, why, who we share
          it with and the choices you have.
        </p>

        <h2>1. Our role</h2>
        <ul>
          <li>
            <strong>For account holders</strong> (people who sign up and use
            Instantlify for a business), we decide how account data is used: we
            are the controller of that data.
          </li>
          <li>
            <strong>For a business&rsquo;s customers</strong> (people who
            message a business, fill in its form, sign up on its link-in-bio
            page or use its website chat), the business decides what it collects
            and why. The business is the controller and Instantlify processes
            that data on its behalf and on its instructions. If you are one of
            those customers, please contact the business directly about your
            data; we will help it respond.
          </li>
        </ul>

        <h2>2. Information we collect</h2>
        <h3>Account and team information</h3>
        <ul>
          <li>
            Name, email address and password (stored only as a secure hash).
          </li>
          <li>
            If you sign in with Google: your name and verified email address
            from Google. We do not receive your Google password.
          </li>
          <li>
            Optional profile photo, your workspaces, team roles and access
            settings.
          </li>
          <li>
            A log of significant actions in a workspace (for example who changed
            settings, connected an account or deleted data), used for security
            and accountability.
          </li>
        </ul>

        <h3>Connected accounts and integrations</h3>
        <ul>
          <li>
            When you connect Instagram, Facebook Messenger, WhatsApp or
            Telegram: the account or page ID, display name and profile details
            the platform provides, and the access token it grants. Tokens are
            encrypted.
          </li>
          <li>
            When you connect other tools (for example Google Calendar or Sheets,
            Gmail, Outlook, Slack, Stripe, Mailchimp, Klaviyo, CRMs such as
            GoHighLevel, Attio, Airtable or Notion, voice or video providers):
            the credentials or tokens you provide, encrypted, and the settings
            you choose.
          </li>
        </ul>

        <h3>Content a business keeps in Instantlify</h3>
        <ul>
          <li>
            Contacts: names, social handles, profile photos, email addresses,
            phone numbers, tags, pipeline stage, custom fields, notes and
            AI-written contact summaries.
          </li>
          <li>
            Conversations: messages, comments, story replies, attachments, voice
            notes and their transcripts, and delivery status.
          </li>
          <li>
            Automations, AI agent settings and the knowledge you add (documents,
            text and imported web pages).
          </li>
          <li>
            Forms and their responses (including uploaded files and signatures),
            link-in-bio pages and signups, website chat settings, scheduled
            posts, tracking links and click counts.
          </li>
        </ul>

        <h3>Information from a business&rsquo;s customers</h3>
        <ul>
          <li>
            Messages they send and the profile name, handle and photo the
            platform shares with the business.
          </li>
          <li>
            Details they choose to give, such as an email address in a form or a
            signup, and their consent where a form asks for it.
          </li>
          <li>
            For website chat: a random visitor ID stored in their browser so the
            conversation continues on their next visit.
          </li>
        </ul>

        <h3>Payments</h3>
        <ul>
          <li>
            Subscriptions and AI credits are paid through Stripe. Stripe
            collects and stores card details; we receive the plan, subscription
            status, invoices and a record of AI credit purchases and usage.
          </li>
          <li>
            Payments a business takes from its own customers in chat go through
            that business&rsquo;s own Stripe account.
          </li>
        </ul>

        <h3>Technical and usage information</h3>
        <ul>
          <li>
            IP address and browser information, used to keep accounts secure,
            prevent abuse and limit request rates.
          </li>
          <li>
            On our public website: the pages visited, the referring page and
            campaign source, linked by a first-party session identifier (see
            Cookies). We do not use advertising trackers.
          </li>
          <li>Error reports when something breaks, so we can fix it.</li>
        </ul>

        <h3>Support, community and referrals</h3>
        <ul>
          <li>
            Support conversations and tickets, and posts you make in the
            community forum.
          </li>
          <li>
            If you join the affiliate program: your referral links and referral
            statistics, managed with our affiliate provider.
          </li>
        </ul>

        <h2>3. How we use information</h2>
        <ul>
          <li>
            To provide the service: deliver and receive messages, show
            conversations, run the automations and AI replies a business sets
            up, sync contacts to the tools it connects, host its forms and
            pages, and process payments.
          </li>
          <li>
            To secure the service, prevent fraud and abuse, and enforce our
            terms.
          </li>
          <li>
            To provide support and tell you about changes to the service or your
            account.
          </li>
          <li>To understand how the service is used and improve it.</li>
          <li>To meet legal, tax and accounting obligations.</li>
        </ul>
        <p>
          We do not sell personal information and we do not use a
          business&rsquo;s customer messages for advertising.
        </p>

        <h3>Legal grounds where applicable</h3>
        <p>
          Depending on the information and applicable law, processing is
          necessary to provide our contract with an account holder, follow a
          business customer&apos;s lawful instructions, maintain legitimate
          service/security interests, comply with legal obligations, or act on
          consent. Where processing relies on consent, it may be withdrawn
          without affecting processing already lawfully carried out.
        </p>
        <h2>4. AI features</h2>
        <p>
          When a business enables or configures AI features, the text needed for
          the task (for example the recent conversation, the relevant knowledge
          and the business&rsquo;s instructions) is sent to the AI provider the
          business selects, such as OpenAI, Anthropic, Google or xAI, to
          generate a reply, classify a message, summarize a contact or check a
          comment. Voice notes may be transcribed and voice replies generated
          with providers such as OpenAI, ElevenLabs, Inworld or MiniMax; avatar
          videos and phone calls use providers such as HeyGen, Vapi or Retell
          when a business configures them. Knowledge documents are converted
          into embeddings to find relevant passages. We do not use a
          business&rsquo;s content to train our own models. AI providers process
          data under their applicable service and data-processing terms. Our own
          support assistant may also send the questions you submit to our
          platform AI provider to answer using Instantlify support knowledge.
        </p>

        <h2>5. Meta Platform Data: Instagram, Facebook and WhatsApp</h2>
        <p>
          When an authorized business connects a Meta account, we receive only
          data available through the permissions it grants and the Meta products
          it uses. This may include professional account, Page, WhatsApp
          Business Account and phone-number identifiers; the authorizing Meta
          user identifier; account names, usernames and profile information;
          access tokens; messages, comments, story replies, attachments and
          delivery/read events; and authorized account/media statistics such as
          follower counts, reach, views and interactions. We do not ask for your
          Facebook, Instagram or WhatsApp password.
        </p>
        <p>
          We use this data to connect and maintain the selected account, display
          and respond to customer conversations, run the business&apos;s
          configured automations, moderate comments, publish content it
          schedules, and provide the analytics it enables. AI processing of
          relevant message content is described in section 4. Features operate
          only within available permissions and platform restrictions. We do not
          sell Meta Platform Data, provide it to data brokers, use it for
          targeted advertising, or use it to train general-purpose AI models. We
          do not combine one business&apos;s private conversations with another
          business&apos;s knowledge.
        </p>
        <p>
          You can revoke access through Meta&apos;s Apps and Websites or
          Business Integrations settings, as applicable, or disconnect the
          account in Instantlify. Revocation stops further access and removes
          the connected account&apos;s stored access tokens when we receive a
          valid revocation notification. Revoking access is different from
          requesting erasure of data already held. To request erasure, use
          Meta&apos;s deletion-request option where available, our{" "}
          <Link href="/data-deletion/">data-deletion instructions</Link>, or
          email{" "}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>. A
          Meta deletion request does not require an active subscription or
          cancellation of unrelated services. We verify the request, stop
          relevant access, and erase applicable data promptly, subject to
          limited lawful retention exceptions.
        </p>

        <h2>6. Who we share information with</h2>
        <p>We share personal information only as needed to run the service:</p>
        <ul>
          <li>
            Hosting, database and email delivery providers that run the service
            for us.
          </li>
          <li>Stripe, for payments.</li>
          <li>
            Messaging platforms (Meta for Instagram, Messenger and WhatsApp, and
            Telegram), to send and receive messages.
          </li>
          <li>
            The AI and media providers described above, when a business enables
            them.
          </li>
          <li>
            An error-reporting provider, with personal data removed where
            possible.
          </li>
          <li>Our affiliate program provider, for affiliates only.</li>
          <li>
            Tools a business connects (for example its CRM, email marketing,
            spreadsheet, calendar or webhook endpoints), at that
            business&rsquo;s direction.
          </li>
          <li>
            Authorities or others when the law requires it, or to protect the
            rights, safety and security of people and the service.
          </li>
          <li>
            A buyer or successor if the business is reorganized or sold, under
            this policy.
          </li>
        </ul>

        <h2>7. How long we keep information</h2>
        <ul>
          <li>
            The default retention job removes or redacts message text,
            attachments and similar payloads after {LEGAL.retentionDays} days. A
            business may have a different configured retention period. Valid
            deletion requests and applicable legal requirements can require
            earlier erasure.
          </li>
          <li>
            Generated voice files used to send a voice note are deleted within
            hours.
          </li>
          <li>Workspace exports are deleted one day after they are created.</li>
          <li>
            Account, contact and workspace data is kept while the account is
            active, until the owner deletes it or the workspace is deleted.
          </li>
          <li>
            Billing and tax records are kept for as long as the law requires.
            Backups are access-restricted and expire through the configured
            backup rotation. Deletion from active systems does not mean every
            backup copy is immediately overwritten; any restored data must have
            applicable deletion requests reapplied before ordinary use. Data
            retained for a legal obligation is restricted to that purpose.
          </li>
        </ul>

        <h2>8. Security</h2>
        <p>
          Data travels over encrypted connections. Access tokens, integration
          credentials, message content and attachments are encrypted at rest.
          Passwords and API tokens are stored only as hashes. Each
          workspace&rsquo;s data is isolated from every other workspace, through
          tenant-scoped access controls. Team access is controlled by roles and
          optional per-account and per-section limits, and staff access requires
          multi-factor authentication and is logged. No system is perfectly
          secure, but we work to protect your information and will notify you of
          a breach as the law requires.
        </p>

        <h2>9. Your choices and rights</h2>
        <ul>
          <li>
            <strong>Access and export:</strong> workspace owners can download
            all workspace data in Settings → Data &amp; privacy.
          </li>
          <li>
            <strong>Deletion:</strong> owners can permanently delete a workspace
            in the same place. You can ask us to delete your account.
          </li>
          <li>
            <strong>Correction:</strong> you can update your profile and
            workspace information in the app.
          </li>
          <li>
            <strong>Connected accounts:</strong> disconnect a channel or
            integration at any time, or remove Instantlify from your Instagram
            or Facebook settings.
          </li>
          <li>
            Depending on where you live, you may also have the right to object
            to or restrict processing, to data portability, to withdraw consent,
            and to complain to your data protection authority.
          </li>
        </ul>
        <p>
          To make a request, email <strong>{LEGAL.privacyEmail}</strong>. If you
          are a customer of a business that uses Instantlify, contact that
          business for requests about its independent records. You may also
          contact us directly, including for Meta Platform Data; we will verify
          the request and coordinate with the business where needed. We may ask
          for the relevant account/workspace, your relationship to it and
          reasonable proof of authority, but never your password, access token
          or full payment-card details. We respond promptly and within
          applicable legal deadlines, and explain any lawful exception or
          additional verification needed.
        </p>

        <h2>10. Cookies and browser storage</h2>
        <ul>
          <li>
            Essential cookies keep you signed in and protect forms against
            cross-site attacks.
          </li>
          <li>
            On our public website, a first-party <code>nm_sid</code> cookie
            links page views in a visit so we can measure which pages lead to
            signups. It is not shared with advertisers.
          </li>
          <li>
            Browser storage remembers preferences such as your language, and the
            website chat visitor ID described above.
          </li>
        </ul>

        <h2>11. Children</h2>
        <p>
          Instantlify is a business tool and is not directed at children.
          Account holders must be at least 18 years old or otherwise have legal
          capacity to enter a business contract. If a child&apos;s information
          has been submitted to a business through our service, a parent or
          guardian may contact that business or our privacy contact to request
          appropriate action.
        </p>

        <h2>12. International transfers</h2>
        <p>
          We and our providers may process information in countries other than
          yours. Applicable safeguards depend on the destination, provider and
          law. Where required, we use legally recognized safeguards or another
          lawful transfer mechanism. Contact our privacy address for information
          about the providers and safeguards applicable to your data.
        </p>

        <h2>13. Changes</h2>
        <p>
          We will update this policy as the service changes and post the new
          version here with its effective date. For significant changes we will
          also notify account holders.
        </p>

        <h2>14. Contact</h2>
        <p>
          {LEGAL.company}, {LEGAL.address}. Privacy: {LEGAL.privacyEmail}.
          Support:{" "}
          <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>.
          Telephone:{" "}
          <a href={`tel:${LEGAL.supportPhoneHref}`}>{LEGAL.supportPhone}</a>.
          See also our <Link href="/terms/">terms of service</Link>.
        </p>
        <LegalLinks />
      </article>
    </main>
  );
}
