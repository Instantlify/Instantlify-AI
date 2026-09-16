"""Funnel analytics, A/B experiments, template export/import and the marketplace."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import Experiment, FunnelEvent
from apps.analytics.services import assign_arm, maybe_auto_promote, record
from apps.automations.models import Automation, ConversationState
from apps.automations.services import publish
from apps.automations.tasks import step
from apps.channels.models import ChannelConnection, WebhookEvent
from apps.crm.services import receive
from apps.marketplace.models import Template
from apps.tenants.models import User
from apps.tenants.services import create_workspace

pytestmark = pytest.mark.django_db


def flow(text, keyword="price"):
    return {
        "start": "hi",
        "triggers": [{"kind": "comment", "keyword": keyword}],
        "nodes": [
            {"id": "hi", "data": {"kind": "send_message", "text": text}},
            {"id": "end", "data": {"kind": "end"}},
        ],
        "edges": [{"source": "hi", "target": "end"}],
    }


@pytest.fixture(autouse=True)
def quiet_notify():
    with patch("apps.crm.services.notify"):
        yield


@pytest.fixture
def channel(workspace):
    return ChannelConnection.objects.for_workspace(workspace).create(
        workspace=workspace,
        external_account_id="ig-account",
        display_name="Test",
        access_token="secret",
        expires_at=timezone.now() + timedelta(days=60),
        is_test=True,
    )


def automation(workspace, user, text, keyword="price"):
    item = Automation.objects.for_workspace(workspace).create(workspace=workspace, name=text)
    return publish(item, flow(text, keyword), user)


def comment(channel, sender, text="price please"):
    event = WebhookEvent.objects.for_workspace(channel.workspace_id).create(
        workspace_id=channel.workspace_id,
        connection=channel,
        event_id=f"evt-{sender}-{WebhookEvent.all_objects.count()}",
        payload="{}",
        available_at=timezone.now(),
    )
    return receive(
        event,
        {"sender_id": sender, "text": text, "kind": "comment", "comment_id": f"c-{sender}"},
    )


def test_inbound_reply_and_trigger_are_recorded_once(workspace, user, channel):
    automation(workspace, user, "Prices!")
    message = comment(channel, "lead-1")
    state = ConversationState.objects.for_workspace(workspace).get()
    step(str(workspace.pk), str(state.id))
    kinds = list(
        FunnelEvent.objects.for_workspace(workspace)
        .order_by("created_at")
        .values_list("kind", flat=True)
    )
    assert kinds == ["comment", "triggered", "replied"]
    assert record(workspace.pk, "comment", key=f"inbound:{message.id}") is None
    assert FunnelEvent.objects.for_workspace(workspace).filter(kind="comment").count() == 1


def test_funnel_report_counts_distinct_leads_and_conversion(client, workspace, user, channel):
    item = automation(workspace, user, "Prices!")
    for sender in ["a", "b", "c"]:
        comment(channel, sender)
    for state in ConversationState.objects.for_workspace(workspace):
        step(str(workspace.pk), str(state.id))
    lead_ids = list(FunnelEvent.objects.for_workspace(workspace).values_list("lead_id", flat=True))
    record(workspace.pk, "booked", lead_id=lead_ids[0], automation_id=item.pk, provider="instagram")
    record(
        workspace.pk,
        "paid",
        lead_id=lead_ids[0],
        automation_id=item.pk,
        provider="instagram",
        amount_cents=4900,
    )
    data = client.get(f"/api/workspaces/{workspace.pk}/analytics/funnel/?period=7d").json()
    steps = {step["kind"]: step for step in data["steps"]}
    assert steps["comment"]["leads"] == 3
    assert steps["triggered"]["leads"] == 3
    assert steps["replied"]["leads"] == 3
    assert steps["booked"]["leads"] == 1 and steps["booked"]["conversion"] == round(1 / 3, 4)
    assert steps["paid"]["leads"] == 1
    assert data["revenue_cents"] == 4900
    assert data["automations"][0]["name"] == "Prices!" and data["automations"][0]["paid"] == 1
    assert data["channels"][0]["provider"] == "instagram"


def test_funnel_is_tenant_scoped_and_admin_only(client, workspace, user):
    record(workspace.pk, "dm", lead_id=workspace.pk)
    stranger = User.objects.create_user(username="s", email="s@example.com")
    other = create_workspace(stranger, "Other")
    outsider = APIClient()
    outsider.force_authenticate(stranger)
    assert outsider.get(f"/api/workspaces/{workspace.pk}/analytics/funnel/").status_code == 404
    data = outsider.get(f"/api/workspaces/{other.pk}/analytics/funnel/").json()
    assert all(step["leads"] == 0 for step in data["steps"])


def test_experiment_assignment_is_deterministic_and_respects_split(workspace, user):
    control = automation(workspace, user, "A")
    variant = automation(workspace, user, "B", keyword="other")
    experiment = Experiment.objects.for_workspace(workspace).create(
        workspace=workspace, name="x", control=control, variant=variant, split=30
    )
    arms = [assign_arm(experiment, f"lead-{i}") for i in range(2000)]
    assert arms == [assign_arm(experiment, f"lead-{i}") for i in range(2000)]
    share = arms.count("variant") / len(arms)
    assert 0.25 < share < 0.35


def test_experiment_routes_variant_and_attributes_goal(client, workspace, user, channel):
    control = automation(workspace, user, "Control copy")
    variant = automation(workspace, user, "Variant copy", keyword="other")
    created = client.post(
        f"/api/workspaces/{workspace.pk}/experiments/",
        {"name": "Copy test", "control": control.pk, "variant": variant.pk, "split": 50},
        format="json",
    )
    assert created.status_code == 201, created.content
    experiment = Experiment.objects.for_workspace(workspace).get()
    seen = {"control": 0, "variant": 0}
    for i in range(12):
        comment(channel, f"lead-{i}")
    for state in ConversationState.objects.for_workspace(workspace):
        seen[state.variant] += 1
        assert state.experiment_id == experiment.pk
        step(str(workspace.pk), str(state.id))
        text = state.graph["nodes"][0]["data"]["text"]
        assert text == ("Variant copy" if state.variant == "variant" else "Control copy")
    assert seen["control"] and seen["variant"]
    lead_id = (
        ConversationState.objects.for_workspace(workspace).first().conversation.identity.lead_id
    )
    triggered = FunnelEvent.objects.for_workspace(workspace).get(kind="triggered", lead_id=lead_id)
    record(
        workspace.pk,
        "booked",
        lead_id=lead_id,
        experiment_id=experiment.pk,
        variant=triggered.variant,
        automation_id=triggered.automation_id,
    )
    results = client.get(f"/api/workspaces/{workspace.pk}/experiments/").json()["results"][0][
        "results"
    ]
    assert results[triggered.variant]["conversions"] == 1
    assert results[triggered.variant]["leads"] == seen[triggered.variant]


def test_promoting_variant_republishes_it_under_the_control(client, workspace, user):
    control = automation(workspace, user, "Control copy")
    variant = automation(workspace, user, "Variant copy", keyword="other")
    experiment = Experiment.objects.for_workspace(workspace).create(
        workspace=workspace, name="x", control=control, variant=variant
    )
    response = client.post(
        f"/api/workspaces/{workspace.pk}/experiments/{experiment.pk}/promote/",
        {"winner": "variant"},
        format="json",
    )
    assert response.status_code == 200
    control.refresh_from_db()
    variant.refresh_from_db()
    assert control.published["nodes"][0]["data"]["text"] == "Variant copy"
    assert control.enabled and not variant.enabled
    experiment.refresh_from_db()
    assert (experiment.status, experiment.winner) == ("concluded", "variant")
    # Concluded experiments are inert; a second promote is a no-op.
    client.post(
        f"/api/workspaces/{workspace.pk}/experiments/{experiment.pk}/promote/",
        {"winner": "control"},
        format="json",
    )
    experiment.refresh_from_db()
    assert experiment.winner == "variant"


def test_auto_promote_waits_for_minimum_leads_then_picks_the_better_arm(workspace, user):
    control = automation(workspace, user, "A")
    variant = automation(workspace, user, "B", keyword="other")
    experiment = Experiment.objects.for_workspace(workspace).create(
        workspace=workspace,
        name="x",
        control=control,
        variant=variant,
        auto_promote=True,
        min_leads=3,
    )
    for arm, _ in [("control", 1), ("variant", 3)]:
        for i in range(3):
            record(
                workspace.pk,
                "triggered",
                lead_id=workspace.pk,
                experiment_id=experiment.pk,
                variant=arm,
                key=f"t:{arm}:{i}",
            )
    maybe_auto_promote(experiment)
    experiment.refresh_from_db()
    assert experiment.status == "running"  # 1 distinct lead per arm so far
    import uuid

    for arm, conversions in [("control", 1), ("variant", 3)]:
        for i in range(3):
            lead = uuid.uuid4()
            record(
                workspace.pk, "triggered", lead_id=lead, experiment_id=experiment.pk, variant=arm
            )
            if i < conversions:
                record(
                    workspace.pk, "booked", lead_id=lead, experiment_id=experiment.pk, variant=arm
                )
    maybe_auto_promote(experiment)
    experiment.refresh_from_db()
    assert (experiment.status, experiment.winner) == ("concluded", "variant")


def test_one_running_experiment_per_control_and_same_tenant_only(client, workspace, user):
    control = automation(workspace, user, "A")
    variant = automation(workspace, user, "B", keyword="other")
    url = f"/api/workspaces/{workspace.pk}/experiments/"
    body = {"name": "x", "control": control.pk, "variant": variant.pk}
    assert client.post(url, body, format="json").status_code == 201
    assert client.post(url, body, format="json").status_code == 400
    stranger = User.objects.create_user(username="s", email="s@example.com")
    other = create_workspace(stranger, "Other")
    theirs = automation(other, stranger, "Theirs")
    assert (
        client.post(
            url, {"name": "y", "control": theirs.pk, "variant": variant.pk}, format="json"
        ).status_code
        == 400
    )


def test_export_then_import_round_trips_as_a_draft(client, workspace, user):
    item = automation(workspace, user, "Prices!")
    exported = client.get(f"/api/workspaces/{workspace.pk}/automations/{item.pk}/export/")
    assert exported.status_code == 200
    document = exported.json()
    assert document["format"] == "nemio.automation"
    stranger = User.objects.create_user(username="s", email="s@example.com")
    other = create_workspace(stranger, "Agency client")
    theirs = APIClient()
    theirs.force_authenticate(stranger)
    imported = theirs.post(
        f"/api/workspaces/{other.pk}/automations/import/", {"template": document}, format="json"
    )
    assert imported.status_code == 201, imported.content
    copy = Automation.objects.for_workspace(other).get()
    assert copy.draft["nodes"] == document["graph"]["nodes"]
    assert not copy.enabled and not copy.published


@pytest.mark.parametrize(
    "document",
    [
        {"format": "other"},
        {"format": "nemio.automation", "version": 99, "graph": {}},
        {
            "format": "nemio.automation",
            "version": 1,
            "graph": {"start": "x", "nodes": [], "edges": []},
        },
        "not json",
    ],
)
def test_invalid_templates_are_rejected(client, workspace, document):
    response = client.post(
        f"/api/workspaces/{workspace.pk}/automations/import/", {"template": document}, format="json"
    )
    assert response.status_code == 400


def test_marketplace_publish_list_and_install(client, workspace, user):
    item = automation(workspace, user, "Prices!")
    published = client.post(
        f"/api/workspaces/{workspace.pk}/templates/publish/",
        {"automation": item.pk, "title": "Comment to DM pricing", "category": "sales"},
        format="json",
    )
    assert published.status_code == 201, published.content
    slug = published.json()["slug"]
    anonymous = APIClient()
    listing = anonymous.get("/api/public/templates/?search=pricing").json()
    assert [t["slug"] for t in listing["results"]] == [slug]
    detail = anonymous.get(f"/api/public/templates/{slug}/").json()
    assert detail["graph"]["nodes"][0]["data"]["text"] == "Prices!"
    assert "workspace" not in detail

    stranger = User.objects.create_user(username="s", email="s@example.com")
    other = create_workspace(stranger, "Other")
    theirs = APIClient()
    theirs.force_authenticate(stranger)
    installed = theirs.post(
        f"/api/workspaces/{other.pk}/templates/install/", {"slug": slug}, format="json"
    )
    assert installed.status_code == 201
    copy = Automation.objects.for_workspace(other).get()
    assert copy.installed_from == Template.all_objects.get(slug=slug).pk
    assert Template.all_objects.get(slug=slug).install_count == 1
    # Unlisting hides it from the public listing and from installs.
    assert (
        client.delete(
            f"/api/workspaces/{workspace.pk}/templates/{published.json()['id']}/"
        ).status_code
        == 204
    )
    assert anonymous.get(f"/api/public/templates/{slug}/").status_code == 404
    assert (
        theirs.post(
            f"/api/workspaces/{other.pk}/templates/install/", {"slug": slug}, format="json"
        ).status_code
        == 404
    )
