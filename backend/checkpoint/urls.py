from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="checkpoint-overview"),
    path("scan/", views.ScanView.as_view(), name="checkpoint-scan"),
    path("<int:pk>/confirm/", views.ConfirmView.as_view(), name="checkpoint-confirm"),
    path("<int:pk>/hold/", views.HoldView.as_view(), name="checkpoint-hold"),
]
