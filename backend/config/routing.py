from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/dispatcher/$", consumers.DispatcherConsumer.as_asgi()),
    re_path(r"^ws/warehouse/$", consumers.WarehouseConsumer.as_asgi()),
    re_path(r"^ws/checkpoint/$", consumers.CheckpointConsumer.as_asgi()),
    re_path(r"^ws/dock/(?P<code>[A-Za-z0-9-]+)/$", consumers.DockConsumer.as_asgi()),
    re_path(r"^ws/display/hall/$", consumers.HallDisplayConsumer.as_asgi()),
    re_path(r"^ws/display/led/(?P<code>[A-Za-z0-9-]+)/$", consumers.LedDisplayConsumer.as_asgi()),
]
