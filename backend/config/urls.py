from django.urls import include, path

from apps.channels.ingress import (
    linkedin_webhook,
    meta_webhook,
    snapchat_webhook,
    telegram_webhook,
)
from apps.channels.views import (
    ConnectionListView,
    LinkedInOAuthCallbackView,
    LinkedInOAuthStartView,
    MetaOAuthCallbackView,
    MetaOAuthStartView,
)
from apps.dashboard_api.views import WorkspaceStatusView, live, ready
from apps.platform_ops.public import (
    AnnouncementListView,
    AnnouncementSeenView,
    BlogViewBeaconView,
    FunnelEventView,
    PageVisitView,
    PromoView,
    PublicBlogDetail,
    PublicBlogList,
    SupportChatView,
    SupportTicketView,
    WizardProgressView,
)
from apps.tenants.invitations import (
    AcceptInvitationView,
    InvitationDetailView,
    InvitationListView,
)
from apps.tenants.recovery import PasswordResetConfirmView, PasswordResetRequestView
from apps.tenants.verification import ResendVerificationView, VerifyEmailView
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
    path("ops/", include("apps.platform_ops.urls")),
    path("", include("config.feature_urls")),
    path("webhooks/telegram/<uuid:connection_id>/", telegram_webhook),
    path("webhooks/linkedin/", linkedin_webhook),
    path("webhooks/snapchat/", snapchat_webhook),
    path("webhooks/<str:provider>/", meta_webhook),
    path("health/live/", live),
    path("health/ready/", ready),
    path("api/auth/csrf/", CSRFView.as_view()),
    path("api/auth/signup/", SignupView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/password-reset/", PasswordResetRequestView.as_view()),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("api/auth/verify-email/", VerifyEmailView.as_view()),
    path("api/auth/verify-email/resend/", ResendVerificationView.as_view()),
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
    path("api/workspaces/<uuid:workspace_id>/linkedin/connect/", LinkedInOAuthStartView.as_view()),
    path("api/linkedin/callback/", LinkedInOAuthCallbackView.as_view()),
    # Growth surfaces: written from the tenant app and the public marketing site,
    # read only by the platform console.
    path("api/growth/funnel/", FunnelEventView.as_view()),
    path("api/growth/wizard/", WizardProgressView.as_view()),
    path("api/growth/visit/", PageVisitView.as_view()),
    path("api/growth/blog-view/", BlogViewBeaconView.as_view()),
    path("api/growth/tickets/", SupportTicketView.as_view()),
    path("api/growth/support-chat/", SupportChatView.as_view()),
    path("api/growth/announcements/", AnnouncementListView.as_view()),
    path("api/growth/announcements/<int:pk>/seen/", AnnouncementSeenView.as_view()),
    path("api/growth/promo/", PromoView.as_view()),
    path("api/blog/", PublicBlogList.as_view()),
    path("api/blog/<slug:slug>/", PublicBlogDetail.as_view()),
]
