"""AI Credits console actions (2.5.4): provider tests, the rate card, ledger search."""

import time
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client

from apps.billing import credits
from apps.billing.models import AICreditTransaction, ModelPricingRate
from apps.platform_ops.intelligence import provider_keys
from apps.platform_ops.models import PlatformAudit, PlatformRole
from apps.platform_ops.security import new_secret
from apps.tenants.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def setup(settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "ops.localhost"]
    cache.clear()


def staff(role="owner", email="ops@example.com"):
    person = User.objects.create_user(
        username=email, email=email, password="A-very-long-password42", is_staff=True
    )
    return PlatformRole.objects.create(
        user=person, role=role, otp_secret=new_secret(), otp_confirmed=True
    )


def console(operator):
    client = Client(HTTP_HOST="ops.localhost")
    client.force_login(operator.user)
    session = client.session
    session["platform_password_at"] = time.time()
    session["platform_mfa"] = {"version": operator.version, "until": time.time() + 1800}
    session.save()
    return client


def test_named_keys_become_separate_cards_and_missing_providers_show(settings):
    settings.PLATFORM_OPENAI_API_KEY = ""
    env = {
        "PLATFORM_ANTHROPIC_API_KEY_MARKO": "k1",
        "PLATFORM_ANTHROPIC_API_KEY_BAZIL": "k2",
        "PLATFORM_GEMINI_API_KEY": "",
        "UNRELATED_KEY": "x",
    }
    cards = {card["env"]: card for card in provider_keys(env)}
    assert cards["PLATFORM_ANTHROPIC_API_KEY_MARKO"]["label"] == "Anthropic (Marko)"
    assert cards["PLATFORM_ANTHROPIC_API_KEY_BAZIL"]["configured"]
    # An empty or absent key is still shown, as unconfigured, rather than vanishing.
    assert not cards["PLATFORM_GEMINI_API_KEY"]["configured"]
    assert not cards["PLATFORM_OPENAI_API_KEY"]["configured"]
    assert "UNRELATED_KEY" not in cards


def test_provider_test_is_owner_only_throttled_and_cached(settings, monkeypatch):
    monkeypatch.setenv("PLATFORM_XAI_API_KEY", "xai-test")
    owner = console(staff())
    support = console(staff("support", "support@example.com"))
    form = {"env": "PLATFORM_XAI_API_KEY"}
    assert support.post("/ops/credits/test/", form).status_code == 403
    assert owner.post("/ops/credits/test/", form).status_code == 302
    result = cache.get("ops:provider-test:PLATFORM_XAI_API_KEY")
    assert result["ok"] and result["at"]
    # A second click inside a minute must not spend a second request.
    assert owner.post("/ops/credits/test/", form).status_code == 403
    assert PlatformAudit.objects.filter(action="provider.tested").count() == 1
    assert owner.post("/ops/credits/test/", {"env": "DJANGO_SECRET_KEY"}).status_code == 403


def test_rendering_the_page_never_calls_a_provider(monkeypatch):
    monkeypatch.setenv("PLATFORM_XAI_API_KEY", "xai-test")
    with (
        patch("apps.platform_ops.intelligence.ping") as ping,
        patch("redis.Redis.get", return_value=None),
        patch("redis.Redis.ttl", return_value=-2),
    ):
        assert console(staff()).get("/ops/?tab=ai_credits").status_code == 200
    ping.assert_not_called()


def test_a_rate_edit_changes_the_next_charge(workspace):
    ModelPricingRate.objects.create(model_pattern="gpt-5%", our_input=1000, real_input=100)
    owner = console(staff())
    rate = ModelPricingRate.objects.get(model_pattern="gpt-5%")
    before = credits.price(credits.resolve_rate("gpt-5"), tokens_in=1_000_000)[0]
    assert before == Decimal("1000")
    fields = {
        "our_input": "20",
        "real_input": "1.5",
        "our_output": "0",
        "real_output": "0",
        "our_cache_read": "",
        "real_cache_read": "",
        "our_cache_write": "",
        "real_cache_write": "",
    }
    assert owner.post(f"/ops/credits/rates/{rate.pk}/", fields).status_code == 302
    # $20 per million, stored as 2000 cents per million.
    after = credits.price(credits.resolve_rate("gpt-5"), tokens_in=1_000_000)[0]
    assert after == Decimal("2000")
    assert PlatformAudit.objects.filter(action="rate.saved").exists()


def test_rate_card_rejects_bad_input_and_protects_the_fallback():
    owner = console(staff())
    fallback = ModelPricingRate.objects.get(is_fallback_default=True)
    assert owner.post(f"/ops/credits/rates/{fallback.pk}/", {"action": "delete"}).status_code == 403
    assert ModelPricingRate.objects.filter(pk=fallback.pk).exists()
    assert (
        owner.post("/ops/credits/rates/", {"model_pattern": "x%", "our_input": "-1"}).status_code
        == 403
    )
    assert (
        owner.post("/ops/credits/rates/", {"model_pattern": "x%", "our_input": "ten"}).status_code
        == 403
    )
    assert owner.post("/ops/credits/rates/", {"model_pattern": "%"}).status_code == 403
    assert (
        owner.post(
            "/ops/credits/rates/", {"model_pattern": "claude-opus%", "our_input": "50"}
        ).status_code
        == 302
    )
    assert ModelPricingRate.objects.get(model_pattern="claude-opus%").our_input == Decimal("5000")
    assert owner.post("/ops/credits/rates/", {"model_pattern": "claude-opus%"}).status_code == 403


def test_ledger_search_and_type_filter_narrow_the_rows(workspace):
    for key, kind, description in [
        ("a", "usage", "AI step: gpt-4o"),
        ("b", "topup", "Manual top-up"),
        ("c", "usage", "AI extractor"),
    ]:
        AICreditTransaction.objects.for_workspace(workspace).create(
            workspace=workspace,
            key=key,
            type=kind,
            amount_cents=Decimal("-1") if kind == "usage" else Decimal("500"),
            remaining_balance_cents=Decimal("0"),
            description=description,
        )
    client = console(staff())
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        topups = client.get("/ops/?tab=ai_credits&sub=transactions&type=topup")
        extractor = client.get("/ops/?tab=ai_credits&sub=transactions&q=extractor")
    assert topups.context["credits"]["ledger"]["page"].paginator.count == 1
    assert extractor.context["credits"]["ledger"]["page"].paginator.count == 1
    assert b"AI extractor" in extractor.content and b"Manual top-up" not in extractor.content


def test_units_toggle_changes_display_not_storage():
    ModelPricingRate.objects.create(model_pattern="gpt-5%", our_input=1250, real_input=125)
    client = console(staff())
    with patch("redis.Redis.get", return_value=None), patch("redis.Redis.ttl", return_value=-2):
        per_million = client.get("/ops/?tab=ai_credits&sub=pricing&unit=m").content.decode()
        per_token = client.get("/ops/?tab=ai_credits&sub=pricing&unit=token").content.decode()
    assert "$12.5" in per_million
    assert "$0.000013" in per_token
    assert ModelPricingRate.objects.get(model_pattern="gpt-5%").our_input == Decimal("1250")
