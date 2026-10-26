"""Create reusable provider call agents through one-shot integration jobs."""

import json
import re
import uuid
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gating import check_feature
from apps.channels.transport import ProviderError, request
from apps.crm.models import IntegrationConfig, IntegrationJob
from apps.tenants.permissions import workspace_membership
from apps.tenants.services import audit


class CallAgentInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    name = serializers.CharField(max_length=40)
    instructions = serializers.CharField(max_length=8000)
    first_message = serializers.CharField(max_length=1000)
    model = serializers.RegexField(r"^[A-Za-z0-9_.:/-]{1,100}$")
    voice_id = serializers.RegexField(r"^[A-Za-z0-9_-]{1,150}$")
    max_duration_seconds = serializers.IntegerField(min_value=30, max_value=1800, default=600)


def public_job(job):
    data, result = json.loads(job.payload), json.loads(job.result)
    return {
        "id": job.pk,
        "name": data.get("name", ""),
        "status": job.status,
        "agent_id": result.get("agent_id", ""),
        "llm_id": result.get("llm_id", ""),
        "error": result.get("error", ""),
        "is_test": bool(result.get("test")),
        "created_at": job.created_at,
    }


class CallAgentView(APIView):
    def integration(self, request, workspace_id, pk):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        return get_object_or_404(
            IntegrationConfig.objects.for_workspace(workspace_id),
            pk=pk,
            provider__in=["vapi", "retell"],
        )

    def get(self, request, workspace_id, pk):
        config = self.integration(request, workspace_id, pk)
        return Response(
            [
                public_job(job)
                for job in IntegrationJob.objects.for_workspace(workspace_id)
                .filter(integration=config, operation="create_call_agent")
                .order_by("-created_at")[:20]
            ]
        )

    def post(self, request, workspace_id, pk):
        config = self.integration(request, workspace_id, pk)
        check_feature(workspace_id, "integrations_unlocked")
        check_feature(workspace_id, "ai_agent_enabled")
        if not config.enabled or config.status != "active":
            raise serializers.ValidationError("Reconnect your calling integration first.")
        serializer = CallAgentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        request_id = data.pop("request_id")
        with transaction.atomic():
            job, created = IntegrationJob.objects.for_workspace(workspace_id).get_or_create(
                idempotency_key=f"call-agent:{config.pk}:{request_id}",
                defaults={
                    "workspace_id": workspace_id,
                    "integration": config,
                    "operation": "create_call_agent",
                    "payload": json.dumps(data),
                    "available_at": timezone.now(),
                },
            )
            if json.loads(job.payload) != data:
                raise serializers.ValidationError(
                    "This creation request already has different settings. Start a new request."
                )
            if created:
                audit(config.workspace, request.user, "call_agent.requested", job.pk)
        return Response(public_job(job), status=202)


def provider_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", value):
        raise ProviderError("call_agent_result_unknown")
    return value


def create_call_agent(job):
    from apps.platform_ops.security import assert_enabled

    config, data = job.integration, json.loads(job.payload)
    assert_enabled(config.workspace_id, "ai", "integration:" + config.provider)
    check_feature(config.workspace_id, "ai_agent_enabled")
    if not config.enabled or config.status != "active":
        raise ProviderError("integration_unavailable")
    if config.is_test:
        if settings.CHANNEL_ADAPTER_MODE != "fake":
            raise ProviderError("test_integration_disabled")
        return {"agent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, job.idempotency_key)), "test": True}
    token = json.loads(config.credentials).get("api_key")
    if not isinstance(token, str) or not token.strip():
        raise ProviderError("integration_credentials_missing")
    headers = {"Authorization": f"Bearer {token}"}

    def still_connected():
        current = IntegrationConfig.objects.for_workspace(config.workspace_id).get(pk=config.pk)
        check_feature(config.workspace_id, "ai_agent_enabled")
        check_feature(config.workspace_id, "integrations_unlocked")
        assert_enabled(config.workspace_id, "ai", "integration:" + config.provider)
        if (
            not current.enabled
            or current.status != "active"
            or current.credentials != config.credentials
            or current.is_test != config.is_test
        ):
            raise ProviderError("calling_integration_changed")

    still_connected()
    if config.provider == "vapi":
        result = request(
            "POST",
            "https://api.vapi.ai/assistant",
            side_effect=True,
            headers=headers,
            json={
                "name": data["name"],
                "firstMessage": data["first_message"],
                "model": {
                    "provider": "openai",
                    "model": data["model"],
                    "messages": [{"role": "system", "content": data["instructions"]}],
                },
                "voice": {"provider": "11labs", "voiceId": data["voice_id"]},
                "maxDurationSeconds": data["max_duration_seconds"],
                "artifactPlan": {"recordingEnabled": False},
            },
        )
        return {"agent_id": str(uuid.UUID(provider_id(result.get("id"))))}
    if config.provider != "retell":
        raise ProviderError("unsupported_calling_provider")
    llm = request(
        "POST",
        "https://api.retellai.com/create-retell-llm",
        side_effect=True,
        headers=headers,
        json={
            "model_config": {
                "type": "cascading",
                "primary": {"model": data["model"], "tier": "standard"},
            },
            "general_prompt": data["instructions"],
            "begin_message": data["first_message"],
            "general_tools": [
                {
                    "type": "end_call",
                    "name": "end_call",
                    "description": "End the conversation when the caller is finished.",
                }
            ],
        },
    )
    llm_id = provider_id(llm.get("llm_id"))
    # Persist each confirmed external creation. Unknown outcomes are never auto-replayed.
    job.result = json.dumps({"llm_id": llm_id})
    job.save(update_fields=["result"])
    still_connected()
    agent = request(
        "POST",
        "https://api.retellai.com/create-agent",
        side_effect=True,
        headers=headers,
        json={
            "agent_name": data["name"],
            "response_engine": {"type": "retell-llm", "llm_id": llm_id},
            "voice_id": data["voice_id"],
            "max_call_duration_ms": data["max_duration_seconds"] * 1000,
            "data_storage_setting": "basic_attributes_only",
        },
    )
    agent_id = provider_id(agent.get("agent_id"))
    job.result = json.dumps({"llm_id": llm_id, "agent_id": agent_id})
    job.save(update_fields=["result"])
    version = agent.get("version")
    if type(version) is not int or version < 0:
        raise ProviderError("call_agent_version_unknown")
    job.result = json.dumps({"llm_id": llm_id, "agent_id": agent_id, "version": version})
    job.save(update_fields=["result"])
    still_connected()
    request(
        "POST",
        f"https://api.retellai.com/publish-agent-version/{quote(agent_id, safe='')}",
        side_effect=True,
        empty_success=True,
        headers=headers,
        json={"version": version},
    )
    return {"llm_id": llm_id, "agent_id": agent_id, "version": version, "published": True}
