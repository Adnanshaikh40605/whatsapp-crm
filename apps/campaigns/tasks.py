from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def process_campaign(self, campaign_id):
    from apps.campaigns.models import Campaign, CampaignRecipient
    from apps.core.whatsapp_service import WhatsAppService
    from apps.crm.models import Contact

    try:
        campaign = Campaign.objects.select_related("template", "organization").get(id=campaign_id)
    except Campaign.DoesNotExist:
        return {"status": "not_found"}

    contacts = Contact.objects.filter(organization=campaign.organization, is_active=True)
    contact_ids = (campaign.audience_filter or {}).get("contact_ids", [])
    if contact_ids:
        contacts = contacts.filter(id__in=contact_ids)
    elif campaign.contact_group_id:
        contacts = contacts.filter(groups=campaign.contact_group)
    if campaign.audience_filter:
        tags = campaign.audience_filter.get("tags", [])
        if tags:
            contacts = contacts.filter(tags__overlap=tags)

    wa = WhatsAppService(campaign.organization)
    sent = delivered = failed = 0

    campaign.status = Campaign.Status.RUNNING
    campaign.save(update_fields=["status", "updated_at"])

    for contact in contacts:
        recipient, _ = CampaignRecipient.objects.get_or_create(
            organization=campaign.organization,
            campaign=campaign,
            contact=contact,
        )

        result = {}
        if campaign.campaign_type == Campaign.CampaignType.CAROUSEL and campaign.template:
            result = wa.send_carousel_template(
                contact.phone, campaign.template.name,
                campaign.carousel_cards or [],
            )
        elif campaign.campaign_type == Campaign.CampaignType.MEDIA and campaign.media_config:
            media_url = campaign.media_config.get("url", "")
            media_type = campaign.media_type or "image"
            if media_type == "pdf":
                media_type = "document"
            result = wa.send_media(contact.phone, media_type, media_url, campaign.message_content)
        elif campaign.template:
            result = wa.send_template(contact.phone, campaign.template.name, campaign.template.language)
        else:
            result = wa.send_text(contact.phone, campaign.message_content or "Hello from WhatsFlow!")

        wa_id = ""
        if result.get("messages"):
            wa_id = result["messages"][0].get("id", "")

        if result.get("error"):
            from apps.campaigns.campaign_analytics import _parse_failure_code
            recipient.status = CampaignRecipient.Status.FAILED
            recipient.error_message = str(result["error"])
            recipient.failure_code = _parse_failure_code(recipient.error_message)
            failed += 1
        else:
            recipient.status = CampaignRecipient.Status.SENT
            recipient.sent_at = timezone.now()
            recipient.whatsapp_message_id = wa_id
            contact.last_contacted_at = timezone.now()
            contact.save(update_fields=["last_contacted_at", "updated_at"])
            sent += 1
        recipient.save()

    campaign.total_recipients = contacts.count()
    campaign.sent_count = sent
    campaign.delivered_count = delivered
    campaign.failed_count = failed
    campaign.status = Campaign.Status.COMPLETED
    campaign.save()
    return {"status": "completed", "sent": sent, "failed": failed}
