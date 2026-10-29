"""Private, authenticated client support. Tickets are bound to their reporter and workspace."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.tenants.permissions import workspace_membership

from .growth import open_ticket
from .models import SupportTicket, SupportTicketMessage


class TicketInput(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=10000)
    category = serializers.ChoiceField(choices=SupportTicket.CATEGORIES, default="support")


class MessageInput(serializers.Serializer):
    body = serializers.CharField(max_length=10000)


def ticket_data(ticket):
    return {
        "id": ticket.pk,
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "body": ticket.body,
        "category": ticket.category,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "messages": [
            {"id": m.pk, "body": m.body, "from_staff": m.from_staff, "created_at": m.created_at}
            for m in ticket.messages.all()
        ],
    }


class MyTicketsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request, workspace_id):
        workspace_membership(request, workspace_id)
        tickets = SupportTicket.objects.filter(
            workspace_id=workspace_id, reporter=request.user
        ).prefetch_related("messages")
        return Response([ticket_data(t) for t in tickets[:100]])

    def post(self, request, workspace_id):
        member = workspace_membership(request, workspace_id)
        data = TicketInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            ticket = open_ticket(
                **data.validated_data,
                reporter_email=request.user.email,
                reporter_name=request.user.get_full_name() or request.user.email,
                reporter_channel="client-portal",
                workspace=member.workspace,
            )
            ticket.reporter = request.user
            ticket.save(update_fields=["reporter"])
        return Response(ticket_data(ticket), status=201)


class MyTicketReplyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @transaction.atomic
    def post(self, request, workspace_id, ticket_id):
        workspace_membership(request, workspace_id)
        ticket = get_object_or_404(
            SupportTicket.objects.select_for_update(),
            pk=ticket_id,
            workspace_id=workspace_id,
            reporter=request.user,
        )
        data = MessageInput(data=request.data)
        data.is_valid(raise_exception=True)
        SupportTicketMessage.objects.create(
            ticket=ticket, author=request.user, **data.validated_data
        )
        ticket.status = "unresolved"
        ticket.is_read = False
        ticket.save(update_fields=["status", "is_read", "updated_at"])
        return Response(ticket_data(ticket), status=201)


def notify_reply(ticket, body):
    """Email delivery failures must not lose the saved support reply."""
    import logging

    from django.conf import settings
    from django.core.mail import send_mail

    try:
        send_mail(
            f"Nemio support {ticket.ticket_number}: {ticket.subject}",
            f"Nemio support replied to your request:\n\n{body}\n\n"
            "If you have a Nemio account, open Help & support to continue this conversation.",
            settings.DEFAULT_FROM_EMAIL,
            [ticket.reporter_email],
        )
    except Exception:
        logging.getLogger(__name__).exception("Support reply email failed for ticket %s", ticket.pk)
