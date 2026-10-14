# Nemio landing page: reference review and implementation

Reviewed 14 October 2026. The reference was used to identify product categories and visitor interactions. All new page copy, layout, colour choices, illustrative conversations and styling were written for Nemio. No reference artwork, photographs, customer endorsements, branded assets or source code were copied. This reduces copying risk; it is not a guarantee against legal claims.

## Public pages reviewed

- [Homepage, plan cards, comparison and FAQ](https://boosend.ai/)
- [Platform conversational flows](https://boosend.ai/boosend/conversational-flows)
- [AI agents](https://boosend.ai/ai-agents)
- [CRM](https://boosend.ai/crm)
- [Voice notes](https://boosend.ai/ai-voice-notes)
- [Instagram flows](https://boosend.ai/instagram/conversational-flows)
- [Instagram comments](https://boosend.ai/instagram-comments)
- [Instagram stories](https://boosend.ai/instagram-stories)
- [Instagram DMs](https://boosend.ai/instagram-dm)
- [Instagram sales agents](https://boosend.ai/instagram-ai-sales)
- [WhatsApp flows](https://boosend.ai/conversational-flows)
- [WhatsApp agent](https://boosend.ai/whatsapp-agent)
- [Phone number management](https://boosend.ai/phone-number-management)
- [Telegram flows](https://boosend.ai/telegram/conversational-flows)
- [Telegram agent](https://boosend.ai/telegram-agent)
- [Blog index](https://boosend.ai/blog)

The reference's Pricing navigation resolves to its homepage. Its robots.txt and sitemap.xml were not accessible through the research tool. Authenticated screens and service internals were not accessed; public marketing claims cannot establish implementation equivalence.

## Landing-page behaviour delivered

| Area | Nemio implementation |
| --- | --- |
| Brand and visual direction | Original orange, cream and olive design; existing Nemio brand |
| Navigation | Twelve-link, four-category product menu; section links; mobile menu; login and signup |
| Hero | Original positioning and a clickable example conversation |
| Product demos | Comment-to-DM, story reply, WhatsApp qualification and Telegram handoff; simulated reply, action and replay |
| Product detail | Six overview cards followed by dedicated channel, flow builder, AI agent, inbox/CRM, voice, bookings/payments, analytics/growth and agency sections |
| Feature catalogue | 58 searchable entries across seven categories, with nine planned capabilities explicitly labelled |
| Detailed product previews | Switchable channel walkthroughs, four-step flow execution preview, agent knowledge/actions/oversight panels, contact selection with CRM context and an explicitly labelled waveform visual |
| Solutions | Switchable creator, service business and agency workflows |
| Integrations | Seventeen entries; search and category filters; native versus API connections labelled |
| Toolkit | Available and planned capabilities distinguished explicitly |
| Comparison | Workflows versus AI assistant, using Nemio's own capabilities rather than unsupported competitor claims |
| Onboarding | Three-step explanation linked to the existing account flow |
| Pricing | Existing backend plan catalogue; monthly/annual toggle; real limits, savings and trial period; selected plan preserved into signup |
| FAQ | Eight expandable answers about channels, setup, handoff, voice, agencies, plans and data |
| Resources | Existing blog, help, password reset and server-configured policy links |
| Compatibility | Existing invitation and plan query redirects retained |
| Accessibility | Named controls, keyboard focus, native disclosures, skip link, pressed states, live demo/search updates and reduced-motion support |

## Capability coverage and remaining gaps

“Existing” means code exists in this repository, not that a production service was connected or end-to-end verified during this landing-page task. Live services require credentials and configuration. The browser conversation demos send no messages, create no bookings and collect no leads.

| Capability identified | Nemio status and evidence / requirement |
| --- | --- |
| Instagram comments, DMs, story and live-comment keyword triggers | Existing channel/automation adapters and workspace flow builder |
| WhatsApp and Telegram messages | Existing channel adapters; live accounts need provider configuration |
| Messenger | Existing adapter; displayed as supported with provider caveat |
| Visual branching, delays, buttons, templates and execution logs | Existing automation app and workspace editor |
| Simple starter wizard | Existing automation-starter component |
| AI agent, business knowledge, qualification and tools | Existing agents app and workspace agent screen; requires configured LLM for live use |
| Unified inbox, CRM, tags, assignments and notes | Existing CRM app and workspace inbox |
| Voice generation and transcription | Existing ElevenLabs integration and agent audio handling; additional reference voice providers absent |
| Calendar bookings with confirmation | Existing Google Calendar and Cal.com integrations |
| Payment links and subscriptions | Existing Stripe integration and billing app |
| Funnel analytics and A/B tests | Existing analytics/experiments code |
| Content calendar | Existing content app and calendar screen; publishing scope depends on channel |
| Link-in-bio and click tracking | Existing bio pages and growth tracking |
| Client workspaces, roles, invitations and branding | Existing tenants app and settings/team screens |
| Native CRM integrations | Existing Airtable, Notion, GoHighLevel and Attio provider handlers |
| Notifications and external automation | Existing Slack integration, signed webhooks and public API; Zapier/n8n connector packages; Make uses API/webhooks |
| Reference's full integration roster | Not equivalent. Additional native providers, AI calling services, video providers, email and commerce connectors need implementation |
| Dedicated form builder | Missing; labelled planned |
| Automatic abusive-comment deletion | Missing; labelled planned |
| Deep-link browser escape | Missing; labelled planned |
| Creator media kits and live audience stats | Missing; labelled planned |
| Embeddable AI website support widget | Missing; labelled planned |
| Generated video DMs | Missing; labelled planned |
| Voice cloning/record/upload UX equivalent to reference | Not equivalent; provider voice configuration exists but full creator recording/cloning workflow needs implementation |
| WhatsApp number lifecycle management | Channel connection exists; full business-number onboarding, registration and lifecycle UX is not implemented as a dedicated feature |
| Natural-language flow generation | Not established by this review; must not be marketed as delivered |
| Follow-status gating/new-follower triggers | Not established as equivalent; provider support and trigger implementation need verification |
| Multilingual marketing site | English only; reference language selector was not reproduced as a nonfunctional control |
| Customer testimonials and case studies | Omitted until authentic Nemio material is supplied |
| Provider certification, customer counts and conversion claims | Omitted because no Nemio evidence was supplied |
| Unlimited contacts/fixed pricing on all plans | Not claimed. Existing Nemio catalogue controls displayed limits and prices |
| Legal policies | Existing server-configured HTTPS policy links retained; business-specific policies still need supplied URLs |

## Running the result

The page replaces `/` in the existing Next.js app. Use the existing Docker Compose stack to run it with the Django backend. A standalone frontend preview renders the page, but real prices require the backend's `/api/public/plans/` endpoint; an outage is shown with a retry button. No invented fallback prices are inserted.

This repository uses a standalone Next.js server and a separate Django/PostgreSQL/Celery backend. It was not registered as an unrelated static Site, since that would sever the working authentication and backend routes. No external deployment was performed during this change.

Files: `frontend/app/page.tsx`, `frontend/components/landing-page.tsx`, `frontend/components/landing-depth.tsx`, `frontend/app/landing.css`, `frontend/app/landing-depth.css`, `frontend/app/layout.tsx`, and additions to `frontend/tests/public-site.spec.ts`.

## Verification

- All 16 public-site Playwright checks passed after the feature-depth revision, including the new channel, builder, agent, inbox, catalogue and mobile-menu behaviours. API responses were mocked for predictable browser checks; this does not certify live providers.
- TypeScript and targeted ESLint checks passed.
- The optimized standalone Next.js production build passed.
- The expanded production page was verified at `http://localhost:3000/` with its real local backend. The public plan endpoint returned HTTP 200 and the page rendered Starter, Pro and Scale plan cards. Existing backend, database, Redis, worker and Beat services were started without deleting their data.
- Desktop and mobile screenshots were reviewed. An inherited outgoing-message text colour was corrected for contrast; the floating note was moved clear of the hero demo control.
- The signup test fixture now returns an authenticated user after its mocked signup, so it accurately follows a successful login session.
- The first revision used port 3100 to avoid an existing instance. During the feature-depth revision, port 3000 was free, so the expanded preview was served at the user's existing browser address, `http://localhost:3000/`.

## Feature-depth revision

The initial overview compressed too many capabilities into broad cards. The revised page gives each major product area a detailed section, concrete feature lists and its own demonstration or example. A feature jump navigation and searchable catalogue make the longer page easier to explore. All examples remain illustrative; this revision changes the marketing experience, not provider credentials or backend capability coverage.
