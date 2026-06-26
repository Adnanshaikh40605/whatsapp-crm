from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.inbox.views import CannedReplyViewSet, ConversationViewSet, MessageViewSet

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")
router.register("canned-replies", CannedReplyViewSet, basename="canned-reply")

urlpatterns = [
    path("message-log/", MessageViewSet.as_view({"get": "list"}), name="message-log"),
    path("", include(router.urls)),
]
