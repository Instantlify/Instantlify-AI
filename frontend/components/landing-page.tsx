"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  GitBranch,
  Instagram,
  MessageCircle,
  Sparkles,
  Users,
  CalendarCheck,
  ShieldCheck,
  Zap,
  Send,
  Menu,
  X,
  Search,
  BarChart3,
  CreditCard,
  Mic,
  Link2,
  LayoutTemplate,
  Headphones,
  Globe,
  CheckCircle2,
} from "lucide-react";
import { Brand } from "@/components/shell";
import { TrackVisit } from "@/components/growth";
import { PublicPricing } from "@/components/public-pricing";
import { ProductDepth } from "@/components/landing-depth";

const scenarios = [
  {
    name: "Comment → DM",
    trigger: "A comment contains “GUIDE”",
    channel: "Instagram",
    incoming: "GUIDE! I’d love to learn more.",
    reply:
      "Here’s your getting-started guide. What’s the biggest thing you’d like to improve?",
    answer: "Following up with people interested in my services.",
    result: "Resource delivered · Interest tagged",
    icon: Instagram,
  },
  {
    name: "Story reply",
    trigger: "Someone replies to your story",
    channel: "Instagram",
    incoming: "Is the workshop suitable for beginners?",
    reply:
      "Yes! We start with the basics and build from there. Would you like the workshop details?",
    answer: "Yes please, send them over!",
    result: "Workshop details sent · Lead captured",
    icon: Instagram,
  },
  {
    name: "AI qualification",
    trigger: "A customer asks about your services",
    channel: "WhatsApp",
    incoming: "Can you help our team automate sales enquiries?",
    reply:
      "Happy to help. Which channel gets the most enquiries, and what would you like to automate first?",
    answer: "WhatsApp. We want to book more consultations.",
    result: "Intent identified · Ready for a booking",
    icon: MessageCircle,
  },
  {
    name: "Team handoff",
    trigger: "A conversation needs a human",
    channel: "Telegram",
    incoming: "I have a question about a custom project.",
    reply:
      "Let’s get the right person involved. Tell me a little about your project and I’ll pass the context to our team.",
    answer: "We need a workflow for three client accounts.",
    result: "Team notified · Context preserved",
    icon: Send,
  },
];

const capabilities = [
  {
    icon: GitBranch,
    title: "Visual automations",
    detail:
      "Connect message blocks, buttons, conditions, delays and handoffs on a visual canvas. Start from a template, publish your workflow and inspect execution logs.",
    tags: "Keyword triggers · Branches · Templates",
  },
  {
    icon: Sparkles,
    title: "AI sales agents",
    detail:
      "Train an assistant on your business documents and FAQs. Guide enquiries through qualification, use configured booking and payment tools, and review agent activity in the audit log.",
    tags: "Knowledge base · Tools · Human oversight",
  },
  {
    icon: Users,
    title: "A connected inbox & CRM",
    detail:
      "Manage conversations across your connected channels. Assign teammates, add internal notes, update stages and tags, merge contacts and hand off AI conversations to a person.",
    tags: "Assignment · Lead stages · Segmentation",
  },
  {
    icon: Mic,
    title: "Voice that feels personal",
    detail:
      "Use the ElevenLabs integration for AI voice replies and transcribe incoming voice notes. Voice delivery depends on your connected provider, channel and plan.",
    tags: "Voice replies · Transcription · Provider setup",
  },
  {
    icon: CalendarCheck,
    title: "Bookings & payment links",
    detail:
      "Connect your calendar, check availability and confirm appointments with your customer. Share payment links for your configured offers and track the next step in the funnel.",
    tags: "Google Calendar · Cal.com · Stripe",
  },
  {
    icon: BarChart3,
    title: "See what moves the needle",
    detail:
      "Follow the journey from first interaction to booking and payment. Break results down by channel and automation, and compare workflow variants with A/B experiments.",
    tags: "Funnel analytics · Attribution · Experiments",
  },
];

const integrations = [
  ["Instagram", "Channels", "IG", "Channel connection"],
  ["WhatsApp", "Channels", "WA", "Channel connection"],
  ["Messenger", "Channels", "M", "Channel connection"],
  ["Telegram", "Channels", "TG", "Channel connection"],
  ["Google Calendar", "Scheduling", "GC", "Native integration"],
  ["Cal.com", "Scheduling", "Cal", "Native integration"],
  ["Airtable", "CRM", "A", "Native integration"],
  ["Notion", "CRM", "N", "Native integration"],
  ["GoHighLevel", "CRM", "GH", "Native integration"],
  ["Attio", "CRM", "At", "Native integration"],
  ["Slack", "Team & AI", "S", "Native integration"],
  ["ElevenLabs", "Team & AI", "Ⅱ", "Voice provider"],
  ["OpenAI", "Team & AI", "AI", "AI provider"],
  ["Stripe", "Payments", "$", "Payment provider"],
  ["Zapier", "Automation", "Z", "API / webhook connector"],
  ["n8n", "Automation", "n8n", "API / webhook connector"],
  ["Make", "Automation", "Mk", "API / webhooks"],
];

const faqs = [
  [
    "What does Nemio do?",
    "Nemio connects sales conversations, visual automations, an AI assistant, your CRM, bookings and payment links in one workspace. Start with one workflow and expand as your business needs grow.",
  ],
  [
    "Which channels can I connect?",
    "The app supports Instagram, WhatsApp, Messenger and Telegram adapters. Live messaging requires your provider credentials, permissions and, for Meta channels, the relevant app review. A local test provider lets you explore before connecting.",
  ],
  [
    "Do I need to know how to code?",
    "No. Build automations visually, start from templates and add your own business knowledge. Connecting external services may require accounts and provider approval.",
  ],
  [
    "Can my team take over from the AI?",
    "Yes. Assign a conversation, add internal notes and switch to a human handoff. The assistant’s tool calls and activity are recorded so your team can review what happened.",
  ],
  [
    "How do voice replies and bookings work?",
    "Voice replies use a configured voice provider. Bookings use your connected calendar and require customer confirmation. Neither sends audio nor books a real appointment from this landing-page demo.",
  ],
  [
    "Can I manage agency clients?",
    "Yes. Separate client workspaces, team roles and branding tools are available in the app. Check the live plan cards for your account, seat and usage limits.",
  ],
  [
    "Are all tools included in every plan?",
    "Features and limits depend on the plan. The pricing section loads the current catalogue from Nemio, including AI usage, contacts, connected accounts, voice and integration availability. External providers may charge separately.",
  ],
  [
    "What about privacy and customer data?",
    "Nemio includes tenant-scoped access, encrypted provider credentials, audit records and customer data export and deletion tools. Configure retention and connected providers to suit your business requirements.",
  ],
];

function Demo({
  scenario,
  step,
  onStep,
}: {
  scenario: number;
  step: number;
  onStep: () => void;
}) {
  const item = scenarios[scenario];
  const Icon = item.icon;
  return (
    <div className="nm-demo" aria-label="Illustrative conversation demo">
      <div className="nm-demo-toolbar">
        <span>
          <span className="nm-dot" /> Conversation preview
        </span>
        <span>•••</span>
      </div>
      <div className="nm-demo-person">
        <span className="nm-avatar">JD</span>
        <div>
          <strong>Jordan Davis</strong>
          <small>
            <Icon size={12} /> {item.channel} · Example lead
          </small>
        </div>
        <span className="nm-status">
          {step === 2 ? "Qualified" : "New enquiry"}
        </span>
      </div>
      <div className="nm-chat" aria-live="polite">
        <div className="nm-time">ILLUSTRATIVE DEMO · NO MESSAGES ARE SENT</div>
        <div className="nm-bubble incoming">{item.incoming}</div>
        <div className="nm-agent">
          <Sparkles size={12} /> Nemio assistant
        </div>
        <div className="nm-bubble outgoing">{item.reply}</div>
        {step >= 1 && <div className="nm-bubble incoming">{item.answer}</div>}
        {step >= 2 && (
          <div className="nm-result">
            <CheckCircle2 size={19} />
            <div>
              <strong>{item.result}</strong>
              <small>A useful next step, without the busywork.</small>
            </div>
          </div>
        )}
      </div>
      <button className="nm-demo-next" onClick={onStep}>
        {step === 0
          ? "Simulate customer reply"
          : step === 1
            ? "Run the next step"
            : "Replay conversation"}
        <ArrowRight size={16} />
      </button>
    </div>
  );
}

export function LandingPage({ helpLinks }: { helpLinks: ReactNode }) {
  const [mobile, setMobile] = useState(false);
  const [scenario, setScenario] = useState(0);
  const [step, setStep] = useState(0);
  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [audience, setAudience] = useState(0);
  const filtered = integrations.filter(
    ([name, group]) =>
      (category === "All" || group === category) &&
      name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="nm-landing">
      <TrackVisit page="/" />
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="nm-announcement">
        <span>A better way to keep the conversation going.</span>
        <a href="#interactive-demo">
          Meet your next sales teammate <ArrowUpRight size={13} />
        </a>
      </div>
      <header className="nm-nav">
        <Link href="/" aria-label="Nemio home">
          <Brand />
        </Link>
        <nav
          className={mobile ? "nm-nav-links open" : "nm-nav-links"}
          aria-label="Main navigation"
        >
          <details className="nm-mega">
            <summary>
              Product <ChevronDown size={13} />
            </summary>
            <div
              className="nd-mega-menu"
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("a")) {
                  setMobile(false);
                  event.currentTarget
                    .closest("details")
                    ?.removeAttribute("open");
                }
              }}
            >
              {[
                {
                  title: "Automate",
                  links: [
                    [
                      "Flow builder",
                      "flow-builder",
                      "Branches, waits & templates",
                    ],
                    [
                      "AI sales agents",
                      "ai-agents",
                      "Knowledge, qualification & actions",
                    ],
                    [
                      "AI voice notes",
                      "voice-detail",
                      "Voice replies & transcription",
                    ],
                  ],
                },
                {
                  title: "Channels",
                  links: [
                    [
                      "Instagram automation",
                      "channels-detail",
                      "Comments, stories & DMs",
                    ],
                    [
                      "WhatsApp & Telegram",
                      "channels-detail",
                      "Messages, agents & handoffs",
                    ],
                    [
                      "Messenger",
                      "channels-detail",
                      "Page conversations in one inbox",
                    ],
                  ],
                },
                {
                  title: "Convert",
                  links: [
                    [
                      "Inbox & CRM",
                      "inbox-crm",
                      "Contacts, assignments & stages",
                    ],
                    [
                      "Bookings & payments",
                      "sales-tools",
                      "Calendar and offer connections",
                    ],
                    [
                      "Analytics & growth",
                      "growth-detail",
                      "Funnels, experiments & content",
                    ],
                  ],
                },
                {
                  title: "Scale",
                  links: [
                    [
                      "Agency & team tools",
                      "agency-detail",
                      "Clients, branding & roles",
                    ],
                    [
                      "Integrations",
                      "integrations",
                      "Native tools, APIs & webhooks",
                    ],
                    [
                      "Every feature",
                      "feature-catalog",
                      "Search the complete catalogue",
                    ],
                  ],
                },
              ].map(({ title, links }) => (
                <div key={title}>
                  <strong>{title}</strong>
                  {links.map(([label, id, description]) => (
                    <a href={`#${id}`} key={label}>
                      <span>
                        {label}
                        <small>{description}</small>
                      </span>
                      <ArrowUpRight size={13} />
                    </a>
                  ))}
                </div>
              ))}
            </div>
          </details>
          <a href="#solutions" onClick={() => setMobile(false)}>
            Solutions
          </a>
          <a href="#integrations" onClick={() => setMobile(false)}>
            Integrations
          </a>
          <a href="#pricing" onClick={() => setMobile(false)}>
            Pricing
          </a>
          <Link href="/blog">Resources</Link>
        </nav>
        <div className="nm-nav-actions">
          <Link href="/auth">Sign in</Link>
          <Link className="nm-button small" href="/auth?mode=signup">
            Get started <ArrowUpRight size={15} />
          </Link>
          <button
            className="nm-menu"
            aria-label={mobile ? "Close navigation" : "Open navigation"}
            aria-expanded={mobile}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X /> : <Menu />}
          </button>
        </div>
      </header>
      <main id="main">
        <section className="nm-hero">
          <div className="nm-hero-copy">
            <span className="nm-eyebrow">
              <span className="nm-dot" /> YOUR CONVERSATIONS. MORE
              POSSIBILITIES.
            </span>
            <h1>
              Turn enquiries into
              <br />
              <em>your next customer.</em>
            </h1>
            <p>
              Turn comments, story replies and messages into sales
              conversations. Build visual automations, qualify leads with AI,
              send voice replies, book appointments and share payment links—all
              from one workspace.
            </p>
            <div className="nm-hero-actions">
              <Link className="nm-button" href="/auth?mode=signup">
                Set up my assistant <ArrowUpRight size={18} />
              </Link>
              <a className="nm-text-link" href="#interactive-demo">
                <span className="nm-play">▶</span> See it in action
              </a>
            </div>
            <div className="nm-assurances">
              <span>
                <Check size={14} /> No-code workflows
              </span>
              <span>
                <Check size={14} /> Your team in control
              </span>
            </div>
            <div className="nm-hero-foot">
              FOR CREATORS, SERVICE BUSINESSES & AGENCIES
            </div>
          </div>
          <div className="nm-hero-scene">
            <span className="nm-scene-caption">
              A FIRST HELLO, MEET A CLEAR NEXT STEP.
            </span>
            <Demo
              scenario={scenario}
              step={step}
              onStep={() => setStep((step + 1) % 3)}
            />
            <div className="nm-float">
              <span>
                <Zap size={19} />
              </span>
              <div>
                <strong>Less chasing. More connecting.</strong>
                <small>Reply → qualify → move things forward</small>
              </div>
            </div>
            <span className="nm-orbit">✳</span>
          </div>
        </section>
        <section
          className="nm-channels"
          aria-label="Supported messaging channels"
        >
          <span>
            ONE WORKSPACE.
            <br />
            <b>WHEREVER THEY SAY HELLO.</b>
          </span>
          <div>
            <Instagram /> Instagram
          </div>
          <div>
            <MessageCircle /> WhatsApp
          </div>
          <div>
            <MessageCircle /> Messenger
          </div>
          <div>
            <Send /> Telegram
          </div>
        </section>
        <section className="nm-section" id="interactive-demo">
          <div className="nm-section-head">
            <span className="nm-eyebrow">
              01 / A CONVERSATION THAT GOES SOMEWHERE
            </span>
            <h2>
              From a small interaction.
              <br />
              To a real opportunity.
            </h2>
            <p>
              Explore how a workflow responds, gathers context and gives your
              customer a next step. Click through an example.
            </p>
          </div>
          <div className="nm-demo-layout">
            <div>
              <div
                className="nm-scenario-list"
                role="group"
                aria-label="Conversation scenarios"
              >
                {scenarios.map((item, index) => (
                  <button
                    key={item.name}
                    aria-pressed={scenario === index}
                    className={scenario === index ? "active" : ""}
                    onClick={() => {
                      setScenario(index);
                      setStep(0);
                    }}
                  >
                    <span className="nm-number">0{index + 1}</span>
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.trigger}</small>
                    </span>
                    <ArrowUpRight size={19} />
                  </button>
                ))}
              </div>
              <div className="nm-demo-note">
                <ShieldCheck size={18} />
                <p>
                  Try the idea here. Configure the real workflow inside your
                  workspace before turning on replies.
                </p>
              </div>
            </div>
            <Demo
              scenario={scenario}
              step={step}
              onStep={() => setStep((step + 1) % 3)}
            />
          </div>
        </section>
        <section className="nm-platform" id="features">
          <div className="nm-section-head">
            <span className="nm-eyebrow">
              02 / CONNECT THE WHOLE CUSTOMER JOURNEY
            </span>
            <h2>
              A lot happens after “hello.”
              <br />
              Keep it all in the loop.
            </h2>
            <p>
              Your assistant starts the conversation. Your workspace keeps the
              context. Your team decides what happens next.
            </p>
          </div>
          <div className="nm-feature-grid">
            {capabilities.map(({ icon: Icon, title, detail, tags }, index) => (
              <article key={title}>
                <div className="nm-feature-top">
                  <Icon size={24} />
                  <span>0{index + 1}</span>
                </div>
                <h3>{title}</h3>
                <p>{detail}</p>
                <small>{tags}</small>
              </article>
            ))}
          </div>
          <div className="nm-flow">
            <div>
              <MessageCircle />
              <span>
                Listen<small>Comment, story or message</small>
              </span>
            </div>
            <ArrowRight />
            <div>
              <Sparkles />
              <span>
                Understand<small>Intent, context and knowledge</small>
              </span>
            </div>
            <ArrowRight />
            <div>
              <GitBranch />
              <span>
                Take action<small>Reply, tag, book or hand off</small>
              </span>
            </div>
            <ArrowRight />
            <div>
              <BarChart3 />
              <span>
                Learn<small>Review your funnel</small>
              </span>
            </div>
          </div>
        </section>
        <ProductDepth />
        <section className="nm-section" id="solutions">
          <div className="nm-section-head">
            <span className="nm-eyebrow">03 / BUILT AROUND YOUR WORK</span>
            <h2>
              Different businesses.
              <br />
              The same need to connect.
            </h2>
          </div>
          <div
            className="nm-audience-tabs"
            role="group"
            aria-label="Business type"
          >
            {["Creators", "Service businesses", "Agencies"].map(
              (item, index) => (
                <button
                  key={item}
                  aria-pressed={audience === index}
                  className={audience === index ? "active" : ""}
                  onClick={() => setAudience(index)}
                >
                  {item}
                </button>
              ),
            )}
          </div>
          <div className="nm-solution-panel">
            <div>
              <span className="nm-eyebrow">YOUR WORKFLOW, YOUR WAY</span>
              <h3>
                {
                  [
                    "Give your audience somewhere to go.",
                    "Spend more time with your customers.",
                    "A workspace for every client relationship.",
                  ][audience]
                }
              </h3>
              <p>
                {
                  [
                    "Turn engagement on your content into thoughtful conversations. Deliver a resource, learn what someone needs and guide them toward your offer.",
                    "Answer common service questions, gather the details that matter and help customers arrange a consultation. Keep complex requests with your team.",
                    "Create separate client workspaces, reuse automation templates and give the right people access. Add your branding and keep each client’s context together.",
                  ][audience]
                }
              </p>
              <Link className="nm-text-link" href="/auth?mode=signup">
                Build your first workflow <ArrowRight size={16} />
              </Link>
            </div>
            <div className="nm-workflow-card">
              <span className="nm-mini-title">EXAMPLE WORKFLOW</span>
              {[
                ...[
                  [
                    "Comment on a post",
                    "Deliver your resource",
                    "Tag interests in the CRM",
                    "Share the next offer",
                  ],
                  [
                    "Receive a service enquiry",
                    "Answer from your FAQs",
                    "Check calendar availability",
                    "Confirm with your customer",
                  ],
                  [
                    "Create a client workspace",
                    "Apply your branding",
                    "Invite the right teammates",
                    "Review the client’s funnel",
                  ],
                ][audience],
              ].map((item, index) => (
                <div key={item}>
                  <span>{index === 3 ? <Check size={15} /> : index + 1}</span>
                  {item}
                  {index < 3 && <i />}
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="nm-integrations nm-section" id="integrations">
          <div className="nm-section-head">
            <span className="nm-eyebrow">
              04 / YOUR TOOLS, WORKING TOGETHER
            </span>
            <h2>
              Keep your favourites.
              <br />
              Connect the dots.
            </h2>
            <p>
              Connect the services your business runs on. Native providers and
              API connectors are labelled so you can see how each fits.
            </p>
          </div>
          <div className="nm-integration-controls">
            <div
              className="nm-filter"
              role="group"
              aria-label="Integration category"
            >
              {[
                "All",
                "Channels",
                "Scheduling",
                "CRM",
                "Team & AI",
                "Payments",
                "Automation",
              ].map((item) => (
                <button
                  key={item}
                  aria-pressed={category === item}
                  className={category === item ? "active" : ""}
                  onClick={() => setCategory(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <label className="nm-search">
              <Search size={17} />
              <input
                type="search"
                aria-label="Search integrations"
                placeholder="Find your tool…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
          </div>
          <div className="nm-integration-grid" aria-live="polite">
            {filtered.map(([name, group, monogram, type]) => (
              <article key={name}>
                <span
                  className={`nm-app-icon tone-${group.split(" ")[0].toLowerCase()}`}
                >
                  {monogram}
                </span>
                <div>
                  <h3>{name}</h3>
                  <small>{type}</small>
                </div>
                <ArrowUpRight size={15} />
              </article>
            ))}
            {filtered.length === 0 && (
              <p className="nm-empty">
                No matching integrations. Try another search or category.
              </p>
            )}
          </div>
          <p className="nm-subnote">
            Live connections require provider accounts and configuration. Plan
            limits and provider fees may apply.
          </p>
        </section>
        <section className="nm-toolkit nm-section" id="toolkit">
          <div className="nm-section-head">
            <span className="nm-eyebrow">
              05 / MORE OF YOUR DAY, IN ONE PLACE
            </span>
            <h2>
              The little tools.
              <br />
              That make a big difference.
            </h2>
            <p>
              Give your conversations the support they need, without losing
              sight of what is available today.
            </p>
          </div>
          <div className="nm-tool-grid">
            {[
              {
                icon: Link2,
                title: "Link-in-bio pages",
                copy: "Publish a page for your offers and track clicks back to your audience.",
                status: "Available",
                link: true,
              },
              {
                icon: CalendarCheck,
                title: "Content calendar",
                copy: "Plan and schedule supported channel content alongside your sales work.",
                status: "Available",
                link: true,
              },
              {
                icon: LayoutTemplate,
                title: "Automation templates",
                copy: "Start with a ready-made workflow and adapt it to your business.",
                status: "Available",
                link: true,
              },
              {
                icon: CreditCard,
                title: "Offers & payment links",
                copy: "Manage offers and connect Stripe to help customers complete a purchase.",
                status: "Available",
                link: true,
              },
              {
                icon: Globe,
                title: "Public API & webhooks",
                copy: "Connect custom workflows and send events to external tools.",
                status: "Available",
                link: true,
              },
              {
                icon: Users,
                title: "Client workspaces",
                copy: "Separate client data, control team roles and configure branding.",
                status: "Available",
                link: true,
              },
              {
                icon: ShieldCheck,
                title: "Comment moderation",
                copy: "Automatic abuse filtering and deletion are not yet available in Nemio.",
                status: "Planned",
                link: false,
              },
              {
                icon: ArrowUpRight,
                title: "Deep links",
                copy: "Opening destinations outside in-app browsers is a future addition.",
                status: "Planned",
                link: false,
              },
              {
                icon: BarChart3,
                title: "Creator media kits",
                copy: "A public media kit with synced audience statistics is a future addition.",
                status: "Planned",
                link: false,
              },
              {
                icon: LayoutTemplate,
                title: "Standalone form builder",
                copy: "A dedicated embeddable lead-form builder is not yet available.",
                status: "Planned",
                link: false,
              },
              {
                icon: Headphones,
                title: "Website chat widget",
                copy: "An embeddable support widget needs its own channel implementation.",
                status: "Planned",
                link: false,
              },
              {
                icon: Mic,
                title: "AI video messages",
                copy: "Generated video DMs are not currently supported by the agent.",
                status: "Planned",
                link: false,
              },
            ].map(({ icon: Icon, title, copy, status, link }) => (
              <article key={title}>
                <div>
                  <Icon size={23} />
                  <span className={link ? "nm-available" : "nm-planned"}>
                    {status}
                  </span>
                </div>
                <h3>{title}</h3>
                <p>{copy}</p>
                {link && (
                  <Link
                    href="/auth?mode=signup"
                    aria-label={`Explore ${title}`}
                  >
                    Explore in your workspace <ArrowRight size={14} />
                  </Link>
                )}
              </article>
            ))}
          </div>
        </section>
        <section className="nm-section nm-compare" id="compare">
          <div className="nm-section-head">
            <span className="nm-eyebrow">
              06 / CHOOSE YOUR LEVEL OF CONTROL
            </span>
            <h2>
              Start with a flow.
              <br />
              Add intelligence when you need it.
            </h2>
            <p>
              Two ways to handle the conversation. One workspace for your team.
            </p>
          </div>
          <div className="nm-table-scroll">
            <table>
              <caption>
                Compare visual workflows and AI-assisted conversations in Nemio
              </caption>
              <thead>
                <tr>
                  <th>What you need</th>
                  <th>Visual workflows</th>
                  <th>AI assistant</th>
                </tr>
              </thead>
              <tbody>
                {[
                  [
                    "Predictable replies",
                    "Messages and buttons you write",
                    "Answers from your business knowledge",
                  ],
                  [
                    "Starting the conversation",
                    "Configured keyword and event triggers",
                    "Enabled conversations and incoming messages",
                  ],
                  [
                    "Choosing the next step",
                    "Conditions and branches",
                    "Context and configured sales tools",
                  ],
                  [
                    "Customer context",
                    "Contact fields, tags and stages",
                    "Knowledge retrieval and CRM context",
                  ],
                  [
                    "Booking and payments",
                    "Use configured links in replies",
                    "Calendar checks and configured payment tools",
                  ],
                  [
                    "Human oversight",
                    "Review flows and execution logs",
                    "Handoffs, audit logs and team control",
                  ],
                  [
                    "How to begin",
                    "Choose a template and publish",
                    "Add FAQs, configure tools and test",
                  ],
                ].map(([label, flow, ai]) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    <td>{flow}</td>
                    <td>{ai}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="nm-start nm-section" id="how-it-works">
          <div className="nm-section-head">
            <span className="nm-eyebrow">07 / LESS SETUP. MORE MOMENTUM.</span>
            <h2>Your first workflow starts here.</h2>
          </div>
          <div className="nm-steps">
            {[
              [
                "01",
                "Make a little space",
                "Create your workspace and choose one enquiry you want to handle better.",
              ],
              [
                "02",
                "Give it your knowledge",
                "Add your FAQs or choose a template. Try a local test conversation before connecting live accounts.",
              ],
              [
                "03",
                "Let the conversation flow",
                "Configure your providers, review the workflow and enable it. Keep your team ready for a handoff.",
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
        <section className="nm-section nm-pricing" id="pricing">
          <div className="nm-section-head">
            <span className="nm-eyebrow">08 / FIND YOUR FIT</span>
            <h2>Room for your next chapter.</h2>
            <p>
              Current plans, straight from Nemio. Compare the included features
              and usage limits, then choose how you want to grow.
            </p>
          </div>
          <PublicPricing />
          <Link className="nm-text-link" href="/pricing">
            Open the full pricing page <ArrowRight size={15} />
          </Link>
        </section>
        <section className="nm-section nm-faq" id="faq">
          <div className="nm-section-head">
            <span className="nm-eyebrow">A FEW GOOD QUESTIONS</span>
            <h2>
              Before you
              <br />
              say hello.
            </h2>
            <Link href="/help" className="nm-text-link">
              Visit the help centre <ArrowUpRight size={16} />
            </Link>
          </div>
          <div>
            {faqs.map(([question, answer]) => (
              <details key={question}>
                <summary>
                  <span>{question}</span>
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="nm-closing">
          <span className="nm-eyebrow">
            A LITTLE CONVERSATION. A LOT OF POSSIBILITY.
          </span>
          <h2>
            Your next customer
            <br />
            starts with a hello.
          </h2>
          <p>
            Make room for the work you love. Let Nemio help with the follow-up.
          </p>
          <Link className="nm-button" href="/auth?mode=signup">
            Get started with Nemio <ArrowUpRight size={18} />
          </Link>
          <span className="nm-closing-star" aria-hidden="true">
            ✳
          </span>
        </section>
      </main>
      <footer className="nm-footer">
        <div>
          <Link href="/" aria-label="Nemio home">
            <Brand />
          </Link>
          <p>
            Good conversations.
            <br />
            Better possibilities.
          </p>
        </div>
        <nav aria-label="Footer product navigation">
          <strong>Explore</strong>
          <a href="#features">Platform</a>
          <a href="#integrations">Integrations</a>
          <Link href="/pricing">Pricing</Link>
          <a href="#toolkit">Growth toolkit</a>
        </nav>
        <nav aria-label="Footer resources">
          <strong>Resources</strong>
          <Link href="/blog">Blog</Link>
          <Link href="/help">Help centre</Link>
          <a href="#faq">FAQs</a>
          {helpLinks}
        </nav>
        <nav aria-label="Footer account navigation">
          <strong>Your workspace</strong>
          <Link href="/auth?mode=signup">Get started</Link>
          <Link href="/auth">Sign in</Link>
          <Link href="/auth/reset">Reset password</Link>
        </nav>
        <div className="nm-footer-bottom">
          <span>© {new Date().getFullYear()} Nemio. All rights reserved.</span>
          <span>
            <ShieldCheck size={13} /> Your business. Your team. Your workspace.
          </span>
        </div>
      </footer>
    </div>
  );
}
