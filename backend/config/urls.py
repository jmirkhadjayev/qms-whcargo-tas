from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from docks import urls as docks_urls

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("cargo_queue.urls")),
    path("api/warehouse/", include("warehouse.urls")),
    path("api/dispatcher/", include("docks.urls")),
    path("api/dock/", include((docks_urls.agent_urlpatterns, "dock"))),
    path("api/display/", include((docks_urls.display_urlpatterns, "display"))),
    path("api/requests/", include((docks_urls.release_urlpatterns, "release"))),
    path("api/exceptions/", include("exceptions_app.urls")),
    path("api/checkpoint/", include("checkpoint.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
