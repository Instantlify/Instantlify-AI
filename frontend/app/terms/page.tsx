import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = { title: "Terms of service · Instantlify" };

const ARTICLE = { maxWidth: 760, margin: "0 auto", padding: 24 } as const;

// Company details live in lib/legal.ts. Have this reviewed by a lawyer for your
// jurisdiction before launch.
export default function TermsPage() {
  return (
    <main className="setup-screen">
      <article className="stack" style={ARTICLE}>
        <h1>Terms of service</h1>
        <p className="muted-text">
          Effective {LEGAL.effectiveDate}. These terms are an agreement between
          you and {LEGAL.company} ({LEGAL.address}).
        </p>

        <h2>1. Accepting these terms</h2>
        <p>
          By creating an account or using Instantlify you agree to these terms
          and to our <Link href="/privacy/">privacy policy</Link>. If you use
          Instantlify for a company, you confirm you can bind that company, and
          &ldquo;you&rdquo; means the company.
        </p>

        <h2>2. The service</h2>
        <p>
          Instantlify lets you manage conversations from Instagram, Facebook
          Messenger, WhatsApp, Telegram and your website in one inbox, build
          automations (including AI replies and AI agents), keep contacts in a
          CRM, run broadcasts, and publish forms, link-in-bio pages, tracking
          links and a website chat widget. Features depend on your plan and may
          change over time.
        </p>

        <h2>3. Accounts and teams</h2>
        <ul>
          <li>
            Keep your sign-in details secure and tell us about any unauthorized
            use.
          </li>
          <li>
            The workspace owner controls the workspace, its data and its team.
            You are responsible for what your teammates, automations and
            connected apps do in your workspace.
          </li>
          <li>
            You must be at least 16 and give accurate account information.
          </li>
        </ul>

        <h2>4. Your responsibilities when messaging people</h2>
        <ul>
          <li>
            Connect only accounts you are authorized to use, and follow the
            rules of each platform, including Meta&rsquo;s Platform Terms,
            Instagram and Messenger policies, the WhatsApp Business Policy
            (including its messaging window and approved-template rules) and
            Telegram&rsquo;s terms.
          </li>
          <li>
            Get the consent the law requires before you message people, add them
            to email lists or call them, and honor opt-outs. Instantlify
            respects opt-outs and platform messaging windows, but you remain
            responsible for your messages and lists.
          </li>
          <li>
            Give people any notices the law requires, for example that they are
            talking to an automated assistant where that applies, and a privacy
            notice for the data you collect through forms, chat and signups.
          </li>
          <li>
            For data about your customers, you are the controller and we process
            it for you as described in the privacy policy. A data processing
            agreement is available on request.
          </li>
        </ul>

        <h2>5. Acceptable use</h2>
        <p>You must not use Instantlify to:</p>
        <ul>
          <li>
            send spam, unsolicited bulk messages or messages to people who opted
            out;
          </li>
          <li>harass, threaten, deceive or impersonate anyone;</li>
          <li>
            send illegal, infringing, hateful or sexually exploitative content;
          </li>
          <li>collect sensitive data you are not permitted to collect;</li>
          <li>
            break, overload, scrape or reverse engineer the service, get around
            its limits or access other workspaces;
          </li>
          <li>violate any law or any messaging platform&rsquo;s rules.</li>
        </ul>
        <p>
          We may suspend automations, messaging or accounts that put people, the
          service or our platform relationships at risk.
        </p>

        <h2>6. AI features</h2>
        <p>
          AI replies, agents, summaries, intent detection and comment moderation
          are generated automatically and can be wrong. Review your instructions
          and knowledge, test with the preview tools, and supervise what is sent
          on your behalf. You are responsible for AI-generated messages sent
          from your workspace. AI features use AI providers described in the
          privacy policy and consume AI credits or your own provider keys.
        </p>

        <h2>7. Plans, trials and payment</h2>
        <ul>
          <li>
            Paid plans are billed in advance, monthly or yearly, through Stripe,
            and renew automatically until cancelled. New plans may include a
            free trial; you will be charged when it ends unless you cancel
            first.
          </li>
          <li>
            AI credits are prepaid and used as AI features run. You can turn on
            automatic top-ups. AI features pause when credits run out.
          </li>
          <li>
            You can cancel any time; your plan stays active to the end of the
            period you paid for. Except where the law requires otherwise,
            payments and used credits are not refundable.
          </li>
          <li>
            Prices exclude taxes unless stated. If a payment fails we may limit
            the workspace until it is resolved. We will give notice before price
            changes take effect for your plan.
          </li>
          <li>
            Payments you take from your own customers in chat are processed by
            your own Stripe account under your agreement with Stripe; you are
            the seller.
          </li>
          <li>
            Paid templates sold in the marketplace are subject to a platform
            fee, and seller payouts are made through Stripe Connect. Affiliate
            program participation is subject to its own terms.
          </li>
        </ul>

        <h2>8. Third-party services</h2>
        <p>
          Instantlify works with platforms and tools we do not control, such as
          Meta, WhatsApp, Telegram, Stripe, Google, Microsoft, AI providers and
          the integrations you connect. Your use of them is governed by their
          terms. They may change, limit or stop access, which can affect
          features, and we are not responsible for their services.
        </p>

        <h2>9. Your content and data</h2>
        <p>
          You keep ownership of the content and data in your workspace. You give
          us the permission needed to host, process, transmit and display it to
          provide and secure the service. You can export or delete your
          workspace data at any time in Settings → Data &amp; privacy. If you
          send us feedback, we may use it without obligation to you.
        </p>

        <h2>10. Our property</h2>
        <p>
          Instantlify, its software, design and brand belong to {LEGAL.company}{" "}
          and its licensors. These terms do not give you rights to them beyond
          using the service as permitted.
        </p>

        <h2>11. Suspension and termination</h2>
        <p>
          You can stop using Instantlify and delete your workspace at any time.
          We may suspend or end access if you breach these terms, fail to pay,
          or if required by law or a platform. Where we can, we will give notice
          and a chance to export your data. Sections that by their nature should
          survive (such as payment obligations, limits of liability and
          indemnity) survive termination.
        </p>

        <h2>12. Disclaimers</h2>
        <p>
          The service is provided &ldquo;as is&rdquo; and &ldquo;as
          available&rdquo;. To the extent the law allows, we disclaim warranties
          of merchantability, fitness for a particular purpose and
          non-infringement, and we do not promise the service will be
          uninterrupted, error-free or that messages will always be delivered by
          third-party platforms.
        </p>

        <h2>13. Limitation of liability</h2>
        <p>
          To the extent the law allows, neither party is liable for indirect,
          incidental, special or consequential damages, or for lost profits,
          revenue or data, and each party&rsquo;s total liability is limited to
          the amount you paid us in the 12 months before the claim. These limits
          do not apply where the law does not allow them.
        </p>

        <h2>14. Indemnity</h2>
        <p>
          You will defend and compensate us against claims arising from your
          content, your messages and campaigns, your use of connected platforms,
          or your breach of these terms or the law.
        </p>

        <h2>15. Changes to these terms</h2>
        <p>
          We may update these terms. We will post the new version here and, for
          material changes, notify account holders in advance. Continuing to use
          Instantlify after changes take effect means you accept them.
        </p>

        <h2>16. Governing law</h2>
        <p>
          These terms are governed by the laws of {LEGAL.governingLaw}, and
          disputes will be resolved in its courts, except where the law of your
          country gives you the right to bring a claim locally.
        </p>

        <h2>17. Contact</h2>
        <p>
          {LEGAL.company}, {LEGAL.address}. Support: {LEGAL.supportEmail}.
          Privacy: {LEGAL.privacyEmail}.
        </p>
      </article>
    </main>
  );
}
