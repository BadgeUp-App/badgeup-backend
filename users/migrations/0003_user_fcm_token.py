from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_reset_code_user_reset_code_expires"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="fcm_token",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="user",
            name="fcm_platform",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="user",
            name="fcm_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
