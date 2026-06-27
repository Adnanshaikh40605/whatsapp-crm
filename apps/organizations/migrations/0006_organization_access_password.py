# Generated manually for project-level access password

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0005_organization_description_organization_project_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="access_password",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
