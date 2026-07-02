from django.urls import path

from apps.embed_api.views import (
    ConversationDetailView,
    ConversationListView,
    CustomerDetailView,
    SSOLoginView,
    SendMediaView,
    SendMessageView,
    SendTemplateView,
)

urlpatterns = [
    path("auth/sso-login/", SSOLoginView.as_view(), name="embed-sso-login"),
    path("inbox/conversations/", ConversationListView.as_view(), name="embed-inbox-conversations"),
    path("inbox/conversations/<uuid:conversation_id>/", ConversationDetailView.as_view(), name="embed-inbox-conversation-detail"),
    path("inbox/messages/send/", SendMessageView.as_view(), name="embed-inbox-send"),
    path("inbox/messages/template/", SendTemplateView.as_view(), name="embed-inbox-template"),
    path("inbox/messages/media/", SendMediaView.as_view(), name="embed-inbox-media"),
    path("customers/<str:phone>/", CustomerDetailView.as_view(), name="embed-customer-detail"),
]
