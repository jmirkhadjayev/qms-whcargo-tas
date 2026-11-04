from django.urls import path

from . import views

urlpatterns = [
    path("permits/check/", views.PermitCheckView.as_view(), name="permit-check"),
    path("permits/manual-verify/", views.ManualVerifyView.as_view(), name="permit-manual-verify"),
    path("requests/", views.QueueRequestListCreateView.as_view(), name="request-list"),
    path("requests/<int:pk>/", views.QueueRequestDetailView.as_view(), name="request-detail"),
    path(
        "requests/<int:pk>/transition/", views.TransitionView.as_view(), name="request-transition"
    ),
    path(
        "requests/<int:pk>/assign-dock/", views.AssignDockView.as_view(), name="request-assign-dock"
    ),
    path("requests/<int:pk>/resume/", views.ResumeView.as_view(), name="request-resume"),
    path("requests/<int:pk>/call/", views.CallView.as_view(), name="request-call"),
    path("requests/<int:pk>/recall/", views.RecallView.as_view(), name="request-recall"),
    path("requests/<int:pk>/arrive/", views.ArriveView.as_view(), name="request-arrive"),
    path("requests/<int:pk>/priority/", views.PriorityView.as_view(), name="request-priority"),
    path("requests/<int:pk>/ticket/", views.TicketView.as_view(), name="request-ticket"),
    path(
        "requests/<int:pk>/ticket/reprint/",
        views.TicketReprintView.as_view(),
        name="request-ticket-reprint",
    ),
    path("lookups/", views.LookupsView.as_view(), name="lookups"),
]
