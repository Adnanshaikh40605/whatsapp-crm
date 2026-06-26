from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message(self, message_id):
    from apps.core.whatsapp_service import WhatsAppService
    from apps.inbox.models import Message

    try:
        message = Message.objects.select_related(
            "conversation__contact", "organization",
        ).get(id=message_id)
    except Message.DoesNotExist:
        return {"status": "not_found"}

    org = message.organization
    phone = message.conversation.contact.phone
    wa = WhatsAppService(org)

    result = {}
    if message.message_type == Message.MessageType.TEXT:
        result = wa.send_text(phone, message.content)
    elif message.message_type == Message.MessageType.IMAGE and message.media_url:
        result = wa.send_media(phone, "image", message.media_url, message.content)
    elif message.message_type == Message.MessageType.VIDEO and message.media_url:
        result = wa.send_media(phone, "video", message.media_url, message.content)
    elif message.message_type == Message.MessageType.DOCUMENT and message.media_url:
        result = wa.send_media(phone, "document", message.media_url, message.content)
    elif message.template_name:
        result = wa.send_template(phone, message.template_name)
    else:
        result = wa.send_text(phone, message.content)

    wa_id = ""
    if result.get("messages"):
        wa_id = result["messages"][0].get("id", "")

    message.status = Message.Status.SENT if not result.get("error") else Message.Status.FAILED
    message.whatsapp_message_id = wa_id
    message.provider_message_id = wa_id
    message.metadata = {
        **message.metadata,
        "sent_at": timezone.now().isoformat(),
        "channel": Message.Channel.WHATSAPP,
        "api_response": result,
    }
    message.save(update_fields=["status", "whatsapp_message_id", "provider_message_id", "metadata", "updated_at"])
    return {"status": message.status, "message_id": str(message_id)}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms_message(self, message_id):
    from apps.core.sms_service import SMSService
    from apps.inbox.models import Message

    try:
        message = Message.objects.select_related(
            "conversation__contact", "organization",
        ).get(id=message_id)
    except Message.DoesNotExist:
        return {"status": "not_found"}

    phone = message.metadata.get("sms_to") or message.conversation.contact.phone
    result = SMSService(message.organization).send_text(phone, message.content)
    provider_id = result.get("sid", "")

    message.status = Message.Status.SENT if not result.get("error") else Message.Status.FAILED
    message.provider_message_id = provider_id
    message.metadata = {
        **message.metadata,
        "sms_to": phone,
        "sent_at": timezone.now().isoformat(),
        "channel": Message.Channel.SMS,
        "api_response": result,
    }
    message.save(update_fields=["status", "provider_message_id", "metadata", "updated_at"])
    return {"status": message.status, "message_id": str(message_id)}


@shared_task
def process_inbound_webhook(payload):
    from apps.inbox.services import WebhookProcessor
    processor = WebhookProcessor(payload)
    return processor.process()
