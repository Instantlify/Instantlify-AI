"""A metered knowledge preview. No conversation, delivery, or tool execution."""

import uuid

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.billing.gating import check_feature
from apps.billing.services import complete_usage, reserve_usage
from apps.channels.transport import ProviderError
from apps.tenants.permissions import workspace_membership

from .models import AgentConfig
from .providers import provider_for
from .rag import retrieve
from .runtime import DEFAULT_HANDOFF_KEYWORDS
from .simple import RULES


class PreviewInput(serializers.Serializer):
    question = serializers.CharField(max_length=2000)


class AgentPreviewView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, workspace_id):
        workspace_membership(request, workspace_id, ["owner", "admin"])
        check_feature(workspace_id, "ai_agent_enabled")
        body = PreviewInput(data=request.data)
        body.is_valid(raise_exception=True)
        question = body.validated_data["question"]
        config = AgentConfig.objects.for_workspace(workspace_id).first()
        if not config:
            return Response(
                {"detail": "Save your assistant settings before testing an answer."}, status=400
            )
        keywords = config.handoff_keywords or DEFAULT_HANDOFF_KEYWORDS
        if any(word.casefold() in question.casefold() for word in keywords):
            return Response(
                {
                    "answer": "This message would be handed to your team. No handoff was created in this preview.",
                    "handoff": True,
                    "sources": [],
                    "is_test": config.is_test,
                }
            )
        key = f"preview:{uuid.uuid4()}"
        # Check billing before either embeddings or generation can spend credits.
        usage = reserve_usage(config, key, kind="preview")
        try:
            chunks = retrieve(config, question, f"rag:{key}")
            if not chunks:
                usage.status = "complete"
                usage.save(update_fields=["status"])
                return Response(
                    {
                        "answer": "There is no ready business knowledge to answer from yet. Add your FAQs and wait for them to finish processing.",
                        "handoff": False,
                        "sources": [],
                        "is_test": config.is_test,
                    }
                )
            context = "\n\n".join(chunk.text for chunk in chunks)
            completion = provider_for(config).complete(
                [
                    {"role": "developer", "content": config.system_prompt + RULES + context},
                    {"role": "user", "content": question},
                ],
                [],
            )
            complete_usage(usage, completion, config)
        except ProviderError:
            usage.status = "failed"
            usage.save(update_fields=["status"])
            return Response(
                {
                    "detail": "The assistant could not answer right now. Check your AI configuration and try again."
                },
                status=503,
            )
        return Response(
            {
                "answer": completion.text.strip()
                or "No answer was returned. Try another question.",
                "handoff": False,
                "sources": list(dict.fromkeys(chunk.document.title for chunk in chunks)),
                "is_test": config.is_test,
            }
        )
