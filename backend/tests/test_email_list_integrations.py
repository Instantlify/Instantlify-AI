import hashlib
from unittest.mock import patch

import pytest

from apps.channels.transport import ProviderError
from apps.crm.integrations import mailchimp_base, sync_email_list

LEAD = {"email": "Ada@Example.com", "name": "Ada Lovelace"}


def test_mailchimp_uses_double_opt_in_by_default():
    with patch(
        "apps.crm.integrations.request", return_value={"id": "m1", "status": "pending"}
    ) as call:
        result = sync_email_list("mailchimp", "key-us21", {"list_id": "L1"}, LEAD)
    assert result == {"id": "m1", "status": "pending"}
    method, url = call.call_args.args
    member = hashlib.md5(b"ada@example.com", usedforsecurity=False).hexdigest()
    assert (method, url) == ("PUT", f"https://us21.api.mailchimp.com/3.0/lists/L1/members/{member}")
    assert call.call_args.kwargs["json"]["status_if_new"] == "pending"
    assert call.call_args.kwargs["auth"] == ("nemio", "key-us21")

    with patch("apps.crm.integrations.request", return_value={"id": "m1"}) as call:
        sync_email_list("mailchimp", "key-us21", {"list_id": "L1", "double_opt_in": "false"}, LEAD)
    assert call.call_args.kwargs["json"]["status_if_new"] == "subscribed"


def test_beehiiv_never_reactivates_or_welcomes():
    with patch("apps.crm.integrations.request", return_value={"data": {"id": "sub_1"}}) as call:
        assert sync_email_list("beehiiv", "tok", {"publication_id": "pub_9"}, LEAD) == {
            "id": "sub_1"
        }
    body = call.call_args.kwargs["json"]
    assert body["reactivate_existing"] is False and body["send_welcome_email"] is False
    assert call.call_args.args[1] == "https://api.beehiiv.com/v2/publications/pub_9/subscriptions"


def test_kit_adds_subscriber_and_optional_tag():
    responses = [{"subscriber": {"id": 42}}, {"subscriber": {"id": 42}}]
    with patch("apps.crm.integrations.request", side_effect=responses) as call:
        result = sync_email_list("kit", "kit-key", {"tag_id": "7"}, LEAD)
    assert result == {"id": "42", "tag_id": "7"}
    assert [c.args[1] for c in call.call_args_list] == [
        "https://api.kit.com/v4/subscribers",
        "https://api.kit.com/v4/tags/7/subscribers",
    ]
    assert call.call_args_list[0].kwargs["headers"] == {"X-Kit-Api-Key": "kit-key"}


@pytest.mark.parametrize(
    "provider,token,options,code",
    [
        ("mailchimp", "no-datacenter", {"list_id": "L"}, "mailchimp_key_invalid"),
        ("mailchimp", "key-us21", {}, "mailchimp_list_missing"),
        ("beehiiv", "tok", {}, "beehiiv_publication_missing"),
        ("kit", "", {}, "integration_credentials_missing"),
    ],
)
def test_configuration_errors(provider, token, options, code):
    with patch("apps.crm.integrations.request"), pytest.raises(ProviderError, match=code):
        sync_email_list(provider, token, options, LEAD)


def test_mailchimp_base():
    assert mailchimp_base("abc-us5") == "https://us5.api.mailchimp.com/3.0"
    with pytest.raises(ProviderError):
        mailchimp_base("abc-evil.com/")
