from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExceptionListView.as_view(), name="exception-list"),
    path("<int:pk>/resolve/", views.ExceptionResolveView.as_view(), name="exception-resolve"),
]
