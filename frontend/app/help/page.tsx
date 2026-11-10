import Link from "next/link";
import { Brand } from "@/components/shell";
import { PublicHelpLinks } from "@/components/public-help-links";

export const metadata = { title: "Help getting started · Instantlify" };

export default function PublicHelp() {
  const email = process.env.INSTANTLIFY_SUPPORT_EMAIL || process.env.NEMIO_SUPPORT_EMAIL || "support@instantlify.com";
  const contact =
    email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : null;
  return (
    <main className="setup-screen">
      <Link href="/">
        <Brand />
      </Link>
      <section className="setup-card">
        <h1>Let’s get your first workflow working.</h1>
        <p>
          Start with one common enquiry, such as a pricing question or an
          appointment request.
        </p>
        <ol>
          <li>
            Create your workspace. You can connect Instagram during setup or
            come back to it later.
          </li>
          <li>
            Open Automations and choose a starter. Add your own reply and review
            the draft before publishing.
          </li>
          <li>
            For AI replies, save your assistant settings and add your business
            FAQs. Wait until the knowledge is ready, then use Test your
            assistant.
          </li>
          <li>
            Connect your channel under Business tools → Integrations, then test
            a real enquiry before inviting customers to use it.
          </li>
        </ol>
        <h2>Can’t sign in?</h2>
        <p>
          <Link href="/auth/reset/">Reset your password</Link> using your
          account email. Check your spam folder if the email hasn’t arrived.
        </p>
        <h2>Need help with your workspace?</h2>
        <p>
          <Link href="/auth">Sign in</Link> and open Getting started to access
          the workspace help and support tools.
        </p>
        {contact && (
          <p>
            Email <a href={`mailto:${contact}`}>{contact}</a>.
          </p>
        )}
        <nav aria-label="Help links" className="button-row">
          <PublicHelpLinks />
          <Link href="/">Back to home</Link>
        </nav>
      </section>
    </main>
  );
}
