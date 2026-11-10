"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  MessageCircle,
  GitBranch,
  Sparkles,
  Send,
  Users,
  Mic,
  CalendarCheck,
  CreditCard,
  BarChart3,
  ShieldCheck,
  Search,
  Clock,
  FileText,
  Bell,
  Layers,
  Plug,
  Play,
  CheckCircle2,
} from "lucide-react";
import { BrandIcon, type BrandName } from "@/lib/brand-icons";

const channels = [
  {
    name: "Instagram",
    brand: "instagram" as const,
    title: "Let your content start the conversation.",
    copy: "Give the interest on your posts, stories and inbox a clear next step. Deliver resources, answer common questions and keep every enquiry in your CRM.",
    features: [
      [
        "Comment-to-DM",
        "Match a keyword in a comment and send a private reply with your offer or resource.",
      ],
      [
        "Story reply automation",
        "Start a configured workflow when someone replies to your story.",
      ],
      [
        "Direct-message triggers",
        "Turn recurring questions into a consistent first response.",
      ],
      [
        "Live-comment triggers",
        "Use supported live-comment events to start your automation.",
      ],
      [
        "Buttons & links",
        "Give customers a clear choice instead of a wall of text.",
      ],
      [
        "AI sales conversations",
        "Use your knowledge base to qualify an enquiry, then offer a booking or human handoff.",
      ],
    ],
    example: [
      "Customer comments: INFO",
      "Send your service guide",
      "Ask what they need",
      "Save the interest in your CRM",
    ],
  },
  {
    name: "WhatsApp",
    brand: "whatsapp" as const,
    title: "Keep the conversation close to your customer.",
    copy: "Connect your WhatsApp business channel to the same inbox, workflows and assistant. Collect context and guide enquiries toward an appointment or purchase.",
    features: [
      [
        "Business channel connection",
        "Connect your configured WhatsApp business credentials to your workspace.",
      ],
      [
        "Message workflows",
        "Respond to inbound messages with your configured keyword automation.",
      ],
      [
        "AI qualification",
        "Ask useful questions and record what the customer is looking for.",
      ],
      [
        "Voice replies",
        "Use configured voice tools and supported channel media delivery.",
      ],
      [
        "Bookings & offers",
        "Check your calendar or share a payment link for a configured offer.",
      ],
      [
        "Team takeover",
        "Pass the conversation to a teammate with the context still attached.",
      ],
    ],
    example: [
      "Customer asks about a service",
      "Answer from your business FAQs",
      "Check a suitable appointment",
      "Ask the customer to confirm",
    ],
  },
  {
    name: "Telegram",
    brand: "telegram" as const,
    title: "A helpful assistant behind your bot.",
    copy: "Connect a Telegram bot and turn incoming questions into useful conversations. Your sales logic, customer context and team remain in one workspace.",
    features: [
      [
        "Bot connection",
        "Connect your bot with its configured provider credentials.",
      ],
      [
        "Keyword workflows",
        "Use messages to start the right automated response.",
      ],
      [
        "Knowledge-based answers",
        "Answer business questions using the documents you provide.",
      ],
      [
        "Links & media",
        "Share supported message content as part of the customer journey.",
      ],
      [
        "Lead organisation",
        "Keep tags, stages and customer fields with the enquiry.",
      ],
      [
        "Human handoff",
        "Bring a person into a conversation when the assistant needs help.",
      ],
    ],
    example: [
      "Customer messages your bot",
      "Find the relevant business context",
      "Tag the enquiry",
      "Notify your team when needed",
    ],
  },
  {
    name: "Messenger",
    brand: "messenger" as const,
    title: "Bring page conversations into the same inbox.",
    copy: "Keep Messenger enquiries alongside your other connected channels. Reuse workflows and give your team one place to manage incoming customer conversations.",
    features: [
      [
        "Page channel connection",
        "Use the configured Meta account connection for your page.",
      ],
      [
        "Inbound message handling",
        "Receive supported Messenger messages through the channel adapter.",
      ],
      [
        "Visual replies",
        "Build your response logic using the same workflow canvas.",
      ],
      [
        "Shared customer context",
        "Keep the lead’s tags, stage and history in your workspace.",
      ],
      ["Team assignments", "Give the conversation a clear owner."],
      [
        "Delivery safeguards",
        "Channel permissions and messaging windows govern live replies.",
      ],
    ],
    example: [
      "Customer sends a page message",
      "Run the configured workflow",
      "Record the enquiry",
      "Assign the right teammate",
    ],
  },
];

const NETWORKS: Record<string, BrandName> = {
  Instagram: "instagram",
  WhatsApp: "whatsapp",
  Telegram: "telegram",
};

const catalog = [
  [
    "Automation",
    "Comment-to-DM keywords",
    "Deliver a private reply when a matching comment arrives.",
  ],
  [
    "Automation",
    "Direct-message triggers",
    "Start a workflow from a configured message keyword.",
  ],
  [
    "Automation",
    "Story reply triggers",
    "Continue the interest generated by your stories.",
  ],
  [
    "Automation",
    "Live-comment events",
    "Start workflows from supported live-comment events.",
  ],
  [
    "Automation",
    "Visual flow canvas",
    "Arrange and connect message and logic blocks.",
  ],
  [
    "Automation",
    "Conditional branches",
    "Choose the next path from configured conditions.",
  ],
  [
    "Automation",
    "Delay and wait steps",
    "Control when a workflow moves forward.",
  ],
  [
    "Automation",
    "Buttons and choices",
    "Help customers choose a clear next action.",
  ],
  [
    "Automation",
    "Template marketplace",
    "Start with a template instead of an empty canvas.",
  ],
  [
    "Automation",
    "Flow import and export",
    "Move configured workflows between environments.",
  ],
  ["Automation", "Execution logs", "Inspect how a workflow ran for a lead."],
  [
    "Automation",
    "Lead cooldowns",
    "Limit repeated workflow starts for the same lead.",
  ],
  [
    "AI & voice",
    "Business knowledge base",
    "Ground replies in your FAQs and uploaded documents.",
  ],
  [
    "AI & voice",
    "Sales qualification",
    "Gather relevant needs and context during a conversation.",
  ],
  [
    "AI & voice",
    "Configured agent tools",
    "Let the assistant use the tools you have enabled.",
  ],
  [
    "AI & voice",
    "Voice-note replies",
    "Use a configured ElevenLabs voice provider.",
  ],
  [
    "AI & voice",
    "Incoming voice transcription",
    "Make supported audio enquiries usable by the assistant.",
  ],
  [
    "AI & voice",
    "Conversation handoff",
    "Move enquiries to a person when needed.",
  ],
  ["AI & voice", "Agent audit trail", "Review agent runs and tool calls."],
  [
    "AI & voice",
    "AI usage tracking",
    "See recorded message usage against your plan.",
  ],
  [
    "Inbox & CRM",
    "Omni-channel inbox",
    "Bring connected channel conversations into one place.",
  ],
  [
    "Inbox & CRM",
    "Conversation assignment",
    "Give each enquiry an owner on your team.",
  ],
  [
    "Inbox & CRM",
    "Internal notes",
    "Keep teammate context separate from customer replies.",
  ],
  [
    "Inbox & CRM",
    "Lead stages",
    "Organise enquiries through your sales process.",
  ],
  [
    "Inbox & CRM",
    "Tags and custom fields",
    "Save the details that make a lead useful.",
  ],
  ["Inbox & CRM", "Contact merging", "Combine duplicate contact records."],
  [
    "Inbox & CRM",
    "AI segmentation",
    "Group your audience using configured AI analysis.",
  ],
  [
    "Inbox & CRM",
    "Hot-lead notifications",
    "Send configured alerts to your connected Slack workspace.",
  ],
  [
    "Sales & growth",
    "Calendar availability",
    "Check availability through configured calendar providers.",
  ],
  [
    "Sales & growth",
    "Confirmed bookings",
    "Require customer confirmation before making a booking.",
  ],
  [
    "Sales & growth",
    "Offer management",
    "Set up the offers your assistant can share.",
  ],
  [
    "Sales & growth",
    "Stripe payment links",
    "Send links for your configured offers.",
  ],
  [
    "Sales & growth",
    "Funnel analytics",
    "Follow leads from initial interaction through conversion.",
  ],
  [
    "Sales & growth",
    "Channel breakdowns",
    "Inspect your funnel by connected channel.",
  ],
  [
    "Sales & growth",
    "Automation breakdowns",
    "Review which workflow generated the next step.",
  ],
  [
    "Sales & growth",
    "A/B experiments",
    "Compare workflow variants and review results.",
  ],
  [
    "Sales & growth",
    "Content calendar",
    "Plan and schedule supported channel content.",
  ],
  [
    "Sales & growth",
    "Link-in-bio pages",
    "Publish your offers on a shareable page.",
  ],
  [
    "Sales & growth",
    "Bio click tracking",
    "Record clicks associated with your published bio page.",
  ],
  [
    "Team & platform",
    "Separate client workspaces",
    "Keep each client’s data and settings in its own space.",
  ],
  [
    "Team & platform",
    "Team invitations",
    "Invite the people who help manage customer conversations.",
  ],
  [
    "Team & platform",
    "Role-based access",
    "Choose who can manage your workspace and conversations.",
  ],
  [
    "Team & platform",
    "Workspace branding",
    "Configure the available white-label branding settings.",
  ],
  [
    "Team & platform",
    "Public API keys",
    "Connect approved custom systems to workspace data.",
  ],
  [
    "Team & platform",
    "Signed outbound webhooks",
    "Send verifiable events to external workflows.",
  ],
  [
    "Team & platform",
    "Customer data exports",
    "Export customer records through the available tools.",
  ],
  [
    "Team & platform",
    "Data deletion and retention",
    "Manage the available deletion and retention controls.",
  ],
  [
    "Team & platform",
    "Encrypted credentials",
    "Protect connected provider credentials at rest.",
  ],
  [
    "Team & platform",
    "Workspace audit records",
    "Keep a record of important workspace actions.",
  ],
  [
    "Sales & growth",
    "Embeddable lead forms",
    "Create, publish and embed forms with consent, response collection and CRM capture.",
  ],
  [
    "Roadmap",
    "Abusive-comment moderation",
    "Automated filtering and removal of abusive comments.",
    "Planned",
  ],
  [
    "Roadmap",
    "Deep-link destinations",
    "A dedicated solution for in-app browser routing.",
    "Planned",
  ],
  [
    "Sales & growth",
    "Creator media kits",
    "Publish a profile, manual audience figures, work links and collaboration offers. Live follower statistics require an eligible plan and an active, non-test Instagram account with provider permissions.",
    "Available",
  ],
  [
    "Roadmap",
    "Website AI chat widget",
    "An embeddable customer-support channel.",
    "Planned",
  ],
  [
    "Roadmap",
    "Generated video DMs",
    "Personalised AI video-message generation.",
    "Planned",
  ],
  [
    "Roadmap",
    "Natural-language flow creation",
    "Generate a workflow from a written instruction.",
    "Planned",
  ],
  [
    "Roadmap",
    "Dedicated phone-number management",
    "A complete business-number lifecycle interface.",
    "Planned",
  ],
  [
    "Roadmap",
    "Follower verification gates",
    "Dedicated follow-status checks and new-follower workflows.",
    "Planned",
  ],
];

function DetailList({ items }: { items: string[][] }) {
  return (
    <div className="nd-details">
      {items.map(([title, description]) => (
        <div key={title}>
          <Check size={15} />
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ProductDepth() {
  const [channel, setChannel] = useState(0);
  const [builderStep, setBuilderStep] = useState(-1);
  const [agent, setAgent] = useState(0);
  const [inbox, setInbox] = useState(0);
  const [voice, setVoice] = useState(false);
  const [filter, setFilter] = useState("All features");
  const [query, setQuery] = useState("");
  const chosen = channels[channel];
  const visible = catalog.filter(
    ([group, title, description]) =>
      (filter === "All features" || filter === group) &&
      `${title} ${description}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="nd-depth">
      <nav className="nd-jump" aria-label="Explore product features">
        <span>EXPLORE INSTANTLIFY</span>
        {[
          ["Channels", "channels-detail"],
          ["Flow builder", "flow-builder"],
          ["AI agents", "ai-agents"],
          ["Inbox & CRM", "inbox-crm"],
          ["Voice", "voice-detail"],
          ["Bookings & payments", "sales-tools"],
          ["Analytics", "growth-detail"],
          ["Every feature", "feature-catalog"],
        ].map(([label, id]) => (
          <a key={id} href={`#${id}`}>
            {label}
            <ArrowUpRight size={11} />
          </a>
        ))}
      </nav>
      <section className="nd-section" id="channels-detail">
        <div className="nd-heading">
          <span className="nm-eyebrow">THE CHANNELS YOUR CUSTOMERS USE</span>
          <h2>
            Four channels.
            <br />
            One connected sales engine.
          </h2>
          <p>
            Explore the triggers, conversations and next steps available for
            each channel.
          </p>
        </div>
        <div
          className="nd-channel-tabs"
          role="group"
          aria-label="Channel details"
        >
          {channels.map(({ name, brand }, i) => (
            <button
              key={name}
              aria-pressed={channel === i}
              className={channel === i ? "active" : ""}
              onClick={() => setChannel(i)}
            >
              <BrandIcon name={brand} size={18} />
              {name}
            </button>
          ))}
        </div>
        <div className="nd-channel-panel">
          <div>
            <div className="nd-channel-title">
              <BrandIcon name={chosen.brand} size={25} />
              <h3>{chosen.title}</h3>
            </div>
            <p className="nd-intro">{chosen.copy}</p>
            <DetailList items={chosen.features} />
          </div>
          <aside className="nd-channel-example">
            <span className="nd-label">
              ILLUSTRATIVE {chosen.name.toUpperCase()} WORKFLOW
            </span>
            <div className="nd-social-post">
              <span className="nd-post-avatar">N</span>
              <div>
                <strong>Your business</strong>
                <small>{chosen.name} · Example</small>
              </div>
              <BrandIcon name={chosen.brand} size={20} />
            </div>
            <div className="nd-offer-art">
              <span>
                LET’S MAKE
                <br />
                <em>something happen.</em>
              </span>
              <span className="nd-art-star">✳</span>
            </div>
            <div className="nd-channel-steps">
              {chosen.example.map((text, i) => (
                <div key={text}>
                  <span>{i === 3 ? <Check size={13} /> : i + 1}</span>
                  {text}
                </div>
              ))}
            </div>
            <p>
              Live delivery depends on channel permissions and provider setup.
            </p>
          </aside>
        </div>
      </section>
      <section className="nd-section nd-builder" id="flow-builder">
        <div className="nd-heading">
          <span className="nm-eyebrow">YOUR LOGIC, WITHOUT THE CODE</span>
          <h2>
            Build the conversation.
            <br />
            Right down to the next step.
          </h2>
          <p>
            Start with a template or map out your own workflow. Every block
            gives you control over what the customer experiences.
          </p>
        </div>
        <div className="nd-builder-layout">
          <div className="nd-canvas">
            <div className="nd-window-bar">
              <span>
                <GitBranch size={15} /> Service enquiry flow
              </span>
              <span className="nd-draft">Illustrative preview</span>
            </div>
            <div className="nd-node-path">
              {[
                {
                  icon: MessageCircle,
                  label: "When a message arrives",
                  text: "Keyword matches “consultation”",
                },
                {
                  icon: Send,
                  label: "Send your first reply",
                  text: "Introduce your services and ask a question",
                },
                {
                  icon: GitBranch,
                  label: "Choose the next path",
                  text: "Route based on the configured condition",
                },
                {
                  icon: CalendarCheck,
                  label: "Share the booking link",
                  text: "Give an interested customer a next step",
                },
              ].map(({ icon: Icon, label, text }, i) => (
                <div
                  key={label}
                  className={`nd-node ${builderStep >= i ? "ran" : ""}`}
                >
                  <span className="nd-node-icon">
                    <Icon size={19} />
                  </span>
                  <div>
                    <strong>{label}</strong>
                    <small>{text}</small>
                  </div>
                  {builderStep >= i && <CheckCircle2 size={17} />}
                  <span className="nd-node-port" />
                </div>
              ))}
            </div>
            <div className="nd-canvas-foot">
              <span aria-live="polite">
                {builderStep < 0
                  ? "Ready to preview"
                  : builderStep < 3
                    ? `Step ${builderStep + 1} of 4 completed`
                    : "Example workflow complete"}
              </span>
              <button
                onClick={() =>
                  setBuilderStep(builderStep >= 3 ? -1 : builderStep + 1)
                }
              >
                <Play size={12} />
                {builderStep < 0
                  ? "Run example flow"
                  : builderStep < 3
                    ? "Continue example"
                    : "Reset example"}
              </button>
            </div>
          </div>
          <div>
            <DetailList
              items={[
                [
                  "Start with a template",
                  "Choose a starting point for your resource delivery, service enquiries or follow-ups.",
                ],
                [
                  "Connect the blocks",
                  "Arrange messages, buttons, conditions, delays and end steps on the visual canvas.",
                ],
                [
                  "Control the timing",
                  "Use waits and delays to decide when your workflow continues.",
                ],
                [
                  "Keep repeat interactions sensible",
                  "Configured cooldowns help prevent repeated starts for the same lead.",
                ],
                [
                  "Publish and inspect",
                  "Enable your reviewed workflow and follow its execution in the logs.",
                ],
                [
                  "Reuse what works",
                  "Import and export flows instead of rebuilding the same logic.",
                ],
              ]}
            />
            <Link className="nm-text-link" href="/auth?mode=signup">
              Create your first automation <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </section>
      <section className="nd-section nd-agent-section" id="ai-agents">
        <div className="nd-heading">
          <span className="nm-eyebrow">AN ASSISTANT WITH BUSINESS CONTEXT</span>
          <h2>
            More than an answer.
            <br />A useful action.
          </h2>
          <p>
            Give your assistant the knowledge and tools to move a conversation
            forward. Review what it does and keep your team within reach.
          </p>
        </div>
        <div className="nd-agent-layout">
          <div>
            <DetailList
              items={[
                [
                  "Train on your own information",
                  "Add FAQs and business documents so replies draw on the context you provide.",
                ],
                [
                  "Qualify the enquiry",
                  "Gather the customer’s needs and help identify the relevant next step.",
                ],
                [
                  "Use configured tools",
                  "Check calendar availability, update CRM details and share configured offer links.",
                ],
                [
                  "Respect the human handoff",
                  "Pass conversations to your team when the assistant reaches its limits.",
                ],
                [
                  "Review activity and usage",
                  "Inspect recorded agent runs, tool calls and AI usage in your workspace.",
                ],
              ]}
            />
          </div>
          <div className="nd-agent-console">
            <div className="nd-window-bar">
              <span>
                <Sparkles size={16} /> Assistant preview
              </span>
              <span>Example only</span>
            </div>
            <div
              className="nd-agent-tabs"
              role="group"
              aria-label="Agent preview"
            >
              {["Knowledge", "Actions", "Oversight"].map((label, i) => (
                <button
                  key={label}
                  aria-pressed={agent === i}
                  className={agent === i ? "active" : ""}
                  onClick={() => setAgent(i)}
                >
                  {label}
                </button>
              ))}
            </div>
            {agent === 0 ? (
              <div className="nd-console-content">
                <span className="nd-label">YOUR BUSINESS KNOWLEDGE</span>
                {[
                  "Services & pricing.pdf",
                  "Customer FAQs",
                  "Appointment guidelines",
                ].map((text) => (
                  <div className="nd-console-row" key={text}>
                    <FileText size={17} />
                    <span>{text}</span>
                    <Check size={14} />
                  </div>
                ))}
                <div className="nd-console-answer">
                  <small>EXAMPLE CUSTOMER QUESTION</small>
                  <p>“What’s included in a consultation?”</p>
                  <strong>Answer using your services and FAQ context.</strong>
                </div>
              </div>
            ) : agent === 1 ? (
              <div className="nd-console-content">
                <span className="nd-label">CONFIGURED TOOL EXAMPLES</span>
                {[
                  [
                    CalendarCheck,
                    "Check availability",
                    "Google Calendar / Cal.com",
                  ],
                  [Users, "Update contact context", "CRM tags and fields"],
                  [
                    CreditCard,
                    "Share an offer link",
                    "Configured Stripe offer",
                  ],
                  [Bell, "Notify your team", "Configured Slack connection"],
                ].map(([Icon, title, text]) => {
                  const ToolIcon = Icon as typeof CalendarCheck;
                  return (
                    <div className="nd-action-row" key={String(title)}>
                      <ToolIcon size={20} />
                      <div>
                        <strong>{String(title)}</strong>
                        <small>{String(text)}</small>
                      </div>
                      <ArrowUpRight size={13} />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="nd-console-content">
                <span className="nd-label">KEEP PEOPLE IN THE LOOP</span>
                <div className="nd-console-answer">
                  <ShieldCheck size={30} />
                  <h3>Your team decides where AI helps.</h3>
                  <p>
                    Review agent activity, manage enabled tools and take over a
                    conversation when it needs a personal response.
                  </p>
                </div>
                <div className="nd-console-row">
                  <Check size={16} />
                  Recorded tool calls
                </div>
                <div className="nd-console-row">
                  <Check size={16} />
                  Human handoff
                </div>
                <div className="nd-console-row">
                  <Check size={16} />
                  Customer booking confirmation
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
      <section className="nd-section" id="inbox-crm">
        <div className="nd-heading">
          <span className="nm-eyebrow">A SHARED INBOX. A CLEARER PICTURE.</span>
          <h2>
            Every message has context.
            <br />
            Every lead has a place.
          </h2>
          <p>
            Put the conversation and the customer record together. Your team can
            see the enquiry, its owner and the details that matter.
          </p>
        </div>
        <div className="nd-inbox-window">
          <div className="nd-window-bar">
            <span>
              <MessageCircle size={16} /> Unified inbox & CRM
            </span>
            <span>Illustrative workspace</span>
          </div>
          <div className="nd-inbox-body">
            <div className="nd-inbox-list">
              {[
                [
                  "JD",
                  "Jordan Davis",
                  "Instagram",
                  "Service enquiry",
                  "Interested",
                ],
                [
                  "AK",
                  "Alex Kim",
                  "WhatsApp",
                  "Consultation request",
                  "Booking",
                ],
                [
                  "SR",
                  "Sam Rivera",
                  "Telegram",
                  "Custom project",
                  "Team handoff",
                ],
              ].map(([initial, name, network, subject], i) => (
                <button
                  key={name}
                  className={inbox === i ? "active" : ""}
                  aria-pressed={inbox === i}
                  onClick={() => setInbox(i)}
                >
                  <span>{initial}</span>
                  <div>
                    <strong>{name}</strong>
                    <small>
                      <BrandIcon name={NETWORKS[network]} size={11} /> {network}{" "}
                      · {subject}
                    </small>
                  </div>
                </button>
              ))}
            </div>
            <div className="nd-contact">
              <span className="nd-label">CONTACT CONTEXT</span>
              <h3>{["Jordan Davis", "Alex Kim", "Sam Rivera"][inbox]}</h3>
              <div className="nd-contact-tags">
                <span>{["Interested", "Booking", "Team handoff"][inbox]}</span>
                <span>
                  {["Service enquiry", "Consultation", "Agency project"][inbox]}
                </span>
              </div>
              <dl>
                <div>
                  <dt>Channel</dt>
                  <dd>{["Instagram", "WhatsApp", "Telegram"][inbox]}</dd>
                </div>
                <div>
                  <dt>Assigned to</dt>
                  <dd>
                    {["Sales team", "Appointments team", "Project lead"][inbox]}
                  </dd>
                </div>
                <div>
                  <dt>Next step</dt>
                  <dd>
                    {
                      [
                        "Share service details",
                        "Confirm the appointment",
                        "Review project requirements",
                      ][inbox]
                    }
                  </dd>
                </div>
              </dl>
              <div className="nd-note">
                <FileText size={15} />
                <div>
                  <strong>Internal note</strong>
                  <p>
                    {
                      [
                        "Asked about our services. Follow up with the relevant package.",
                        "Prefers an afternoon consultation. Confirm before booking.",
                        "Needs a workflow for multiple client accounts. A teammate should review.",
                      ][inbox]
                    }
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="nd-mini-grid">
          {[
            [
              "Shared conversations",
              "Instagram, WhatsApp, Messenger and Telegram in one connected inbox.",
            ],
            [
              "Clear ownership",
              "Assign enquiries, add teammate notes and manage human handoffs.",
            ],
            [
              "Useful customer records",
              "Keep stages, tags, fields and contact history with the conversation.",
            ],
            [
              "Better organisation",
              "Merge duplicate records, segment contacts and configure hot-lead alerts.",
            ],
          ].map(([title, copy]) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="nd-section nd-voice-section" id="voice-detail">
        <div className="nd-voice-copy">
          <span className="nm-eyebrow">A MORE PERSONAL WAY TO REPLY</span>
          <h2>
            Give your assistant
            <br />a voice.
          </h2>
          <p>
            Use a configured voice provider to send AI voice replies. Incoming
            voice-note transcription helps your assistant understand supported
            audio enquiries, too.
          </p>
          <DetailList
            items={[
              [
                "AI voice responses",
                "Generate spoken replies through your configured ElevenLabs integration.",
              ],
              [
                "Incoming voice context",
                "Transcribe supported customer voice notes for the conversation.",
              ],
              [
                "Channel-aware delivery",
                "Send through the media capabilities supported by your connected channel.",
              ],
              [
                "Plan and provider controls",
                "Voice availability follows your plan and configured provider.",
              ],
            ]}
          />
        </div>
        <div className="nd-voice-card">
          <div className="nd-label">
            <Mic size={14} /> ILLUSTRATIVE VOICE MESSAGE
          </div>
          <div className="nd-voice-avatar">N</div>
          <h3>Sound like your business.</h3>
          <p>
            “Thanks for reaching out. Tell me a little about what you’re looking
            for, and we can find the right next step.”
          </p>
          <div
            className={`nd-wave ${voice ? "playing" : ""}`}
            aria-hidden="true"
          >
            {Array.from({ length: 42 }, (_, i) => (
              <i
                key={i}
                style={{
                  height: `${12 + ((i * 17) % 43)}px`,
                  animationDelay: `${i * 0.025}s`,
                }}
              />
            ))}
          </div>
          <button aria-pressed={voice} onClick={() => setVoice(!voice)}>
            <Play size={13} />
            {voice ? "Stop waveform preview" : "Preview voice-message visual"}
          </button>
          <small>This visual preview does not play or generate audio.</small>
          <div className="nd-voice-provider">
            <span>VOICE PROVIDER</span>
            <strong>ElevenLabs</strong>
            <span className="nm-available">Integration available</span>
          </div>
        </div>
      </section>
      <section className="nd-section" id="sales-tools">
        <div className="nd-heading">
          <span className="nm-eyebrow">MAKE THE NEXT STEP EASY</span>
          <h2>
            From “I’m interested”
            <br />
            to “it’s booked.”
          </h2>
          <p>
            Give your assistant a configured booking or purchase path. Keep
            those actions attached to the customer journey.
          </p>
        </div>
        <div className="nd-sales-grid">
          <article>
            <div className="nd-sales-icon">
              <CalendarCheck size={24} />
            </div>
            <h3>Appointments, with confirmation.</h3>
            <p>
              Check calendar availability through a connected provider, help a
              customer find a suitable time and require confirmation before
              creating the booking.
            </p>
            <ul>
              <li>
                <Check />
                Google Calendar and Cal.com connections
              </li>
              <li>
                <Check />
                Availability checks through agent tools
              </li>
              <li>
                <Check />
                Customer confirmation before booking
              </li>
              <li>
                <Check />
                Bookings included in funnel analytics
              </li>
            </ul>
            <div className="nd-sales-preview">
              <CalendarCheck size={22} />
              <div>
                <strong>Consultation requested</strong>
                <small>Check availability → Confirm → Book</small>
              </div>
              <span>Example</span>
            </div>
          </article>
          <article>
            <div className="nd-sales-icon">
              <CreditCard size={24} />
            </div>
            <h3>The right offer, in the conversation.</h3>
            <p>
              Create your offers and connect Stripe. Your assistant can share a
              payment link for a configured offer, with the purchase reflected
              in your funnel.
            </p>
            <ul>
              <li>
                <Check />
                Workspace offer management
              </li>
              <li>
                <Check />
                Stripe-backed payment links
              </li>
              <li>
                <Check />
                Configured offers available to the assistant
              </li>
              <li>
                <Check />
                Payment and revenue tracking
              </li>
            </ul>
            <div className="nd-sales-preview">
              <CreditCard size={22} />
              <div>
                <strong>Your configured offer</strong>
                <small>Share link → Customer checkout → Record payment</small>
              </div>
              <span>Example</span>
            </div>
          </article>
        </div>
      </section>
      <section className="nd-section nd-growth-section" id="growth-detail">
        <div className="nd-heading">
          <span className="nm-eyebrow">KNOW WHAT HAPPENS AFTER THE REPLY</span>
          <h2>
            Connect your activity
            <br />
            to the customer journey.
          </h2>
          <p>
            Review the funnel, compare workflow variants and keep your content
            and offers connected to your sales work.
          </p>
        </div>
        <div className="nd-growth-grid">
          {[
            {
              icon: BarChart3,
              title: "Funnel analytics",
              copy: "Review the journey from comment or message to a reply, booking and payment.",
              items: [
                "Unique lead counts",
                "Booking and payment stages",
                "Revenue recorded in the funnel",
              ],
            },
            {
              icon: GitBranch,
              title: "Workflow experiments",
              copy: "Compare variants so you can understand which approach moves a conversation forward.",
              items: [
                "A/B workflow experiments",
                "Automation-level breakdowns",
                "Variant performance review",
              ],
            },
            {
              icon: Clock,
              title: "Content calendar",
              copy: "Plan and schedule supported channel posts from the workspace where you manage enquiries.",
              items: [
                "Calendar planning",
                "Scheduled content",
                "Supported channel publishing",
              ],
            },
            {
              icon: ArrowUpRight,
              title: "Link-in-bio pages",
              copy: "Publish a page for your offers and record clicks from the people exploring your business.",
              items: [
                "Shareable public pages",
                "Links to your offers",
                "Bio click tracking",
              ],
            },
          ].map(({ icon: Icon, title, copy, items }) => (
            <article key={title}>
              <Icon size={25} />
              <h3>{title}</h3>
              <p>{copy}</p>
              <ul>
                {items.map((item) => (
                  <li key={item}>
                    <Check size={13} />
                    {item}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
      <section className="nd-section nd-agency" id="agency-detail">
        <div className="nd-heading">
          <span className="nm-eyebrow">
            YOUR TEAM. YOUR CLIENTS. YOUR BRAND.
          </span>
          <h2>
            Build beyond
            <br />
            one business.
          </h2>
          <p>
            Keep clients organised in separate workspaces, control access and
            connect the systems your team uses.
          </p>
        </div>
        <div className="nd-agency-grid">
          {[
            {
              icon: Layers,
              title: "Client workspaces",
              copy: "Separate data, channel connections and settings for each client.",
            },
            {
              icon: Users,
              title: "Team roles & invitations",
              copy: "Invite collaborators and choose the access they need.",
            },
            {
              icon: Sparkles,
              title: "Workspace branding",
              copy: "Configure available branding and white-label settings for your agency.",
            },
            {
              icon: Plug,
              title: "API & signed webhooks",
              copy: "Connect external workflows using workspace API keys and verifiable events.",
            },
            {
              icon: ShieldCheck,
              title: "Data controls",
              copy: "Manage the available export, deletion, retention and access controls.",
            },
            {
              icon: FileText,
              title: "Audit visibility",
              copy: "Review recorded workspace actions and AI activity when you need context.",
            },
          ].map(({ icon: Icon, title, copy }) => (
            <article key={title}>
              <Icon size={22} />
              <div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="nd-section nd-catalog" id="feature-catalog">
        <div className="nd-heading">
          <span className="nm-eyebrow">THE DETAILS, ALL IN ONE PLACE</span>
          <h2>Explore every feature.</h2>
          <p>
            Search {catalog.length} feature entries, browse by category and see
            the planned additions. Available features depend on your plan and
            configuration.
          </p>
        </div>
        <div className="nd-catalog-controls">
          <div role="group" aria-label="Feature category">
            {[
              "All features",
              "Automation",
              "AI & voice",
              "Inbox & CRM",
              "Sales & growth",
              "Team & platform",
              "Roadmap",
            ].map((item) => (
              <button
                key={item}
                aria-pressed={filter === item}
                className={filter === item ? "active" : ""}
                onClick={() => setFilter(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <label>
            <Search size={17} />
            <input
              type="search"
              aria-label="Search product features"
              value={query}
              placeholder="Search features…"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>
        <p className="nd-count" aria-live="polite">
          {visible.length} features shown
        </p>
        <div className="nd-catalog-grid">
          {visible.map(([group, title, description, status]) => (
            <article key={title}>
              <div>
                <span>{group}</span>
                {status ? (
                  <span
                    className={
                      status === "Available" ? "nm-available" : "nm-planned"
                    }
                  >
                    {status}
                  </span>
                ) : (
                  <Check size={14} />
                )}
              </div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
        {!visible.length && (
          <p className="nm-empty">
            No matching features. Try another category or search.
          </p>
        )}
        <div className="nd-catalog-end">
          <span>
            <ShieldCheck size={16} /> Planned entries describe future work, not
            enabled capabilities.
          </span>
          <Link className="nm-text-link" href="/auth?mode=signup">
            Explore your workspace <ArrowRight size={15} />
          </Link>
        </div>
      </section>
    </div>
  );
}
