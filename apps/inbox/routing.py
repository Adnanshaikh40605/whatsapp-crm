from django.urls import re_path

from apps.embed_api.consumers import EmbedInboxConsumer
from apps.inbox.consumers import InboxConsumer

websocket_urlpatterns = [
    re_path(r"ws/inbox/$", EmbedInboxConsumer.as_asgi()),
    re_path(r"ws/inbox/(?P<org_id>[0-9a-f-]+)/$", InboxConsumer.as_asgi()),
]
