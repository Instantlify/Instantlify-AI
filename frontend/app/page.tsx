import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowRight,
  Check,
  GitBranch,
  Instagram,
  MessageCircle,
  Sparkles,
  Users,
  CalendarCheck,
  ShieldCheck,
  Zap,
  Send,
  ChevronRight,
} from "lucide-react";
import { Brand } from "@/components/shell";
import { TrackVisit } from "@/components/growth";
import { PublicPricing } from "@/components/public-pricing";
import { PublicHelpLinks } from "@/components/public-help-links";

export const metadata: Metadata = {
  title: "Nemio · Turn conversations into customers",
  description:
    "Grow your business with Nemio: AI sales agents, messaging automation, a unified inbox, CRM, bookings and payments. Explore plans and get started.",
  openGraph: {
    title: "Nemio · Turn conversations into customers",
    description:
      "Your conversations, team and sales automations. One connected workspace.",
    type: "website",
  },
};

const features = [
  {
    icon: MessageCircle,
    title: "One inbox. Every conversation.",
    copy: "Bring Instagram, WhatsApp, Messenger and Telegram together. Give every customer a thoughtful reply without switching tabs.",
    tone: "violet",
  },
  {
    icon: Sparkles,
    title: "Meet your AI sales teammate.",
    copy: "Answer questions from your knowledge base, qualify leads and help customers take the next step. Your team stays in control.",
    tone: "teal",
  },
  {
    icon: GitBranch,
    title: "Your best follow-up, on repeat.",
    copy: "Build visual automations that turn comments and messages into conversations. Start with a template and make it yours.",
    tone: "orange",
  },
  {
    icon: CalendarCheck,
    title: "From first hello to booked.",
    copy: "Keep leads, bookings and payment links in the same workflow, with funnel analytics to see what moves your business forward.",
    tone: "blue",
  },
];

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  // Keep previously issued invitation and pricing links working.
  if (query.invite || query.plan) {
    const params = new URLSearchParams();
    for (const key of ["invite", "plan", "interval"]) {
      if (typeof query[key] === "string") params.set(key, query[key]);
    }
    if (query.plan) params.set("mode", "signup");
    redirect(`/auth?${params.toString()}`);
  }
  return (
    <div className="marketing">
      <TrackVisit page="/" />
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="marketing-nav">
        <Link href="/" aria-label="Nemio home">
          <Brand />
        </Link>
        <nav aria-label="Main navigation">
          <a href="#features">Product</a>
          <a href="#how-it-works">How it works</a>
          <a href="#pricing">Pricing</a>
        </nav>
        <div className="marketing-actions">
          <Link href="/auth" className="sign-in">
            Sign in
          </Link>
          <Link href="/auth?mode=signup" className="button primary">
            Get started <ArrowRight size={16} />
          </Link>
        </div>
      </header>
      <main id="main">
        <section className="landing-hero">
          <div className="hero-copy">
            <span className="hero-kicker">
              <span /> FOR BUSINESSES THAT SELL THROUGH CONVERSATION
            </span>
            <h1>
              Turn enquiries into
              <br />
              <span>booked appointments.</span>
            </h1>
            <p>
              Answer common questions, qualify interested customers and help
              them book. Your AI assistant handles the first conversation; your
              team stays in control.
            </p>
            <div className="hero-actions">
              <Link href="/auth?mode=signup" className="button primary">
                Set up my assistant <ArrowRight size={18} />
              </Link>
              <a href="#how-it-works" className="button hero-secondary">
                See how it works <ChevronRight size={17} />
              </a>
            </div>
            <div className="hero-assurances">
              <span>
                <Check size={15} /> No-code automations
              </span>
              <span>
                <Check size={15} /> Human when it matters
              </span>
            </div>
          </div>
          <div
            className="product-scene"
            aria-label="Illustrative example of a customer conversation and AI follow-up"
          >
            <div className="scene-label">
              <span className="live-dot" /> A LITTLE LESS BUSYWORK. A LOT MORE
              POSSIBILITY.
            </div>
            <div className="demo-window">
              <div className="demo-toolbar">
                <span className="demo-logo">
                  <MessageCircle size={16} /> nemio
                </span>
                <span className="demo-label">Inbox preview</span>
                <span className="demo-dots">•••</span>
              </div>
              <div className="demo-body">
                <div className="demo-rail">
                  <MessageCircle size={19} />
                  <GitBranch size={19} />
                  <Users size={19} />
                  <Sparkles size={19} />
                </div>
                <div className="demo-chat">
                  <div className="demo-person">
                    <span className="demo-avatar">JL</span>
                    <div>
                      <strong>Jamie Lee</strong>
                      <small>
                        <Instagram size={12} /> Instagram · Example conversation
                      </small>
                    </div>
                    <span className="demo-status">New lead</span>
                  </div>
                  <div className="chat-date">TODAY, 10:24 AM</div>
                  <div className="demo-message incoming">
                    Hi! I love your work. Can I book a consultation?
                  </div>
                  <div className="demo-agent-label">
                    <Sparkles size={12} /> Nemio AI
                  </div>
                  <div className="demo-message outgoing">
                    Absolutely! Let’s find a time that works for you. Would you
                    prefer morning or afternoon?
                  </div>
                  <div className="demo-message incoming short">
                    Afternoon would be perfect 🙌
                  </div>
                  <div className="demo-booking">
                    <CalendarCheck size={20} />
                    <div>
                      <strong>The next step, made simple.</strong>
                      <small>Qualify → Find a time → Confirm</small>
                    </div>
                    <Check size={17} />
                  </div>
                  <div className="demo-compose">
                    Your team can take over anytime <Send size={15} />
                  </div>
                </div>
              </div>
            </div>
            <div className="scene-note">
              <span>
                <Zap size={20} />
              </span>
              <div>
                <strong>Keep the conversation moving.</strong>
                <small>From a first hello to a new opportunity.</small>
              </div>
            </div>
          </div>
        </section>
        <section
          className="channel-strip"
          aria-label="Supported messaging channels"
        >
          <span>YOUR CUSTOMERS ARE ALREADY HERE.</span>
          <div>
            <Instagram size={20} /> Instagram
          </div>
          <div>
            <MessageCircle size={20} /> WhatsApp
          </div>
          <div>
            <MessageCircle size={20} /> Messenger
          </div>
          <div>
            <Send size={20} /> Telegram
          </div>
        </section>
        <section className="landing-section" id="features">
          <div className="section-heading">
            <span className="eyebrow">LESS FRICTION. MORE CONNECTION.</span>
            <h2>
              Big possibilities.
              <br />
              One connected workspace.
            </h2>
            <p>
              Built for service businesses turning customer enquiries into
              consultations and appointments.
            </p>
          </div>
          <div className="feature-grid">
            {features.map(({ icon: Icon, title, copy, tone }) => (
              <article className={`feature-tile ${tone}`} key={title}>
                <span className="feature-icon">
                  <Icon size={24} />
                </span>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="how-section" id="how-it-works">
          <div className="section-heading">
            <span className="eyebrow">FROM HELLO TO WHAT’S NEXT</span>
            <h2>Your business, with a little more flow.</h2>
            <p>Start small. Build the workflow that works for you.</p>
          </div>
          <div className="steps-grid">
            {[
              [
                "01",
                "Make yourself at home",
                "Create your workspace and choose the first customer enquiry you want to automate.",
              ],
              [
                "02",
                "Connect the conversation",
                "Add your services, prices and FAQs. Preview your assistant’s answers before enabling replies.",
              ],
              [
                "03",
                "Give every lead a next step",
                "Connect your account, activate your workflow and keep your team available for questions that need a human.",
              ],
            ].map(([number, title, copy]) => (
              <article key={number}>
                <span>{number}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="landing-section" id="pricing">
          <div className="section-heading">
            <span className="eyebrow">ROOM TO GROW</span>
            <h2>The right fit for your next chapter.</h2>
            <p>
              Explore current plans, compare what’s included and choose your
              pace.
            </p>
          </div>
          <PublicPricing />
        </section>
        <section className="landing-faq">
          <div>
            <span className="eyebrow">A FEW GOOD QUESTIONS</span>
            <h2>Let’s clear things up.</h2>
          </div>
          <div>
            {[
              [
                "What does Nemio do?",
                "Nemio helps businesses manage customer conversations, automate follow-ups and turn interest into sales. Your inbox, AI agent, CRM, bookings and payments live in one workspace.",
              ],
              [
                "Can my team take over from the AI?",
                "Yes. Your team can step into conversations, assign leads and manage human handoffs. You decide where automation helps and where a personal reply matters.",
              ],
              [
                "Do I need to know how to code?",
                "No. Build automations visually, start from templates and add your own business knowledge. Connecting external services may require accounts and provider approval.",
              ],
              [
                "Can I use Nemio for my agency?",
                "Yes. Nemio supports separate client workspaces and agency branding. Available features and limits depend on your plan and workspace configuration.",
              ],
            ].map(([q, a]) => (
              <details key={q}>
                <summary>{q}</summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="closing-cta">
          <Sparkles size={30} />
          <h2>
            Your next great customer
            <br />
            relationship starts here.
          </h2>
          <p>Make room for more conversations. We’ll help with the busywork.</p>
          <Link href="/auth?mode=signup" className="button">
            Get started with Nemio <ArrowRight size={17} />
          </Link>
          <span>
            <ShieldCheck size={14} /> Your business. Your team. Your workspace.
          </span>
        </section>
      </main>
      <footer className="marketing-footer">
        <Link href="/" aria-label="Nemio home">
          <Brand />
        </Link>
        <p>More connection. More possibility.</p>
        <nav aria-label="Footer navigation">
          <PublicHelpLinks />
          <Link href="/pricing">Pricing</Link>
          <Link href="/blog">Blog</Link>
          <Link href="/auth">Sign in</Link>
        </nav>
        <small>© {new Date().getFullYear()} Nemio</small>
      </footer>
    </div>
  );
}
