"""Seeds the transactional email registry and the segment classifier's label set.

Both are content, not code: an operator edits them in the console afterwards. Seeding
them in a migration (rather than a fixture) means a fresh environment boots with a
working email path instead of raising `TemplateMissing` on the first signup.
"""

from django.db import migrations

TEMPLATES = [
    (
        "welcome-v2",
        "Sent once, immediately after a workspace is created.",
        "Welcome to Nemio, {{ name }}",
        "Hi {{ name }},\n\nYour workspace {{ workspace }} is ready.\n\n"
        "Connect an account and your first automation can be live in a few minutes.\n\n"
        "{{ app_url }}\n\n— The Nemio team",
        "active",
    ),
    (
        "magic-link-signin",
        "Magic link / OTP sign-in email.",
        "Your Nemio sign-in link",
        "Use this link to sign in:\n\n{{ link }}\n\n"
        "It works once and expires in 15 minutes. If you did not ask for it, ignore this email.",
        "active",
    ),
    (
        "password-reset",
        "Password reset.",
        "Reset your Nemio password",
        "Reset your password here:\n\n{{ link }}\n\n"
        "The link expires in 1 hour. If you did not request a reset, nothing has changed.",
        "active",
    ),
    (
        "trial-ending-soon",
        "Fires 3 days before a trial ends.",
        "Your trial ends in {{ days }} days",
        "Hi {{ name }},\n\nYour {{ plan }} trial ends on {{ trial_ends }}.\n\n"
        "Add a card to keep your automations running:\n{{ billing_url }}",
        "active",
    ),
    (
        "plan-changed-v2",
        "Plan change confirmation. The billing line is composed at send time from the "
        "live Stripe upcoming-invoice preview, never from cached local state, because "
        "Stripe's proration and billing-date logic is the source of truth.",
        "You're on the {{ plan }} plan now",
        "Hi {{ name }},\n\nYour workspace {{ workspace }} is now on {{ plan }}.\n\n"
        "{{ billing_line }}\n\nManage your subscription: {{ billing_url }}",
        "active",
    ),
    (
        "manage-subscription-link",
        "Stripe billing-portal link. The URL must be generated fresh immediately "
        "before send: it is single-use and expires in about five minutes, so it can "
        "never be pre-generated and stored.",
        "Manage your Nemio subscription",
        "Hi {{ name }},\n\nManage or cancel your subscription here:\n\n{{ portal_url }}\n\n"
        "This link is single-use and expires shortly.",
        "active",
    ),
    (
        "email-change-notice-current",
        "Goes to the CURRENT address when an email change is requested. Companion to "
        "email-change-confirmation, which goes to the new address.",
        "Your Nemio account email was changed",
        "Your account email was changed to {{ new_email }}.\n\n"
        "If this was not you, contact support immediately: {{ support_email }}",
        "active",
    ),
    (
        "email-change-confirmation",
        "Goes to the NEW address; carries the confirmation link.",
        "Confirm your new Nemio email",
        "Confirm this address for your Nemio account:\n\n{{ link }}",
        "active",
    ),
    (
        "form-submission-received",
        "Sent to a form owner when someone submits their published form.",
        "New submission: {{ form_title }}",
        "{{ form_title }} received a new submission.\n\n{{ summary }}\n\n{{ app_url }}",
        "active",
    ),
    (
        "support-ticket-opened",
        "Acknowledges a ticket, whether a person filed it or the support agent did.",
        "We got your message ({{ ticket_number }})",
        "Hi {{ name }},\n\nWe've logged your request as {{ ticket_number }}:\n\n"
        "{{ subject }}\n\nSomeone will reply by email.",
        "active",
    ),
    (
        "credits-low",
        "Fires when a prepaid AI credit balance is nearly spent and auto top-up is off.",
        "Your AI credits are running low",
        "Hi {{ name }},\n\n{{ workspace }} has {{ balance }} of AI credit left.\n\n"
        "Top up or turn on auto top-up so replies keep going out:\n{{ billing_url }}",
        "active",
    ),
    (
        "auto-topup-failed",
        "Auto top-up was disabled after a declined off-session charge.",
        "We couldn't top up your AI credits",
        "Hi {{ name }},\n\nThe card on file was declined, so automatic top-up is off "
        "for {{ workspace }}.\n\nUpdate your card to switch it back on:\n{{ billing_url }}",
        "active",
    ),
]

CATEGORIES = [
    ("Coach/Consultant", "Coaching, consulting and advisory businesses."),
    ("Education/Training", "Courses, cohorts, tutoring and training providers."),
    ("AI Automation Builder", "Builds automations or AI workflows for clients."),
    ("General Influencer", "Audience-first creator without a named niche."),
    ("Marketing Agency", "Agency selling marketing services to other businesses."),
    ("Ecommerce Store", "Sells physical or digital products directly."),
    ("AI Tech Creator", "Creates content about AI tools and technology."),
    ("Music/Creative Artist", "Musicians, artists and creative practitioners."),
    ("Local Business", "Serves a specific geographic area."),
    ("Software/SaaS", "Sells software or a subscription product."),
    ("Financial Services", "Finance, insurance, lending or investment services."),
    ("Content Agency", "Produces content on behalf of other brands."),
    ("Event Planning", "Events, weddings and experience planning."),
    ("Nonprofit", "Charitable or community organisations."),
    ("Retail Store", "Bricks-and-mortar retail."),
    ("Health/Fitness", "Trainers, clinics, nutrition and wellness."),
    ("Real Estate", "Agents, brokerages and property services."),
]


def seed(apps, schema_editor):
    EmailTemplate = apps.get_model("platform_ops", "EmailTemplate")
    SegmentCategory = apps.get_model("platform_ops", "SegmentCategory")
    for name, description, subject, body, status in TEMPLATES:
        EmailTemplate.objects.update_or_create(
            name=name,
            defaults={
                "description": description,
                "subject": subject,
                "body": body,
                "status": status,
            },
        )
    for name, description in CATEGORIES:
        SegmentCategory.objects.get_or_create(name=name, defaults={"description": description})


def unseed(apps, schema_editor):
    apps.get_model("platform_ops", "EmailTemplate").objects.filter(
        name__in=[row[0] for row in TEMPLATES]
    ).delete()
    apps.get_model("platform_ops", "SegmentCategory").objects.filter(
        name__in=[row[0] for row in CATEGORIES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0005_billingauditrun_blogcategory_emailtemplate_and_more")]

    operations = [migrations.RunPython(seed, unseed)]
