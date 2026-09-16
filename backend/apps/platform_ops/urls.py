from django.urls import path

from . import views

urlpatterns = [
    path("invite/revoke/", views.revoke_invite),
    path("", views.dashboard),
    path("login/", views.sign_in),
    path("logout/", views.sign_out),
    path("mfa/", views.mfa),
    path("control/", views.control),
    path("staff/", views.staff_change),
    path("invite/", views.invite),
    path("accept/", views.accept_invite),
    path("support/", views.start_support),
    path("support/<uuid:pk>/", views.support),
    path("operations/", views.operation_status),
]
