from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_contactgroup"),
        ("campaigns", "0005_campaign_contact_group_whatsapptemplate_components_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaignrecipient",
            name="failure_code",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.CreateModel(
            name="CampaignClickEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("button_type", models.CharField(blank=True, max_length=30)),
                ("button_name", models.CharField(blank=True, max_length=255)),
                ("button_url", models.CharField(blank=True, max_length=500)),
                ("click_count", models.PositiveIntegerField(default=1)),
                ("clicked_at", models.DateTimeField()),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="click_events",
                        to="campaigns.campaign",
                    ),
                ),
                (
                    "contact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="campaign_click_events",
                        to="crm.contact",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)ss",
                        to="organizations.organization",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="click_events",
                        to="campaigns.campaignrecipient",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["organization", "campaign", "clicked_at"], name="campaigns_c_organiz_7f2a91_idx"),
                    models.Index(fields=["organization", "campaign", "button_name"], name="campaigns_c_organiz_4c8b12_idx"),
                ],
            },
        ),
    ]
