from django.urls import include, path

from apps.channels.ingress import meta_webhook, telegram_webhook
from apps.channels.views import ConnectionListView, MetaOAuthCallbackView, MetaOAuthStartView
from apps.dashboard_api.views import WorkspaceStatusView, live, ready
from apps.tenants.invitations import (
    AcceptInvitationView,
    InvitationDetailView,
    InvitationListView,
)
from apps.tenants.views import (
    AuditListView,
    CSRFView,
    JWTLoginView,
    JWTRefreshView,
    JWTRevokeView,
    LoginView,
    LogoutView,
    MembershipDetailView,
    MembershipListView,
    MeView,
    SignupView,
    WorkspaceDetailView,
    WorkspaceListView,
)

urlpatterns = [
    path("", include("config.feature_urls")),
    path("webhooks/<str:provider>/", meta_webhook),
    path("webhooks/telegram/<uuid:connection_id>/", telegram_webhook),
    path("health/live/", live),
    path("health/ready/", ready),
    path("api/auth/csrf/", CSRFView.as_view()),
    path("api/auth/signup/", SignupView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/auth/token/", JWTLoginView.as_view()),
    path("api/auth/token/refresh/", JWTRefreshView.as_view()),
    path("api/auth/token/revoke/", JWTRevokeView.as_view()),
    path("api/workspaces/", WorkspaceListView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/", WorkspaceDetailView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/members/", MembershipListView.as_view()),
    path(
        "api/workspaces/<uuid:workspace_id>/members/<uuid:membership_id>/",
        MembershipDetailView.as_view(),
    ),
    path("api/workspaces/<uuid:workspace_id>/invitations/", InvitationListView.as_view()),
    path(
        "api/workspaces/<uuid:workspace_id>/invitations/<uuid:invitation_id>/",
        InvitationDetailView.as_view(),
    ),
    path("api/invitations/accept/", AcceptInvitationView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/audit/", AuditListView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/status/", WorkspaceStatusView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/connections/", ConnectionListView.as_view()),
    path("api/workspaces/<uuid:workspace_id>/meta/connect/", MetaOAuthStartView.as_view()),
    path("api/meta/callback/", MetaOAuthCallbackView.as_view()),
]
