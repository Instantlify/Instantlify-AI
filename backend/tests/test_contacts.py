"""Contacts are the people who message a connected channel: they arrive with the
profile Meta reports, and the CRM panel can read, edit, refresh and remove them."""

from unittest.mock import patch

from test_meta_client import agent_client, connect, inbound

from apps.channels.ingress import normalize_meta
from apps.channels.transport import RetryableError
from apps.crm.models import ChannelIdentity, Lead
from apps.crm.tasks import enrich_lead

WORKSPACE = "/api/workspaces/{}/leads/"


def test_form_and_manual_contact_filters_follow_stored_provenance(client, workspace):
    manual = Lead.objects.create(workspace=workspace, name="Manual contact")
    form = Lead.objects.create(
        workspace=workspace, name="Form contact", fields={"source": "form", "form": "qa"}
    )
    url = WORKSPACE.format(workspace.pk)
    assert [row["id"] for row in client.get(url + "?source=manual").json()["results"]] == [
        str(manual.pk)
    ]
    assert [row["id"] for row in client.get(url + "?source=form").json()["results"]] == [
        str(form.pk)
    ]


def test_webhooks_carry_the_senders_name_and_handle():
    whatsapp = {
        "entry": [
            {
                "id": "1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "15550001"},
                            "contacts": [{"wa_id": "15550100", "profile": {"name": "Omar Haddad"}}],
                            "messages": [
                                {"id": "wamid.1", "from": "15550100", "text": {"body": "hi"}}
                            ],
                        },
                    }
                ],
            }
        ]
    }
    [(_, _, payload)] = normalize_meta(whatsapp, "whatsapp")
    assert (payload["sender_name"], payload["sender_handle"]) == ("Omar Haddad", "+15550100")

    comment = {
        "entry": [
            {
                "id": "ig-account",
                "changes": [
                    {
                        "field": "comments",
                        "value": {"id": "c1", "from": {"id": "9", "username": "maya.chen"}},
                    }
                ],
            }
        ]
    }
    [(_, _, payload)] = normalize_meta(comment, "instagram")
    assert payload["sender_handle"] == "@maya.chen"


def test_first_message_names_the_contact_and_enrichment_fills_the_profile(workspace):
    channel = connect(workspace)
    lead = inbound(channel, "hello", sender="maya-chen").conversation.identity.lead
    # Until the profile is fetched, the raw ID is the placeholder name.
    assert lead.name == "maya-chen" and lead.profile_due_at is not None
    enrich_lead(str(workspace.pk), str(lead.pk))
    lead.refresh_from_db()
    assert (lead.name, lead.handle) == ("Maya Chen", "@maya.chen")
    assert lead.profile_due_at is None and lead.profile_synced_at is not None

    # A name the webhook already carried is kept; the handle still comes from the lookup.
    whatsapp = connect(workspace, "whatsapp", "15550001")
    named = inbound(
        whatsapp, "hi", sender="15550100", sender_name="Omar Haddad", sender_handle="+15550100"
    ).conversation.identity.lead
    assert (named.name, named.handle) == ("Omar Haddad", "+15550100")

    # A rate limit retries later instead of giving up.
    retry = inbound(channel, "yo", sender="lena-f").conversation.identity.lead
    with patch(
        "apps.channels.adapters.FakeChannelAdapter.fetch_profile", side_effect=RetryableError(60)
    ):
        enrich_lead(str(workspace.pk), str(retry.pk))
    retry.refresh_from_db()
    assert retry.name == "lena-f" and retry.profile_due_at is not None


def test_contact_panel_reads_updates_refreshes_and_deletes(client, workspace):
    channel = connect(workspace)
    lead = inbound(channel, "hello", sender="maya-chen").conversation.identity.lead
    url = WORKSPACE.format(workspace.pk) + f"{lead.pk}/"

    row = client.get(url).json()
    assert row["channels"] == ["instagram"]
    assert row["identities"][0]["provider"] == "instagram"
    identity = ChannelIdentity.objects.for_workspace(workspace).get(lead=lead)
    assert row["identities"][0]["conversation_id"] == str(identity.conversation.pk)
    assert row["message_count"] == 1 and row["last_activity_at"]

    updated = client.patch(
        url,
        {"tags": [" vip ", "vip", "hot"], "fields": {"City": "Lahore"}, "email": "m@example.com"},
        format="json",
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["tags"] == ["vip", "hot"]
    assert updated.json()["identities"]
    assert client.patch(url, {"tags": ["x" * 41]}, format="json").status_code == 400
    assert client.patch(url, {"fields": "nope"}, format="json").status_code == 400

    refreshed = client.post(url + "refresh/", format="json")
    assert refreshed.status_code == 200, refreshed.content
    assert (refreshed.json()["name"], refreshed.json()["handle"]) == ("Maya Chen", "@maya.chen")
    assert (
        "?search=maya"
        and client.get(WORKSPACE.format(workspace.pk) + "?search=maya.chen").json()["count"] == 1
    )

    # Agents can read contacts behind their conversations but never delete them.
    assert agent_client(workspace).delete(url).status_code == 403
    assert client.delete(url).status_code == 204
    assert not Lead.objects.for_workspace(workspace).filter(pk=lead.pk).exists()
    assert not ChannelIdentity.objects.for_workspace(workspace).exists()


def test_hand_added_contact_is_editable_and_merges_into_the_real_person(client, workspace):
    url = WORKSPACE.format(workspace.pk)
    manual = client.post(url, {"name": "Maya Chen", "email": "maya@example.com"}, format="json")
    assert manual.status_code == 201, manual.content
    manual_id = manual.json()["id"]
    assert client.get(url + f"{manual_id}/").json()["identities"] == []
    assert (
        client.patch(url + f"{manual_id}/", {"stage": "qualified"}, format="json").status_code
        == 200
    )
    assert client.post(url + f"{manual_id}/refresh/", format="json").status_code == 400
    assert [row["id"] for row in client.get(url + "?source=manual").json()["results"]] == [
        manual_id
    ]

    channel = connect(workspace)
    real = inbound(channel, "hello", sender="maya-chen").conversation.identity.lead
    assert client.get(url + "?source=channel").json()["results"][0]["id"] == str(real.pk)

    merged = client.post(url + f"{real.pk}/merge/", {"source_id": manual_id}, format="json")
    assert merged.status_code == 200, merged.content
    body = merged.json()
    assert (body["name"], body["email"], body["stage"]) == ("Maya Chen", "maya@example.com", "new")
    assert body["channels"] == ["instagram"]
    assert Lead.objects.for_workspace(workspace).count() == 1
