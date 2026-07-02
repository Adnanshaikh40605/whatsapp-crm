from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_platform", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="last_used_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="apikey",
            name="key_prefix",
            field=models.CharField(max_length=12),
        ),
    ]
