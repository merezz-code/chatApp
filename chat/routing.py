# chat/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # [^/]+ pour autoriser les espaces et autres caractères
    re_path(r'ws/chat/room/(?P<room_name>[^/]+)/$', consumers.ChatConsumer.as_asgi()),

    re_path(r'ws/chat/private/(?P<username>\w+)/$', consumers.PrivateChatConsumer.as_asgi()),
]