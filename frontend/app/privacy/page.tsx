import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = { title: "Privacy policy · Nemio" };

const ARTICLE = { maxWidth: 760, margin: "0 auto", padding: 24 } as const;

// Describes what Nemio actually collects and does. Company details live in
// lib/legal.ts. Have this reviewed by a lawyer for your jurisdiction before launch.
export default function PrivacyPage() {
  return (
    <main className="setup-screen">
      <article className="stack" style={ARTICLE}>
        <h1>Privacy policy</h1>
        <p className="muted-text">
          Effective {LEGAL.effectiveDate}. {LEGAL.company}, {LEGAL.address}.
        </p>

        <p>
          Nemio is a platform businesses use to manage customer conversations on
          Instagram, Facebook Messenger, WhatsApp, Telegram and their own
          website, to automate replies (including with AI), and to keep a
          contact list, forms, link-in-bio pages and related tools. This policy
          explains what personal information we handle, why, who we share it
          with and the choices you have.
        </p>

        <h2>1. Our role</h2>
        <ul>
          <li>
            <strong>For account holders</strong> (people who sign up and use
            Nemio for a business), we decide how account data is used: we are
            the controller of that data.
          </li>
          <li>
            <strong>For a business&rsquo;s customers</strong> (people who
            message a business, fill in its form, sign up on its link-in-bio
            page or use its website chat), the business decides what it collects
            and why. The business is the controller and Nemio processes that
            data on its behalf and on its instructions. If you are one of those
            customers, please contact the business directly about your data; we
            will help it respond.
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

        <h3>Content a business keeps in Nemio</h3>
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

        <h2>4. AI features</h2>
        <p>
          AI features run only when a business turns them on. When they do, the
          text needed for the task (for example the recent conversation, the
          relevant knowledge and the business&rsquo;s instructions) is sent to
          the AI provider the business selects, such as OpenAI, Anthropic,
          Google or xAI, to generate a reply, classify a message, summarize a
          contact or check a comment. Voice notes may be transcribed and voice
          replies generated with providers such as OpenAI, ElevenLabs, Inworld
          or MiniMax; avatar videos and phone calls use providers such as
          HeyGen, Vapi or Retell when a business configures them. Knowledge
          documents are converted into embeddings to find relevant passages. We
          do not use a business&rsquo;s content to train our own models. AI
          providers process data under their own terms.
        </p>

        <h2>5. Meta platform data</h2>
        <p>
          Through Instagram and Facebook we access only what a business
          authorizes: its connected professional account or page, the messages
          and comments people send to it, and the profile details Meta provides
          about those people. We use this solely to show conversations to the
          business, reply on its behalf and run the automations it sets up. We
          do not sell this data or use it for advertising. When someone removes
          Nemio from their Instagram or Facebook settings, we disconnect the
          account and delete its access tokens; see{" "}
          <Link href="/data-deletion/">data deletion</Link>.
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
            Message text, attachments and similar delivery records are removed
            after {LEGAL.retentionDays} days by default.
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
            Backups are overwritten on a rolling basis.
          </li>
        </ul>

        <h2>8. Security</h2>
        <p>
          Data travels over encrypted connections. Access tokens, integration
          credentials, message content and attachments are encrypted at rest.
          Passwords and API tokens are stored only as hashes. Each
          workspace&rsquo;s data is isolated from every other workspace,
          including at the database level. Team access is controlled by roles
          and optional per-account and per-section limits, and staff access
          requires multi-factor authentication and is logged. No system is
          perfectly secure, but we work to protect your information and will
          notify you of a breach as the law requires.
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
            integration at any time, or remove Nemio from your Instagram or
            Facebook settings.
          </li>
          <li>
            Depending on where you live, you may also have the right to object
            to or restrict processing, to data portability, to withdraw consent,
            and to complain to your data protection authority.
          </li>
        </ul>
        <p>
          To make a request, email <strong>{LEGAL.privacyEmail}</strong>. If you
          are a customer of a business that uses Nemio, contact that business
          first; we will help it respond.
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
          Nemio is a business tool and is not directed at children. Account
          holders must be at least 16 years old (or the age of digital consent
          where they live).
        </p>

        <h2>12. International transfers</h2>
        <p>
          We and our providers may process information in countries other than
          yours. Where required, we use appropriate safeguards such as standard
          contractual clauses.
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
          Support: {LEGAL.supportEmail}. See also our{" "}
          <Link href="/terms/">terms of service</Link>.
        </p>
      </article>
    </main>
  );
}
