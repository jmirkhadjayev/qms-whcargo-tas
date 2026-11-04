from django.urls import path

from . import release_views, views

# Mounted under /api/dock/ (dock agent) and /api/display/ (public screens) in config/urls.py.
agent_urlpatterns = [
    path("me/", views.AgentScreenView.as_view(), name="dock-me"),
    path("checkin/", views.CheckInView.as_view(), name="dock-checkin"),
    path("checkout/", views.CheckOutView.as_view(), name="dock-checkout"),
    path("scan/", views.AgentScanView.as_view(), name="dock-scan"),
]

display_urlpatterns = [
    path("hall/", views.DisplayHallView.as_view(), name="display-hall"),
    path("led/<str:code>/", views.DisplayLedView.as_view(), name="display-led"),
]

# Mounted under /api/requests/: what the dock agent does with the customer's cargo.
release_urlpatterns = [
    path("<int:pk>/release/start/", release_views.StartView.as_view(), name="release-start"),
    path(
        "<int:pk>/release/progress/", release_views.ProgressView.as_view(), name="release-progress"
    ),
    path("<int:pk>/release/finish/", release_views.FinishView.as_view(), name="release-finish"),
    path("<int:pk>/release/partial/", release_views.PartialView.as_view(), name="release-partial"),
    path("<int:pk>/problems/", release_views.ProblemView.as_view(), name="request-problem"),
]

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="dispatcher-overview"),
    path("queue/", views.QueueView.as_view(), name="dispatcher-queue"),
    path(
        "docks/<str:code>/maintenance/",
        views.DockMaintenanceView.as_view(),
        name="dock-maintenance",
    ),
]
