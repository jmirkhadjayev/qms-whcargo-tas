from django.urls import path

from . import views

urlpatterns = [
    path("tasks/", views.TaskListView.as_view(), name="warehouse-tasks"),
    path("tasks/scan/", views.TaskScanView.as_view(), name="warehouse-scan"),
    path("tasks/<int:pk>/start/", views.TaskStartView.as_view(), name="warehouse-start"),
    path("tasks/<int:pk>/ready/", views.TaskReadyView.as_view(), name="warehouse-ready"),
    path("tasks/<int:pk>/problem/", views.TaskProblemView.as_view(), name="warehouse-problem"),
    path("tasks/<int:pk>/handover/", views.TaskHandOverView.as_view(), name="warehouse-handover"),
]
